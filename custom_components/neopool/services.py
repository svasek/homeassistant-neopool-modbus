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

"""Services for the NeoPool integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from neopool_modbus.decoders import get_timer_interval, hhmm_to_seconds
from neopool_modbus.exceptions import NeoPoolError
from neopool_modbus.registers import TIMER_BLOCKS

from .const import DOMAIN
from .coordinator import NeoPoolCoordinator
from .helpers import parse_register_int

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_TIMER = "set_timer"
SERVICE_WRITE_REGISTER = "write_register"

ATTR_ENTRY_ID = "entry_id"
ATTR_TIMER = "timer"
ATTR_START = "start"
ATTR_STOP = "stop"
ATTR_PERIOD = "period"
ATTR_ENABLE = "enable"
ATTR_ADDRESS = "address"
ATTR_VALUE = "value"
ATTR_APPLY = "apply"

SERVICE_SET_TIMER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_TIMER): cv.string,
        vol.Optional(ATTR_START): cv.string,
        vol.Optional(ATTR_STOP): cv.string,
        vol.Optional(ATTR_PERIOD): vol.All(int, vol.Range(min=1, max=604800)),
        # 'enable' carries the relay-mode integer (0=disabled, 1=auto, 3=on, 4=off)
        # used by the relay_mode select platform.
        vol.Optional(ATTR_ENABLE): vol.All(int, vol.Range(min=0, max=4)),
    }
)

SERVICE_WRITE_REGISTER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_ADDRESS): cv.string,
        vol.Required(ATTR_VALUE): cv.string,
        vol.Optional(ATTR_APPLY, default=True): cv.boolean,
    }
)


def _get_coordinator(hass: HomeAssistant, call: ServiceCall) -> NeoPoolCoordinator:
    """Resolve the coordinator for a service call.

    If `entry_id` is provided in the service data, look it up; otherwise
    use the first loaded config entry. Raises ServiceValidationError if
    no matching loaded entry / coordinator is found.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    entry_id = call.data.get(ATTR_ENTRY_ID)
    if entry_id:
        entry = next((e for e in entries if e.entry_id == entry_id), None)
    else:
        entry = next(
            (e for e in entries if e.state == ConfigEntryState.LOADED),
            None,
        )
    if not entry:
        if entry_id:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_loaded_entry",
        )
    coordinator: NeoPoolCoordinator | None = entry.runtime_data
    if coordinator is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_coordinator",
            translation_placeholders={"entry_id": entry.entry_id},
        )
    return coordinator


async def _async_set_timer(call: ServiceCall) -> None:
    """Set a timer on the pool controller."""
    timer_name = call.data[ATTR_TIMER]
    if timer_name not in TIMER_BLOCKS:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_timer",
            translation_placeholders={
                "timer_name": timer_name,
                "valid_timers": ", ".join(sorted(TIMER_BLOCKS)),
            },
        )

    coordinator = _get_coordinator(call.hass, call)
    start = call.data.get(ATTR_START)
    stop = call.data.get(ATTR_STOP)
    period = call.data.get(ATTR_PERIOD)
    enable = call.data.get(ATTR_ENABLE)

    start_sec = hhmm_to_seconds(start) if start else None
    stop_sec = hhmm_to_seconds(stop) if stop else None
    interval = get_timer_interval(start_sec, stop_sec) if (start and stop) else None

    timer_data: dict[str, Any] = {}
    if start_sec is not None:
        timer_data["on"] = start_sec
    if interval is not None:
        timer_data["interval"] = interval
    if period is not None:
        timer_data["period"] = period
    if enable is not None:
        timer_data["enable"] = enable

    _LOGGER.debug("Setting timer %s with data: %s", timer_name, timer_data)
    try:
        await coordinator.client.write_timer(timer_name, timer_data)
    except (NeoPoolError, OSError) as err:
        _LOGGER.error(
            "Failed to set timer %s: %s (%s)",
            timer_name,
            err,
            type(err).__name__,
        )
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="timer_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    coordinator.request_refresh_with_followup()


async def _async_write_register(call: ServiceCall) -> None:
    """Write a value to a Modbus holding register."""
    address = parse_register_int(call.data[ATTR_ADDRESS], "address")
    value = parse_register_int(call.data[ATTR_VALUE], "value")
    apply = call.data[ATTR_APPLY]
    coordinator = _get_coordinator(call.hass, call)

    try:
        result = await coordinator.client.async_write_register(
            address, value, apply=apply
        )
    except (NeoPoolError, OSError) as err:
        _LOGGER.error(
            "Failed to write register 0x%04X: %s (%s)",
            address,
            err,
            type(err).__name__,
        )
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="register_write_failed",
            translation_placeholders={
                "address": f"0x{address:04X}",
                "error": str(err),
            },
        ) from err

    if result is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"address": f"0x{address:04X}"},
        )

    confirmed = result.get("confirmed")
    _LOGGER.info(
        "Service write_register: 0x%04X = %s (confirmed: %s, apply: %s)",
        address,
        result.get("value"),
        confirmed,
        apply,
    )
    if confirmed != value:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="write_verification_failed",
            translation_placeholders={
                "address": f"0x{address:04X}",
                "value": str(value),
                "confirmed": str(confirmed),
            },
        )
    coordinator.request_refresh_with_followup()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the NeoPool services (idempotent)."""
    if not hass.services.has_service(DOMAIN, SERVICE_SET_TIMER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_TIMER,
            _async_set_timer,
            schema=SERVICE_SET_TIMER_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_WRITE_REGISTER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_WRITE_REGISTER,
            _async_write_register,
            schema=SERVICE_WRITE_REGISTER_SCHEMA,
        )
