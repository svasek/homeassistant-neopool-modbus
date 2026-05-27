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

"""VistaPool Integration for Home Assistant - Switch Module"""

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VistaPoolConfigEntry
from .const import (
    EXEC_REGISTER,
    MANUAL_FILTRATION_REGISTER,
    SWITCH_DEFINITIONS,
    is_valid_relay_gpio,
)
from .entity import VistaPoolEntity

_LOGGER = logging.getLogger(__name__)


def _should_skip_switch(
    key: str,
    props: dict[str, Any],
    data: dict[str, Any],
    entry_options: Mapping[str, Any],
) -> bool:
    """Return True if a switch entity should not be created."""
    # Only create relay switches if enabled in options
    option_key = props.get("option")
    if option_key and not entry_options.get(option_key, False):
        return True
    # Conditionally add clima mode only if heating relay is assigned
    if key == "MBF_PAR_CLIMA_ONOFF":
        if not bool(data.get("MBF_PAR_HEATING_GPIO")) or not bool(
            data.get("MBF_PAR_TEMPERATURE_ACTIVE")
        ):
            return True
    # Skip smart antifreeze if temperature sensor not active
    if key == "MBF_PAR_SMART_ANTI_FREEZE":
        if not bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE")):
            return True
    # Hydro cover-reduction switch only when hydrolysis module present
    if key == "MBF_PAR_HIDRO_COVER_ENABLE":
        if not data.get("Hydrolysis module detected"):
            return True
    # Hydro temp-shutdown switch needs hydrolysis and temperature sensor
    if key == "MBF_PAR_HIDRO_TEMP_SHUTDOWN":
        if not data.get("Hydrolysis module detected") or not bool(
            data.get("MBF_PAR_TEMPERATURE_ACTIVE")
        ):
            return True
    # UV mode switch only when UV relay is assigned
    if key == "MBF_PAR_UV_MODE":
        uv_gpio = data.get("MBF_PAR_UV_RELAY_GPIO", 0) or 0
        if not is_valid_relay_gpio(uv_gpio):
            return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VistaPool switches from a config entry."""
    coordinator = entry.runtime_data
    entry_id = entry.entry_id

    entities = []

    if coordinator.data is None:
        _LOGGER.warning("No data from Modbus, skipping switch setup!")
        return

    for key, props in SWITCH_DEFINITIONS.items():
        if _should_skip_switch(key, props, coordinator.data, entry.options):
            continue

        entities.append(VistaPoolSwitch(coordinator, entry_id, key, props))

    async_add_entities(entities)


class VistaPoolSwitch(VistaPoolEntity, SwitchEntity):  # type: ignore[reportIncompatibleVariableOverride]
    """Representation of a VistaPool switch entity."""

    def __init__(self, coordinator, entry_id, key, props) -> None:
        """Initialize the VistaPool switch entity."""
        super().__init__(coordinator, entry_id)
        self._key = key
        self._attr_suggested_object_id = (
            f"{self.coordinator.device_slug}_{VistaPoolEntity.slugify(self._key)}"
        )
        # Use entry.unique_id (serial-based in v2+) for stable identity, fallback to entry_id
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{self._key.lower()}"
        self._attr_translation_key = VistaPoolEntity.slugify(self._key)

        self._switch_type = props.get("switch_type") or None
        self._relay_index = props.get("relay_index") or None

        # The winter_mode switch itself must remain available while winter mode is on
        if self._switch_type == "winter_mode":
            self._winter_mode_active = False

        self._attr_entity_category = props.get("entity_category") or None
        self._icon_on = props.get("icon_on")
        self._icon_off = props.get("icon_off")
        self._attr_icon = props.get("icon") or None

        # Initialize properties for relay timer switches
        self.timer_block_addr: int | None = props.get("timer_block_addr")
        self.function_addr: int | None = props.get("function_addr")
        self.function_code: int | None = props.get("function_code")

        # Initialize properties for bitmask switches
        self._mask_bit: int | None = props.get("mask_bit")
        self._data_key = props.get("data_key") or self._key

        _LOGGER.debug(
            "INIT: suggested_object_id=%s, translation_key=%s, has_entity_name=%s",
            self._attr_suggested_object_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch ON."""
        if (
            self._switch_type not in ("winter_mode", "auto_time_sync")
            and self.coordinator.winter_mode
        ):
            _LOGGER.warning(
                "Winter mode is active — ignoring turn_on for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers.")
            return
        if self._switch_type == "manual_filtration":
            await client.async_write_register(MANUAL_FILTRATION_REGISTER, 1)
        elif self._switch_type == "aux":
            _LOGGER.debug(
                "Turning ON %s (relay index %s)", self._key, self._relay_index
            )
            await client.async_write_aux_relay(self._relay_index, True)
        elif self._switch_type == "auto_time_sync":
            await self.coordinator.set_auto_time_sync(True)
        elif self._switch_type == "winter_mode":
            await self.coordinator.set_winter_mode(True)
        elif self._switch_type == "relay_timer":
            if (
                self.function_addr is None
                or self.function_code is None
                or self.timer_block_addr is None
            ):
                _LOGGER.error("Missing relay_timer config for %s", self._key)
                return
            _LOGGER.debug(
                "Turning ON relay %s: function_addr=0x%04X, timer_block_addr=0x%04X",
                self._key,
                self.function_addr,
                self.timer_block_addr,
            )
            await client.async_write_register(
                self.function_addr, self.function_code
            )  # Set function (if needed)
            await client.async_write_register(self.timer_block_addr, 3)  # Always on
            await client.async_write_register(EXEC_REGISTER, 1)  # Commit
        elif self._switch_type in ("climate_mode", "smart_anti_freeze", "uv_mode"):
            if self.function_addr is None:
                _LOGGER.error("Missing function_addr for %s", self._key)
                return
            _LOGGER.debug(
                "Setting %s ON via register 0x%04X",
                self._switch_type,
                self.function_addr,
            )
            await client.async_write_register(self.function_addr, 1)
        elif self._switch_type == "bitmask":
            if self.function_addr is None or self._mask_bit is None:
                _LOGGER.error("Missing bitmask config for %s", self._key)
                return
            current = int(self.coordinator.data.get(self._data_key, 0) or 0)
            new_value = current | self._mask_bit
            _LOGGER.debug(
                "Bitmask ON %s: reg=0x%04X mask=0x%04X current=%s new=%s",
                self._key,
                self.function_addr,
                self._mask_bit,
                current,
                new_value,
            )
            await client.async_write_register(self.function_addr, new_value, apply=True)

        # Optimistic update + schedule follow-up for IO switch types
        if self._switch_type not in ("auto_time_sync", "winter_mode"):
            self._optimistic_update(True)
            if self.coordinator.data is not None:
                self.coordinator.async_set_updated_data(self.coordinator.data)
            self.coordinator.request_refresh_with_followup()
        else:
            await self.coordinator.async_request_refresh()
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch OFF."""
        if (
            self._switch_type not in ("winter_mode", "auto_time_sync")
            and self.coordinator.winter_mode
        ):
            _LOGGER.warning(
                "Winter mode is active — ignoring turn_off for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers.")
            return
        if self._switch_type == "manual_filtration":
            await client.async_write_register(MANUAL_FILTRATION_REGISTER, 0)
        elif self._switch_type == "aux":
            _LOGGER.debug(
                "Turning OFF %s (relay index %s)", self._key, self._relay_index
            )
            await client.async_write_aux_relay(self._relay_index, False)
        elif self._switch_type == "auto_time_sync":
            await self.coordinator.set_auto_time_sync(False)
        elif self._switch_type == "winter_mode":
            await self.coordinator.set_winter_mode(False)
        elif self._switch_type == "relay_timer":
            if self.timer_block_addr is None:
                _LOGGER.error("Missing timer_block_addr for %s", self._key)
                return
            _LOGGER.debug(
                "Turning OFF relay %s: timer_block_addr=0x%04X",
                self._key,
                self.timer_block_addr,
            )
            await client.async_write_register(self.timer_block_addr, 4)  # Always off
            await client.async_write_register(EXEC_REGISTER, 1)  # Commit
        elif self._switch_type in ("climate_mode", "smart_anti_freeze", "uv_mode"):
            if self.function_addr is None:
                _LOGGER.error("Missing function_addr for %s", self._key)
                return
            _LOGGER.debug(
                "Setting %s OFF via register 0x%04X",
                self._switch_type,
                self.function_addr,
            )
            await client.async_write_register(self.function_addr, 0)
        elif self._switch_type == "bitmask":
            if self.function_addr is None or self._mask_bit is None:
                _LOGGER.error("Missing bitmask config for %s", self._key)
                return
            current = int(self.coordinator.data.get(self._data_key, 0) or 0)
            new_value = current & ~self._mask_bit
            _LOGGER.debug(
                "Bitmask OFF %s: reg=0x%04X mask=0x%04X current=%s new=%s",
                self._key,
                self.function_addr,
                self._mask_bit,
                current,
                new_value,
            )
            await client.async_write_register(self.function_addr, new_value, apply=True)

        # Optimistic update + schedule follow-up for IO switch types
        if self._switch_type not in ("auto_time_sync", "winter_mode"):
            self._optimistic_update(False)
            if self.coordinator.data is not None:
                self.coordinator.async_set_updated_data(self.coordinator.data)
            self.coordinator.request_refresh_with_followup()
        else:
            await self.coordinator.async_request_refresh()
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:  # pragma: no cover
        """Handle entity which will be added to hass."""
        _LOGGER.debug(
            "ADDED: entity_id=%s, translation_key=%s, has_entity_name=%s",
            self.entity_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )
        await super().async_added_to_hass()

    def _optimistic_update(self, state: bool) -> None:
        """Apply an optimistic state update to coordinator data."""
        data = self.coordinator.data
        if data is None:
            return
        if self._switch_type == "manual_filtration":
            data["MBF_PAR_FILT_MANUAL_STATE"] = 1 if state else 0
        elif self._switch_type == "aux":
            data[self._key] = state
        elif self._switch_type == "relay_timer":
            data[f"relay_{self._key}_enable"] = 3 if state else 4
        elif self._switch_type == "climate_mode":
            data["MBF_PAR_CLIMA_ONOFF"] = 1 if state else 0
        elif self._switch_type == "smart_anti_freeze":
            data["MBF_PAR_SMART_ANTI_FREEZE"] = 1 if state else 0
        elif self._switch_type == "uv_mode":
            data["MBF_PAR_UV_MODE"] = 1 if state else 0
        elif self._switch_type == "bitmask" and self._mask_bit is not None:
            current = int(data.get(self._data_key, 0) or 0)
            if state:
                data[self._data_key] = current | self._mask_bit
            else:
                data[self._data_key] = current & ~self._mask_bit

    @property
    def is_on(self) -> bool:  # type: ignore[override]
        """Return True if the switch is on."""
        if self._switch_type == "manual_filtration":
            if self.coordinator.data.get("MBF_PAR_FILT_MODE") == 1:
                return False
            return self.coordinator.data.get("MBF_PAR_FILT_MANUAL_STATE") == 1
        elif self._switch_type == "aux":
            return bool(self.coordinator.data.get(self._key, False))
        elif self._switch_type == "auto_time_sync":
            return getattr(self.coordinator, "auto_time_sync", False)
        elif self._switch_type == "winter_mode":
            return getattr(self.coordinator, "winter_mode", False)
        elif self._switch_type == "timer_enable":
            return bool(self.coordinator.data.get(self._key, 0))
        elif self._switch_type == "relay_timer":
            enable_val = self.coordinator.data.get(f"relay_{self._key}_enable", None)
            return enable_val == 3  # ON if ALWAYS ON
        elif self._switch_type == "climate_mode":
            return bool(self.coordinator.data.get("MBF_PAR_CLIMA_ONOFF", 0))
        elif self._switch_type == "smart_anti_freeze":
            return bool(self.coordinator.data.get("MBF_PAR_SMART_ANTI_FREEZE", 0))
        elif self._switch_type == "uv_mode":
            return bool(self.coordinator.data.get("MBF_PAR_UV_MODE", 0))
        elif self._switch_type == "bitmask" and self._mask_bit is not None:
            raw = int(self.coordinator.data.get(self._data_key, 0) or 0)
            return bool(raw & self._mask_bit)
        return False

    @property
    def available(self) -> bool:  # type: ignore[override]
        """Return True if the switch is available."""
        # These switches are pure HA settings (not device state) – always operable.
        if self._switch_type in ("winter_mode", "auto_time_sync"):
            return True
        if not super().available:
            return False
        if self._switch_type == "manual_filtration":
            return self.coordinator.data.get("MBF_PAR_FILT_MODE") == 0
        if self._switch_type == "relay_timer":
            # Getting the timer name based on the switch key (e.g., "aux1" -> "relay_aux1_enable")
            if self._key.startswith("aux"):
                timer_name = f"relay_{self._key}_enable"
            elif self._key == "light":
                timer_name = "relay_light_enable"
            else:
                return True
            mode_val = self.coordinator.data.get(timer_name, None)
            # 3 = on, 4 = off → available; 0 (disabled) or 1 (auto) → not available
            return mode_val in (3, 4)
        return True

    @property
    def icon(self) -> str | None:  # type: ignore[override]
        """Return the icon to use in the frontend, depending on the state."""
        if self._icon_on and self._icon_off:
            return self._icon_on if self.is_on else self._icon_off
        if self._attr_icon:
            return self._attr_icon
        return None
