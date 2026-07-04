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

from neopool_modbus import NeoPoolModbusClient

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import NeoPoolConfigEntry, NeoPoolCoordinator

# Re-exported for Home Assistant, HA discovers async_migrate_entry from __init__.
from .migration import (
    async_cleanup_legacy_files,
    async_migrate_entry,
    cleanup_removed_entities,
)
from .services import async_setup_services

# CUSTOM-ONLY START, re-exports the migration symbol for HA's discovery.
__all__ = ["async_migrate_entry"]
# CUSTOM-ONLY END

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the NeoPool integration."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NeoPoolConfigEntry) -> bool:
    """Set up the NeoPool integration from a config entry."""
    client = NeoPoolModbusClient(entry.data)
    coordinator = NeoPoolCoordinator(hass, client, entry, entry.entry_id)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # CUSTOM-ONLY START
    cleanup_removed_entities(hass, entry)
    # CUSTOM-ONLY END

    # CUSTOM-ONLY START, HACS does not prune deleted files on upgrade,
    # so we sweep modules whose implementation moved to neopool-modbus.
    await async_cleanup_legacy_files(hass)
    # CUSTOM-ONLY END

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NeoPoolConfigEntry) -> bool:
    """Unload a NeoPool config entry."""
    coordinator = entry.runtime_data
    coordinator.cancel_follow_up_refresh()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and coordinator.client is not None:
        await coordinator.client.close()
    return unload_ok
