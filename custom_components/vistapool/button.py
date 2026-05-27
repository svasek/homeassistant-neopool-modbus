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

"""VistaPool Integration for Home Assistant - Button Module"""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VistaPoolConfigEntry
from .const import BUTTON_DEFINITIONS
from .entity import VistaPoolEntity
from .helpers import has_filtvalve, prepare_device_time

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VistaPool button entities from a config entry."""
    coordinator = entry.runtime_data
    entry_id = entry.entry_id

    entities = []

    if coordinator.data is None:
        _LOGGER.warning("No data from Modbus, skipping button setup!")
        return

    for key, props in BUTTON_DEFINITIONS.items():
        # BACKWASH button is only available when a Besgo filter valve is configured
        if key == "BACKWASH" and not has_filtvalve(coordinator.data):
            continue
        entities.append(VistaPoolButton(coordinator, entry_id, key, props))
    async_add_entities(entities)


class VistaPoolButton(VistaPoolEntity, ButtonEntity):  # type: ignore[reportIncompatibleVariableOverride]
    """Representation of a VistaPool button entity."""

    def __init__(self, coordinator, entry_id, key, props) -> None:
        """Initialize the VistaPool button entity."""
        super().__init__(coordinator, entry_id)
        self._key = key
        self._attr_suggested_object_id = (
            f"{self.coordinator.device_slug}_{VistaPoolEntity.slugify(self._key)}"
        )
        # Use entry.unique_id (serial-based in v2+) for stable identity, fallback to entry_id
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{self._key.lower()}"
        self._attr_translation_key = VistaPoolEntity.slugify(self._key)

        self._attr_entity_category = props.get("entity_category") or None
        self._attr_icon = props.get("icon") or "mdi:button-pointer"

        _LOGGER.debug(
            "INIT: suggested_object_id=%s, translation_key=%s, has_entity_name=%s",
            self._attr_suggested_object_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )

    async def async_press(self) -> None:
        """Perform button action depending on key."""
        if self.coordinator.winter_mode:
            _LOGGER.warning("Winter mode is active — ignoring press for %s", self._key)
            return
        if self._key == "SYNC_TIME":
            client = self.coordinator.client
            _LOGGER.debug("Syncing time with device...")
            await client.async_write_register(0x0408, prepare_device_time(self.hass))
            await client.async_write_register(0x04F0, 1)
            await self.coordinator.async_request_refresh()
        elif self._key == "MBF_ESCAPE":
            client = self.coordinator.client
            _LOGGER.debug("Clearing all possible errors...")
            await client.async_write_register(0x0297, 1)
            await self.coordinator.async_request_refresh()
        elif self._key == "BACKWASH":
            if not has_filtvalve(self.coordinator.data):
                _LOGGER.warning(
                    "Backwash valve not configured "
                    "(MBF_PAR_FILTVALVE_ENABLE=%r, MBF_PAR_FILTVALVE_GPIO=%r) "
                    "- ignoring backwash command for %s",
                    self.coordinator.data.get("MBF_PAR_FILTVALVE_ENABLE"),
                    self.coordinator.data.get("MBF_PAR_FILTVALVE_GPIO"),
                    self.coordinator.device_name,
                )
                return
            client = self.coordinator.client
            _LOGGER.info(
                "Starting backwash on device '%s'", self.coordinator.device_name
            )
            # Set filtration mode to backwash (13 = MBV_PAR_FILT_BACKWASH).
            # The device opens the configured Besgo valve and runs the filter
            # cleaning cycle for the duration stored in MBF_PAR_FILTVALVE_INTERVAL.
            await client.async_write_register(0x0411, 13)
            await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:  # pragma: no cover
        """Run when the entity is added to hass."""
        _LOGGER.debug(
            "ADDED: entity_id=%s, translation_key=%s, has_entity_name=%s",
            self.entity_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )
        await super().async_added_to_hass()

    @property
    def icon(self) -> str | None:  # type: ignore[override]
        """Return the icon for the button."""
        return self._attr_icon
