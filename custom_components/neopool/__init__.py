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

"""NeoPool integration for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from neopool_modbus import NeoPoolModbusClient

from .const import DOMAIN, PLATFORMS, REMOVED_ENTITY_KEYS
from .coordinator import NeoPoolCoordinator

# Re-exported for Home Assistant — HA calls async_migrate_entry(hass, entry)
# from the integration's __init__ module when config entry version changes.
from .migration import async_cleanup_legacy_files, async_migrate_entry
from .services import (
    SERVICE_SET_TIMER,
    SERVICE_WRITE_REGISTER,
    async_setup_services,
)

__all__ = ["async_migrate_entry"]

type NeoPoolConfigEntry = ConfigEntry[NeoPoolCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


def _cleanup_removed_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove orphaned entity-registry entries for entities no longer in definitions."""
    registry = er.async_get(hass)
    # Match both old ({entry_id}_{key}) and new ({unique_id}_{key}) unique_id formats
    prefixes = {entry.entry_id}
    if entry.unique_id:
        prefixes.add(entry.unique_id)
    removed_uids = {
        f"{prefix}_{key}" for prefix in prefixes for key in REMOVED_ENTITY_KEYS
    }
    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity_entry.unique_id in removed_uids:
            _LOGGER.debug(
                "Removing orphaned entity %s (unique_id=%s)",
                entity_entry.entity_id,
                entity_entry.unique_id,
            )
            registry.async_remove(entity_entry.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: NeoPoolConfigEntry) -> bool:
    """Set up the NeoPool integration."""
    # --- MIGRATE CONFIG FLOW DATA TO OPTIONS IF NEEDED ---
    # Copy all keys except connection settings from data to options
    connection_keys = [CONF_HOST, CONF_PORT, CONF_NAME, "slave_id"]
    candidate_keys = [k for k in entry.data if k not in connection_keys]
    if not entry.options or not any(k in entry.options for k in candidate_keys):
        new_options = {k: entry.data[k] for k in candidate_keys}
        if new_options:  # pragma: no cover
            _LOGGER.debug(
                "NeoPool: Migrating ALL config entry data (except connection params) to options: %s",
                new_options,
            )
            hass.config_entries.async_update_entry(entry, options=new_options)
    # --- End migration ---

    # Initialize Modbus client and coordinator
    client = NeoPoolModbusClient(entry.data)
    coordinator = NeoPoolCoordinator(hass, client, entry, entry.entry_id)

    # Wait for the first update from the coordinator
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator as runtime_data for easy access
    entry.runtime_data = coordinator

    # Remove orphaned entity-registry entries for sensors that no longer exist
    _cleanup_removed_entities(hass, entry)

    # Remove .py modules whose implementation moved to the neopool-modbus
    # PyPI library; HACS does not prune deleted files on upgrade.
    await async_cleanup_legacy_files(hass)

    # Forward entities setup to Home Assistant
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (idempotent — each service is registered only if missing)
    async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NeoPoolConfigEntry) -> bool:
    """Unload a NeoPool config entry."""
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None:
        coordinator.cancel_follow_up_refresh()
        if getattr(coordinator, "client", None):
            await coordinator.client.close()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Cleanup services when no other loaded entry remains
        remaining = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id and e.state == ConfigEntryState.LOADED
        ]
        if not remaining:
            if hass.services.has_service(DOMAIN, SERVICE_SET_TIMER):
                hass.services.async_remove(DOMAIN, SERVICE_SET_TIMER)
            if hass.services.has_service(DOMAIN, SERVICE_WRITE_REGISTER):
                hass.services.async_remove(DOMAIN, SERVICE_WRITE_REGISTER)
    return unload_ok
