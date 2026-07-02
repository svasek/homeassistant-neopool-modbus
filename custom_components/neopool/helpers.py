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

import datetime
import logging
from typing import Any

from neopool_modbus.decoders import (
    decode_device_time,
    encode_device_time,
    parse_register_int as _lib_parse_register_int,
)

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import homeassistant.util.dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def get_device_time(
    data: dict[str, Any], hass: HomeAssistant | None = None
) -> datetime.datetime | None:
    """Decode ``MBF_PAR_TIME`` as UTC-normalised wall-clock time."""
    unix_ts = data.get("MBF_PAR_TIME")
    if unix_ts is None:
        return None
    tz = (
        dt_util.get_time_zone(hass.config.time_zone) if hass else datetime.UTC
    ) or datetime.UTC
    return decode_device_time(unix_ts, tz)


def prepare_device_time(hass: HomeAssistant | None = None) -> int:
    """Return the unix timestamp the device should display as local wall-clock."""
    if hass:
        tz = dt_util.get_time_zone(hass.config.time_zone) or datetime.UTC
        return encode_device_time(dt_util.now(tz))
    return encode_device_time(dt_util.utcnow())  # pragma: no cover


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


def parse_register_int(raw: int | str, name: str) -> int:
    """Parse a Modbus register value, raising a translated ServiceValidationError."""
    try:
        return _lib_parse_register_int(raw)
    except ValueError as err:
        msg = str(err)
        if msg.startswith("register value out of range"):
            key = "register_out_of_range"
        elif msg.startswith("register value must not be a float"):
            key = "invalid_register_float"
        else:
            # bool / unparsable string / unsupported type all collapse to
            # the generic "invalid type" translation.
            key = "invalid_register_type"
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=key,
            translation_placeholders={"name": name, "value": str(raw)},
        ) from err
