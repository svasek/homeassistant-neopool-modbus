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

"""VistaPool Integration for Home Assistant - Light Module"""

import logging

from homeassistant.components.light import LightEntity
from homeassistant.components.light.const import ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, EXEC_REGISTER, LIGHT_DEFINITIONS, is_valid_relay_gpio
from .entity import VistaPoolEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up VistaPool lights from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entry_id = entry.entry_id

    entities = []

    if coordinator.data is None:
        _LOGGER.warning("No data from Modbus, skipping light setup!")
        return

    for key, props in LIGHT_DEFINITIONS.items():
        # Only create light if enabled in options
        option_key = props.get("option")
        if option_key and not entry.options.get(option_key, False):
            continue
        # Skip if lighting relay is not assigned.
        # Only enforce when the GPIO key is present in data; a missing key
        # (e.g. old capability snapshot) must not suppress the entity.
        if "MBF_PAR_LIGHTING_GPIO" in coordinator.data and not is_valid_relay_gpio(
            coordinator.data["MBF_PAR_LIGHTING_GPIO"] or 0
        ):
            continue

        entities.append(VistaPoolLight(coordinator, entry_id, key, props))

    async_add_entities(entities)


class VistaPoolLight(VistaPoolEntity, LightEntity):  # type: ignore[reportIncompatibleVariableOverride]
    """Representation of a VistaPool light entity."""

    def __init__(self, coordinator, entry_id, key, props) -> None:
        """Initialize the VistaPool light entity."""
        super().__init__(coordinator, entry_id)
        self._key = key
        self._attr_suggested_object_id = (
            f"{self.coordinator.device_slug}_{VistaPoolEntity.slugify(self._key)}"
        )
        self._attr_unique_id = f"{self._entry_id}_{self._key.lower()}"
        self._attr_translation_key = VistaPoolEntity.slugify(self._key)

        self._switch_type = props.get("switch_type") or None
        self._attr_icon = props.get("icon") or None
        self._icon_on = props.get("icon_on")
        self._icon_off = props.get("icon_off")

        # Initialize properties for relay timer switches
        self.timer_block_addr: int | None = props.get("timer_block_addr")
        self.function_addr: int | None = props.get("function_addr")
        self.function_code: int | None = props.get("function_code")

        _LOGGER.debug(
            "INIT: suggested_object_id=%s, translation_key=%s, has_entity_name=%s",
            self._attr_suggested_object_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light ON."""
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active — ignoring turn_on for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:
            _LOGGER.error("Modbus client not available for writing registers.")
            return
        if self._switch_type == "relay_timer":
            if (
                self.function_addr is None
                or self.function_code is None
                or self.timer_block_addr is None
            ):
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
            await client.async_write_register(self.timer_block_addr, 3)  # Always ON
            await client.async_write_register(EXEC_REGISTER, 1)  # Commit

        # Optimistic update + schedule follow-up
        self._optimistic_update(True)
        if self.coordinator.data is not None:
            self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light OFF."""
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active — ignoring turn_off for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:
            _LOGGER.error("Modbus client not available for writing registers.")
            return
        if self._switch_type == "relay_timer":
            if self.timer_block_addr is None:
                _LOGGER.error("Missing timer_block_addr for %s", self._key)
                return
            _LOGGER.debug(
                "Turning OFF %s: timer_block_addr=0x%04X",
                self._key,
                self.timer_block_addr,
            )
            await client.async_write_register(self.timer_block_addr, 4)  # Always OFF
            await client.async_write_register(EXEC_REGISTER, 1)  # Commit

        # Optimistic update + schedule follow-up
        self._optimistic_update(False)
        if self.coordinator.data is not None:
            self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    def _optimistic_update(self, state: bool) -> None:
        """Apply an optimistic state update to coordinator data."""
        data = self.coordinator.data
        if data is None:
            return
        if self._switch_type == "relay_timer":
            data["relay_light_enable"] = 3 if state else 4

    async def async_added_to_hass(self) -> None:
        """Run when the entity is added to hass."""
        _LOGGER.debug(
            "ADDED: entity_id=%s, translation_key=%s, has_entity_name=%s",
            self.entity_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )
        await super().async_added_to_hass()

    @property
    def is_on(self) -> bool:  # type: ignore[override]
        """Return True if the light is ON."""
        if self._switch_type == "relay_timer":
            enable_val = self.coordinator.data.get("relay_light_enable", None)
            return enable_val == 3  # ON if ALWAYS ON
        return False

    @property
    def available(self) -> bool:  # type: ignore[override]
        """Return True if the light is available."""
        if not super().available:
            return False
        if self._switch_type == "relay_timer":
            mode_val = self.coordinator.data.get("relay_light_enable", None)
            return mode_val in (0, 3, 4)
        return True

    @property
    def icon(self) -> str | None:  # type: ignore[override]
        """Return custom icon depending on state."""
        if self._icon_on and self._icon_off:
            return self._icon_on if self.is_on else self._icon_off
        if self._attr_icon:
            return self._attr_icon
        return None

    @property
    def supported_color_modes(self) -> set[str]:  # type: ignore[override]
        """Return the color modes supported by this light."""
        # For simple on/off light, the correct mode is COLOR_MODE_ONOFF (or ColorMode.ONOFF)
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> str:  # type: ignore[override]
        """Return the current color mode of the light."""
        # Actual mode is always onoff, as brightness and color are not available
        return ColorMode.ONOFF
