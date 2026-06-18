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

"""Helper functions for the NeoPool integration."""

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


def prepare_device_time(hass: HomeAssistant | None = None) -> int:
    """Return the unix timestamp the device should display as local wall-clock."""
    if hass:
        ha_tz = dt_util.get_time_zone(hass.config.time_zone)
        now_local = dt_util.now(ha_tz)
        # WORKAROUND: the device's naive display shows the correct wall-clock time
        epoch_local = datetime.datetime(1970, 1, 1, tzinfo=ha_tz)
        return int((now_local - epoch_local).total_seconds())
    return int(dt_util.now().timestamp())  # pragma: no cover


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
    """Return the timestamp for the next interval start, rounded to the nearest minute.

    Returns None if seconds is None, not a number, or <= 0.
    """
    if seconds is None or not isinstance(seconds, (int, float)) or seconds <= 0:
        return None

    if hass:
        ha_tz = dt_util.get_time_zone(hass.config.time_zone)
        now_local = dt_util.now(ha_tz)
        target_time = now_local + datetime.timedelta(seconds=seconds)
    else:
        now_utc = dt_util.utcnow()
        target_time = now_utc + datetime.timedelta(seconds=seconds)

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
    """Perform minimal Modbus read to get device serial number."""
    host = config.get(CONF_HOST, "")
    port = config.get(CONF_PORT, 502)
    unit_id = config.get("unit_id", 1)
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
