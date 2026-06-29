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

"""Button platform for the NeoPool integration."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import logging
from typing import Any, override

from neopool_modbus.capabilities import has_filtvalve

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NeoPoolConfigEntry
from .coordinator import NeoPoolCoordinator
from .entity import NeoPoolEntity
from .helpers import prepare_device_time

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

type SupportedFn = Callable[[dict[str, Any], Mapping[str, Any]], bool]


@dataclass(frozen=True, kw_only=True)
class NeoPoolButtonEntityDescription(ButtonEntityDescription):
    """Describes a NeoPool button entity."""

    supported_fn: SupportedFn | None = None


BUTTON_DESCRIPTIONS: dict[str, NeoPoolButtonEntityDescription] = {
    "SYNC_TIME": NeoPoolButtonEntityDescription(
        key="SYNC_TIME",
        entity_category=EntityCategory.CONFIG,
    ),
    "MBF_ESCAPE": NeoPoolButtonEntityDescription(
        key="MBF_ESCAPE",
        entity_category=EntityCategory.CONFIG,
    ),
    "BACKWASH": NeoPoolButtonEntityDescription(
        key="BACKWASH",
        supported_fn=lambda data, opts: has_filtvalve(data),
    ),
    "RESET_CELL_PARTIAL": NeoPoolButtonEntityDescription(
        key="RESET_CELL_PARTIAL",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool button entities from a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        NeoPoolButton(coordinator, entry.entry_id, key, desc)
        for key, desc in BUTTON_DESCRIPTIONS.items()
        if desc.supported_fn is None
        or desc.supported_fn(coordinator.data, entry.options)
    )


class NeoPoolButton(NeoPoolEntity, ButtonEntity):
    """Representation of a NeoPool button entity."""

    entity_description: NeoPoolButtonEntityDescription

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        description: NeoPoolButtonEntityDescription,
    ) -> None:
        """Initialize the NeoPool button entity."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._key = key
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{key.lower()}"
        self._attr_translation_key = NeoPoolEntity.slugify(key)

    @override
    async def async_added_to_hass(self) -> None:
        """Run when the entity is added to hass."""
        _LOGGER.debug(
            "ADDED: entity_id=%s, translation_key=%s, has_entity_name=%s",
            self.entity_id,
            self.translation_key,
            getattr(self, "has_entity_name", None),
        )
        await super().async_added_to_hass()

    @override
    async def async_press(self) -> None:
        """Perform button action depending on key."""
        if self.coordinator.winter_mode:
            _LOGGER.warning("Winter mode is active, ignoring press for %s", self._key)
            return
        client = self.coordinator.client
        if self._key == "SYNC_TIME":
            _LOGGER.debug("Syncing time with device")
            await client.async_sync_device_time(prepare_device_time(self.hass))
        elif self._key == "MBF_ESCAPE":
            _LOGGER.debug("Clearing all possible errors")
            await client.async_clear_errors()
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
            _LOGGER.info(
                "Starting backwash on device '%s'", self.coordinator.device_name
            )
            await client.async_set_filtration_mode("backwash")
        elif self._key == "RESET_CELL_PARTIAL":
            _LOGGER.info(
                "Resetting partial cell runtime counter on device '%s'",
                self.coordinator.device_name,
            )
            await client.async_reset_user_counters()
        await self.coordinator.async_request_refresh()
