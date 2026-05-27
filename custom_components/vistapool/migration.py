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
from homeassistant.helpers import device_registry as dr
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
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != config_entry.entry_id and entry.unique_id == new_unique_id:
            _LOGGER.error(
                "Migration failed: Device %s is already configured",
                new_unique_id,
            )
            return False

    # Migrate entity unique_ids in registry before bumping version.
    # Use all-or-nothing: collect planned changes, then apply. If any
    # update fails, roll back already-applied changes to avoid a
    # partially-migrated registry.
    entity_registry = er.async_get(hass)
    old_entry_id = config_entry.entry_id
    old_prefix = f"{old_entry_id}_"

    # Build list of (entity_id, old_unique_id, new_unique_id) to migrate
    planned: list[tuple[str, str, str]] = []
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    ):
        if entity_entry.unique_id and entity_entry.unique_id.startswith(old_prefix):
            key_part = entity_entry.unique_id.replace(old_prefix, "", 1)
            planned.append(
                (
                    entity_entry.entity_id,
                    entity_entry.unique_id,
                    f"{new_unique_id}_{key_part}",
                )
            )

    # Apply changes, tracking successful updates for potential rollback
    applied: list[tuple[str, str, str]] = []  # (entity_id, old_uid, new_uid)
    for entity_id, old_uid, new_uid in planned:
        _LOGGER.debug("Migrating entity %s: %s → %s", entity_id, old_uid, new_uid)
        try:
            entity_registry.async_update_entity(entity_id, new_unique_id=new_uid)
            applied.append((entity_id, old_uid, new_uid))
        except Exception as err:
            _LOGGER.error("Failed to migrate entity %s: %s", entity_id, err)
            # Roll back already-applied changes
            rollback_failed = False
            for rb_entity_id, rb_old_uid, _rb_new_uid in applied:
                try:
                    entity_registry.async_update_entity(
                        rb_entity_id, new_unique_id=rb_old_uid
                    )
                except Exception as rb_err:  # noqa: BLE001
                    _LOGGER.error(
                        "Rollback failed for entity %s: %s", rb_entity_id, rb_err
                    )
                    rollback_failed = True
            if rollback_failed:
                _LOGGER.error(
                    "Migration aborted for %s: rollback incomplete — "
                    "integration will not load to prevent duplicates.",
                    config_entry.title,
                )
                return False
            _LOGGER.error(
                "Migration aborted for %s: entity update error. "
                "Will retry on next restart.",
                config_entry.title,
            )
            return True

    # Bump version only after all entities migrated successfully
    hass.config_entries.async_update_entry(
        config_entry, unique_id=new_unique_id, version=2
    )

    # Update old device identifier to serial-based one (preserves area, labels, etc.)
    device_registry = dr.async_get(hass)
    old_device = device_registry.async_get_device(identifiers={(DOMAIN, old_entry_id)})
    if old_device:
        device_registry.async_update_device(
            old_device.id,
            new_identifiers={(DOMAIN, new_unique_id)},
        )
        _LOGGER.debug("Updated device identifier %s → %s", old_entry_id, new_unique_id)

    _LOGGER.info(
        "Migration completed for %s: %d entities migrated, unique_id=%s",
        config_entry.title,
        len(applied),
        new_unique_id,
    )
    return True
