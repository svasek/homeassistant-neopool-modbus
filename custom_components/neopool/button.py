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

"""NeoPool Integration for Home Assistant - Button Module"""

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import NeoPoolConfigEntry
from .const import BUTTON_DEFINITIONS, FOLLOW_UP_REFRESH_DELAY
from .coordinator import NeoPoolCoordinator
from .entity import NeoPoolEntity
from .helpers import has_filtvalve, prepare_device_time

_LOGGER = logging.getLogger(__name__)

_BACKWASH_DIAG_KEYS = (
    "MBF_PAR_FILT_MODE",
    "MBF_PAR_FILT_MANUAL_STATE",
    "MBF_PAR_FILTRATION_STATE",
    "MBF_PAR_FILTVALVE_ENABLE",
    "MBF_PAR_FILTVALVE_MODE",
    "MBF_PAR_FILTVALVE_GPIO",
    "MBF_PAR_FILTVALVE_INTERVAL",
    "MBF_PAR_FILTVALVE_REMAINING",
)


def _log_backwash_state(label: str, data: dict) -> None:
    """Log backwash-related register values for diagnostics."""
    parts = ", ".join(f"{k}={data.get(k)!r}" for k in _BACKWASH_DIAG_KEYS)
    _LOGGER.info("Backwash %s: %s", label, parts)


PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NeoPool button entities from a config entry."""
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
        entities.append(NeoPoolButton(coordinator, entry_id, key, props))
    async_add_entities(entities)


class NeoPoolButton(NeoPoolEntity, ButtonEntity):  # type: ignore[reportIncompatibleVariableOverride]
    """Representation of a NeoPool button entity."""

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        props: dict[str, Any],
    ) -> None:
        """Initialize the NeoPool button entity."""
        super().__init__(coordinator, entry_id)
        self._key = key
        self._attr_suggested_object_id = (
            f"{self.coordinator.device_slug}_{NeoPoolEntity.slugify(self._key)}"
        )
        # Use entry.unique_id (serial-based in v2+) for stable identity, fallback to entry_id
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{self._key.lower()}"
        self._attr_translation_key = NeoPoolEntity.slugify(self._key)

        self._attr_entity_category = props.get("entity_category") or None

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
            # Log current state of all relevant registers for diagnostics
            _log_backwash_state("pre-write state", self.coordinator.data or {})
            # Set MBF_PAR_FILT_MODE = 13 (backwash).
            # The device manages the Besgo valve cleaning cycle internally
            # for the duration stored in MBF_PAR_FILTVALVE_INTERVAL.
            await client.async_write_register(0x0411, 13)
            await self.coordinator.async_request_refresh()
            self.coordinator.request_refresh_with_followup()

            # Schedule a diagnostic log after the follow-up refresh completes
            # to capture whether the device accepted or reverted the mode change.
            coordinator = self.coordinator
            log_delay = FOLLOW_UP_REFRESH_DELAY + 3.0

            @callback
            def _log_post_backwash_state(_now: Any) -> None:
                _log_backwash_state(
                    f"post-write state (after ~{log_delay:.0f}s)",
                    coordinator.data or {},
                )

            async_call_later(self.hass, log_delay, _log_post_backwash_state)

    async def async_added_to_hass(self) -> None:  # pragma: no cover
        """Run when the entity is added to hass."""
        _LOGGER.debug(
            "ADDED: entity_id=%s, translation_key=%s, has_entity_name=%s",
            self.entity_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )
        await super().async_added_to_hass()
