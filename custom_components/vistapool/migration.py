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

"""VistaPool Integration for Home Assistant - Config Entry Migration"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .helpers import async_get_device_serial

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate config entry from v1 (no unique_id) to v2 (serial-based unique_id).

    Old format: entry.unique_id = None
    New format: entry.unique_id = "neopool_{serial}"
    """
    _LOGGER.info(
        "Migrating VistaPool config entry %s from v%s to v2",
        config_entry.entry_id,
        config_entry.version,
    )

    # Trial read to get serial (dict() unwraps MappingProxy for the Modbus client)
    serial = await async_get_device_serial(dict(config_entry.data))
    if not serial:
        _LOGGER.warning(
            "Migration for %s: Cannot read device serial — "
            "device may be offline. Will retry on next restart.",
            config_entry.entry_id,
        )
        # Don't bump version — migration will be retried on next HA startup
        return True

    new_unique_id = f"neopool_{serial}"

    # Check if this serial is already registered (duplicate after migration)
    if serial:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if (
                entry.entry_id != config_entry.entry_id
                and entry.unique_id == new_unique_id
            ):
                _LOGGER.error(
                    "Migration failed: Device %s is already configured",
                    new_unique_id,
                )
                return False

    # Migrate entity unique_ids in registry before bumping version
    entity_registry = er.async_get(hass)
    old_entry_id = config_entry.entry_id
    migrated_count = 0
    failed = False

    for entity_entry in list(
        er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    ):
        # Old format: {entry_id}_{key}
        # New format: {new_unique_id}_{key}
        old_prefix = f"{old_entry_id}_"
        if entity_entry.unique_id and entity_entry.unique_id.startswith(old_prefix):
            key_part = entity_entry.unique_id.replace(old_prefix, "", 1)
            migrated_unique_id = f"{new_unique_id}_{key_part}"

            _LOGGER.debug(
                "Migrating entity %s: %s → %s",
                entity_entry.entity_id,
                entity_entry.unique_id,
                migrated_unique_id,
            )

            try:
                entity_registry.async_update_entity(
                    entity_entry.entity_id,
                    new_unique_id=migrated_unique_id,
                )
                migrated_count += 1
            except Exception as err:
                _LOGGER.error(
                    "Failed to migrate entity %s: %s", entity_entry.entity_id, err
                )
                failed = True

    if failed:
        _LOGGER.error(
            "Migration aborted for %s: entity update errors occurred. "
            "Will retry on next restart.",
            config_entry.title,
        )
        return True

    # Bump version only after all entities migrated successfully
    hass.config_entries.async_update_entry(
        config_entry, unique_id=new_unique_id, version=2
    )

    _LOGGER.info(
        "Migration completed for %s: %d entities migrated, unique_id=%s",
        config_entry.title,
        migrated_count,
        new_unique_id,
    )
    return True
