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

"""Light platform for the NeoPool integration."""

import logging
from typing import Any

from neopool_modbus.registers import EXEC_REGISTER, TimerRelayMode, is_valid_relay_gpio

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NeoPoolConfigEntry
from .const import LIGHT_DEFINITIONS
from .coordinator import NeoPoolCoordinator
from .entity import NeoPoolEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool lights from a config entry."""
    coordinator = entry.runtime_data
    entry_id = entry.entry_id

    entities = []

    for key, props in LIGHT_DEFINITIONS.items():
        option_key = props.get("option")
        if option_key and not entry.options.get(option_key, False):
            continue
        if "MBF_PAR_LIGHTING_GPIO" in coordinator.data and not is_valid_relay_gpio(
            coordinator.data["MBF_PAR_LIGHTING_GPIO"] or 0
        ):
            continue

        entities.append(NeoPoolLight(coordinator, entry_id, key, props))

    async_add_entities(entities)


class NeoPoolLight(NeoPoolEntity, LightEntity):
    """Representation of a NeoPool light entity."""

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        props: dict[str, Any],
    ) -> None:
        """Initialize the NeoPool light entity."""
        super().__init__(coordinator, entry_id)
        self._key = key
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{self._key.lower()}"
        self._attr_translation_key = NeoPoolEntity.slugify(self._key)

        self._switch_type = props.get("switch_type") or None

        self.timer_block_addr: int | None = props.get("timer_block_addr")
        self.function_addr: int | None = props.get("function_addr")
        self.function_code: int | None = props.get("function_code")

    async def async_added_to_hass(self) -> None:
        """Run when the entity is added to hass."""
        _LOGGER.debug(
            "ADDED: entity_id=%s, translation_key=%s, has_entity_name=%s",
            self.entity_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )
        await super().async_added_to_hass()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light ON."""
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active — ignoring turn_on for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers")
            return
        if self._switch_type == "relay_timer":
            if (
                self.function_addr is None
                or self.function_code is None
                or self.timer_block_addr is None
            ):  # pragma: no cover
                _LOGGER.error("Missing relay_timer config for %s", self._key)
                return
            _LOGGER.debug(
                "Turning ON %s: function_addr=0x%04X, timer_block_addr=0x%04X",
                self._key,
                self.function_addr,
                self.timer_block_addr,
            )
            await client.async_write_register(
                self.function_addr, self.function_code
            )  # Set function (if needed)
            await client.async_write_register(
                self.timer_block_addr, TimerRelayMode.ALWAYS_ON
            )
            await client.async_write_register(EXEC_REGISTER, 1)  # Commit

        # Optimistic update + schedule follow-up
        self._optimistic_update(True)
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light OFF."""
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active — ignoring turn_off for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers")
            return
        if self._switch_type == "relay_timer":
            if self.timer_block_addr is None:  # pragma: no cover
                _LOGGER.error("Missing timer_block_addr for %s", self._key)
                return
            _LOGGER.debug(
                "Turning OFF %s: timer_block_addr=0x%04X",
                self._key,
                self.timer_block_addr,
            )
            await client.async_write_register(
                self.timer_block_addr, TimerRelayMode.ALWAYS_OFF
            )
            await client.async_write_register(EXEC_REGISTER, 1)  # Commit

        # Optimistic update + schedule follow-up
        self._optimistic_update(False)
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    def _optimistic_update(self, state: bool) -> None:
        """Apply an optimistic state update to coordinator data."""
        data = self.coordinator.data
        if self._switch_type == "relay_timer":
            data["relay_light_enable"] = (
                TimerRelayMode.ALWAYS_ON if state else TimerRelayMode.ALWAYS_OFF
            )

    @property
    def is_on(self) -> bool:
        """Return True if the light is ON."""
        if self._switch_type == "relay_timer":
            enable_val = self.coordinator.data.get("relay_light_enable", None)
            return enable_val == TimerRelayMode.ALWAYS_ON
        return False  # pragma: no cover

    @property
    def available(self) -> bool:
        """Return True if the light is available."""
        if not super().available:
            return False
        if self._switch_type == "relay_timer":
            mode_val = self.coordinator.data.get("relay_light_enable", None)
            return mode_val in (0, TimerRelayMode.ALWAYS_ON, TimerRelayMode.ALWAYS_OFF)
        return True  # pragma: no cover

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return the color modes supported by this light."""
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        """Return the current color mode of the light."""
        return ColorMode.ONOFF
