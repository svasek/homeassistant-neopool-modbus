# Copyright 2025 Miloš Svašek

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helper functions for the NeoPool integration.

This module contains helper functions for the NeoPool integration.
It includes functions to handle device time, prepare data for writing to the device,
and parse version information.
"""

import asyncio
import datetime
import logging
from typing import Any

from neopool_modbus import async_probe_serial
from neopool_modbus.exceptions import NeoPoolError
from neopool_modbus.registers import DEFAULT_MODBUS_FRAMER

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import homeassistant.util.dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# This function takes a dictionary of data and returns the device time as a datetime object
# It extracts the low and high parts of the time from the dictionary, combines them into a single timestamp,
# and converts it to a datetime object in UTC timezone
def get_device_time(
    data: dict[str, Any], hass: HomeAssistant | None = None
) -> datetime.datetime | None:
    """Get device time and convert to datetime object."""
    unix_ts = data.get("MBF_PAR_TIME")
    if unix_ts is None:
        return None
    if hass:
        local_tz = dt_util.get_time_zone(hass.config.time_zone)
        # WORKAROUND: This is the naive datetime object, without timezone info
        dt_naive = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=unix_ts)
        dt_local = dt_naive.replace(tzinfo=local_tz)
        return dt_local.astimezone(datetime.UTC)
    return datetime.datetime.fromtimestamp(unix_ts, tz=datetime.UTC)


# This function prepares the device time for writing to the device.
# The NeoPool controller stores time as a single 32-bit unix-style counter
# but is timezone-naive — it just shows the value back through its display
# as a wall-clock time. To get the display to match the user's local clock,
# we anchor the "epoch" at 1970-01-01 in the user's timezone instead of UTC.
def prepare_device_time(hass: HomeAssistant | None = None) -> int:
    """Return the unix timestamp the device should display as local wall-clock."""
    if hass:
        ha_tz = dt_util.get_time_zone(hass.config.time_zone)
        now_local = dt_util.now(ha_tz)
        # The device displays this counter as a naive wall-clock time, so we
        # measure seconds from a 1970 epoch anchored in the same local timezone
        # as `now_local`. The subtraction cancels the timezone offset out and
        # yields the local-clock seconds the device's display expects.
        epoch_local = datetime.datetime(1970, 1, 1, tzinfo=ha_tz)
        return int((now_local - epoch_local).total_seconds())
    return int(dt_util.now().timestamp())  # pragma: no cover


# This function checks if the device time is out of sync with the Home Assistant time
# It compares the device time with the current time in UTC and returns True if the difference is greater than the threshold
def is_device_time_out_of_sync(
    data: dict[str, Any], hass: HomeAssistant | None = None, threshold_seconds: int = 60
) -> bool:
    """Returns True if device time and HA time differ by more than threshold_seconds."""
    device_dt = get_device_time(data, hass)
    if device_dt is None:
        return False
    now_dt = dt_util.utcnow().replace(tzinfo=datetime.UTC)
    diff = abs((device_dt - now_dt).total_seconds())
    return diff > threshold_seconds


def calculate_next_interval_time(
    seconds: float | None, hass: HomeAssistant | None = None
) -> datetime.datetime | None:
    """Calculate the timestamp for the next interval start.

    Args:
        seconds: Number of seconds until the next interval starts (countdown).
        hass: Home Assistant instance for timezone info (optional).

    Returns:
        datetime object representing when the next interval will start,
        or None if seconds is None, not a number, or <= 0.
        Time is rounded to the nearest minute (no seconds).
    """
    if seconds is None or not isinstance(seconds, (int, float)) or seconds <= 0:
        return None

    if hass:
        # Get current time in HA's local timezone
        ha_tz = dt_util.get_time_zone(hass.config.time_zone)
        now_local = dt_util.now(ha_tz)
        # Add seconds using timedelta
        target_time = now_local + datetime.timedelta(seconds=seconds)
    else:
        # Fallback to UTC if hass is not available
        now_utc = dt_util.utcnow()
        target_time = now_utc + datetime.timedelta(seconds=seconds)

    # Round to nearest minute (set seconds and microseconds to 0)
    return target_time.replace(second=0, microsecond=0)


def parse_register_int(raw: int | str, name: str) -> int:
    """Parse an integer from decimal or hex string (e.g. '1539' or '0x0603')."""
    if isinstance(raw, bool):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_register_type",
            translation_placeholders={"name": name, "value": str(raw)},
        )
    if isinstance(raw, float):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_register_float",
            translation_placeholders={"name": name, "value": str(raw)},
        )
    try:
        val = int(raw, 0) if isinstance(raw, str) else int(raw)
    except (ValueError, TypeError) as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_register_type",
            translation_placeholders={"name": name, "value": str(raw)},
        ) from err
    if not 0 <= val <= 65535:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="register_out_of_range",
            translation_placeholders={"name": name, "value": str(val)},
        )
    return val


async def async_get_device_serial(
    config: dict[str, Any], timeout: float = 5.0
) -> str | None:
    """Perform minimal Modbus read to get device serial number.

    Thin wrapper around :func:`neopool_modbus.async_probe_serial` that
    converts the library's exception-based contract into the
    ``str | None`` shape used by callers (config flow / migration), where
    a missing serial is an expected outcome rather than an error.

    Args:
        config: Configuration dict with host, port, unit_id, modbus_framer.
            The legacy ``slave_id`` key is still accepted as a fallback when
            ``unit_id`` is not present.
        timeout: Timeout in seconds for the Modbus probe (connect + read).

    Returns:
        The 24-character hex serial string, or ``None`` if the device was
        unreachable, the read failed, or the registers contained no
        usable serial bytes. ``asyncio.CancelledError`` is propagated.
    """
    host = config.get(CONF_HOST, "")
    port = config.get(CONF_PORT, 502)
    unit_id = config.get("unit_id", config.get("slave_id", 1))
    framer = config.get("modbus_framer", DEFAULT_MODBUS_FRAMER)

    try:
        return await async_probe_serial(
            host,
            port=port,
            unit_id=unit_id,
            framer=framer,
            timeout=timeout,
        )
    except asyncio.CancelledError:
        raise
    except NeoPoolError as err:
        _LOGGER.warning(
            "Trial Modbus read failed for %s:%s: %s (%s)",
            host,
            port,
            err,
            type(err).__name__,
        )
        return None
