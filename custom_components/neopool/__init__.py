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

from neopool_modbus import NeoPoolModbusClient

from homeassistant.config_entries import ConfigEntry

# CUSTOM-ONLY START — these constants are only referenced by the
# legacy data→options migration block in async_setup_entry below.
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT

# CUSTOM-ONLY END
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS, REMOVED_ENTITY_KEYS
from .coordinator import NeoPoolCoordinator

# Re-exported for Home Assistant — HA discovers async_migrate_entry from __init__.
from .migration import async_cleanup_legacy_files, async_migrate_entry
from .services import async_setup_services

# CUSTOM-ONLY START — re-exports the migration symbol for HA's discovery.
__all__ = ["async_migrate_entry"]
# CUSTOM-ONLY END

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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the NeoPool integration."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NeoPoolConfigEntry) -> bool:
    """Set up the NeoPool integration from a config entry."""
    # CUSTOM-ONLY START — historic config flow stored options inside `data`;
    # the core integration writes options correctly from day one.
    connection_keys = [CONF_HOST, CONF_PORT, CONF_NAME, "unit_id"]
    candidate_keys = [k for k in entry.data if k not in connection_keys]
    if not entry.options or not any(k in entry.options for k in candidate_keys):
        new_options = {k: entry.data[k] for k in candidate_keys}
        if new_options:  # pragma: no cover
            _LOGGER.debug(
                "NeoPool: Migrating ALL config entry data (except connection params) to options: %s",
                new_options,
            )
            hass.config_entries.async_update_entry(entry, options=new_options)
    # CUSTOM-ONLY END

    client = NeoPoolModbusClient(entry.data)
    coordinator = NeoPoolCoordinator(hass, client, entry, entry.entry_id)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _cleanup_removed_entities(hass, entry)

    # CUSTOM-ONLY START — HACS does not prune deleted files on upgrade,
    # so we sweep modules whose implementation moved to neopool-modbus.
    await async_cleanup_legacy_files(hass)
    # CUSTOM-ONLY END

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NeoPoolConfigEntry) -> bool:
    """Unload a NeoPool config entry."""
    coordinator = entry.runtime_data
    coordinator.cancel_follow_up_refresh()
    if coordinator.client is not None:
        await coordinator.client.close()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
