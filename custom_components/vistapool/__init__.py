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

"""VistaPool Integration for Home Assistant"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS, REMOVED_ENTITY_KEYS, TIMER_BLOCKS
from .coordinator import VistaPoolCoordinator
from .helpers import modbus_regs_to_hex_string
from .migration import async_migrate_entry  # noqa: F401
from .modbus import VistaPoolModbusClient

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


def _cleanup_removed_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove orphaned entity-registry entries for entities no longer in definitions."""
    registry = er.async_get(hass)
    removed_uids = {f"{entry.entry_id}_{key}" for key in REMOVED_ENTITY_KEYS}
    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity_entry.unique_id in removed_uids:
            _LOGGER.debug(
                "Removing orphaned entity %s (unique_id=%s)",
                entity_entry.entity_id,
                entity_entry.unique_id,
            )
            registry.async_remove(entity_entry.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the VistaPool integration."""

    # --- MIGRATE CONFIG FLOW DATA TO OPTIONS IF NEEDED ---
    # Copy all keys except connection settings from data to options
    connection_keys = [CONF_HOST, CONF_PORT, CONF_NAME, "slave_id"]
    candidate_keys = [k for k in entry.data if k not in connection_keys]
    if not entry.options or not any(k in entry.options for k in candidate_keys):
        new_options = {k: entry.data[k] for k in candidate_keys}
        if new_options:  # pragma: no cover
            _LOGGER.debug(
                "VistaPool: Migrating ALL config entry data (except connection params) to options: %s",
                new_options,
            )
            hass.config_entries.async_update_entry(entry, options=new_options)
    # --- End migration ---

    # Initialize Modbus client and coordinator
    client = VistaPoolModbusClient(entry.data)
    coordinator = VistaPoolCoordinator(hass, client, entry, entry.entry_id)

    # Wait for the first update from the coordinator
    await coordinator.async_config_entry_first_refresh()

    # Fallback: Ensure entry has unique_id set (for backward compatibility with v1 entries)
    if not entry.unique_id and coordinator.data:
        serial = modbus_regs_to_hex_string(
            coordinator.data.get("MBF_POWER_MODULE_NODEID")
        )
        if serial:
            unique_id = f"neopool_{serial}"
            _LOGGER.debug(
                "Assigning unique_id to entry %s: %s (backward compatibility)",
                entry.entry_id,
                unique_id,
            )
            hass.config_entries.async_update_entry(entry, unique_id=unique_id)

    # Store the coordinator and client in hass.data for easy access
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Remove orphaned entity-registry entries for sensors that no longer exist
    _cleanup_removed_entities(hass, entry)

    # Forward entities setup to Home Assistant
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (idempotent — each service is registered only if missing)
    _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a VistaPool config entry."""
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator:
        coordinator.cancel_follow_up_refresh()
        if getattr(coordinator, "client", None):
            await coordinator.client.close()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        # Cleanup services when last entry is removed
        if not hass.data[DOMAIN]:
            if hass.services.has_service(DOMAIN, "set_timer"):
                hass.services.async_remove(DOMAIN, "set_timer")
            if hass.services.has_service(DOMAIN, "write_register"):
                hass.services.async_remove(DOMAIN, "write_register")
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    """Register VistaPool services."""
    from .helpers import get_timer_interval, hhmm_to_seconds, parse_register_int

    def _get_coordinator(call):
        """Resolve coordinator from service call data."""
        entries = hass.data.get(DOMAIN, {})
        entry_id = call.data.get("entry_id")
        if not entry_id:
            entry_id = next(iter(entries), None)
        if not entry_id:
            raise ServiceValidationError("No entry_id found for VistaPool service call")
        coordinator = entries.get(entry_id)
        if not coordinator:
            raise ServiceValidationError(
                f"No VistaPool coordinator found for entry_id '{entry_id}'"
            )
        return coordinator

    async def async_handle_set_timer(call) -> None:
        """Handle the set_timer service call."""
        try:
            timer_name = call.data["timer"]
        except KeyError:
            raise ServiceValidationError("Missing required parameter 'timer'")

        if timer_name not in TIMER_BLOCKS:
            raise ServiceValidationError(
                f"Invalid timer name '{timer_name}'. "
                f"Valid timers: {', '.join(sorted(TIMER_BLOCKS))}"
            )

        try:
            start = call.data.get("start")
            stop = call.data.get("stop")
            enable = call.data.get("enable")
            period = call.data.get("period")
            coordinator = _get_coordinator(call)
            # Convert start and stop times to seconds
            start_sec = hhmm_to_seconds(start) if start else None
            stop_sec = hhmm_to_seconds(stop) if stop else None
            interval = (
                get_timer_interval(start_sec, stop_sec) if (start and stop) else None
            )

            # Prepare the timer data as a dictionary
            timer_data = {}
            if start_sec is not None:
                timer_data["on"] = start_sec
            if interval is not None:
                timer_data["interval"] = interval
            if period is not None:
                timer_data["period"] = int(period)
            if enable is not None:
                timer_data["enable"] = enable

            _LOGGER.debug("Setting timer %s with data: %s", timer_name, timer_data)
            await coordinator.client.write_timer(timer_name, timer_data)
            coordinator.request_refresh_with_followup()
        except ServiceValidationError:
            raise
        except Exception as e:
            _LOGGER.error(
                "Failed to set timer %s: %s", call.data.get("timer", "unknown"), e
            )
            raise ServiceValidationError(f"Timer setting failed: {e}") from e

    async def async_handle_write_register(call) -> None:
        """Handle the write_register service call."""
        try:
            raw_address = call.data["address"]
            raw_value = call.data["value"]
        except KeyError as exc:
            raise ServiceValidationError(f"Missing required parameter '{exc.args[0]}'")

        address = parse_register_int(raw_address, "address")
        value = parse_register_int(raw_value, "value")
        apply = call.data.get("apply", True)
        if not isinstance(apply, bool):
            raise ServiceValidationError(
                f"Invalid apply '{apply}': must be a boolean (true/false)"
            )
        coordinator = _get_coordinator(call)

        try:
            result = await coordinator.client.async_write_register(
                address, value, apply=apply
            )
            if result is None:
                raise ServiceValidationError(
                    f"Write to register 0x{address:04X} failed"
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
                    f"Write verification failed at 0x{address:04X}: "
                    f"wrote {value}, read back {confirmed}"
                )
            coordinator.request_refresh_with_followup()
        except ServiceValidationError:
            raise
        except Exception as e:
            _LOGGER.error("Failed to write register 0x%04X: %s", address, e)
            raise ServiceValidationError(
                f"Register write failed at 0x{address:04X}: {e}"
            ) from e

    if not hass.services.has_service(DOMAIN, "set_timer"):
        hass.services.async_register(DOMAIN, "set_timer", async_handle_set_timer)
    if not hass.services.has_service(DOMAIN, "write_register"):
        hass.services.async_register(
            DOMAIN, "write_register", async_handle_write_register
        )
