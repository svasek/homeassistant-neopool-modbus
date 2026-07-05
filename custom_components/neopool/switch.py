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

"""Switch platform for the NeoPool integration."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import logging
from typing import Any, override

from neopool_modbus.registers import (
    AUX1_FUNCTION_CODE,
    AUX1_FUNCTION_REGISTER,
    AUX1_TIMER_BLOCK_REGISTER,
    AUX2_FUNCTION_CODE,
    AUX2_FUNCTION_REGISTER,
    AUX2_TIMER_BLOCK_REGISTER,
    AUX3_FUNCTION_CODE,
    AUX3_FUNCTION_REGISTER,
    AUX3_TIMER_BLOCK_REGISTER,
    AUX4_FUNCTION_CODE,
    AUX4_FUNCTION_REGISTER,
    AUX4_TIMER_BLOCK_REGISTER,
    CLIMA_ONOFF_REGISTER,
    EXEC_REGISTER,
    HIDRO_COVER_ENABLE_BIT,
    HIDRO_COVER_ENABLE_REGISTER,
    HIDRO_TEMP_SHUTDOWN_BIT,
    MANUAL_FILTRATION_REGISTER,
    SMART_ANTI_FREEZE_REGISTER,
    UV_MODE_REGISTER,
    TimerRelayMode,
    is_valid_relay_gpio,
)

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import NeoPoolConfigEntry, NeoPoolCoordinator
from .entity import NeoPoolEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# Switch types that are HA-side settings, not device state: they don't need a
# client, don't participate in the winter-mode guard, and stay available even
# while winter mode is active.
_HA_SETTING_TYPES = frozenset({"winter_mode", "auto_time_sync"})

_SIMPLE_REGISTER_TYPES = frozenset({"climate_mode", "smart_anti_freeze", "uv_mode"})


@dataclass(frozen=True, kw_only=True)
class NeoPoolSwitchEntityDescription(SwitchEntityDescription):
    """Describes a NeoPool switch entity."""

    switch_type: str = ""
    function_addr: int | None = None
    function_code: int | None = None
    timer_block_addr: int | None = None
    mask_bit: int | None = None
    data_key: str | None = None
    supported_fn: Callable[[dict[str, Any], Mapping[str, Any]], bool] | None = None


SWITCH_DESCRIPTIONS: dict[str, NeoPoolSwitchEntityDescription] = {
    "WINTER_MODE": NeoPoolSwitchEntityDescription(
        key="WINTER_MODE",
        translation_key="winter_mode",
        entity_category=EntityCategory.CONFIG,
        switch_type="winter_mode",
    ),
    "TIME_AUTO_SYNC": NeoPoolSwitchEntityDescription(
        key="TIME_AUTO_SYNC",
        translation_key="time_auto_sync",
        entity_category=EntityCategory.CONFIG,
        switch_type="auto_time_sync",
    ),
    "MBF_PAR_FILT_MANUAL_STATE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_FILT_MANUAL_STATE",
        translation_key="filt_manual_state",
        switch_type="manual_filtration",
    ),
    "MBF_PAR_CLIMA_ONOFF": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_CLIMA_ONOFF",
        translation_key="clima_onoff",
        entity_category=EntityCategory.CONFIG,
        switch_type="climate_mode",
        function_addr=CLIMA_ONOFF_REGISTER,
        supported_fn=lambda data, opts: (
            bool(data.get("MBF_PAR_HEATING_GPIO"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
    "MBF_PAR_SMART_ANTI_FREEZE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_SMART_ANTI_FREEZE",
        translation_key="smart_anti_freeze",
        entity_category=EntityCategory.CONFIG,
        switch_type="smart_anti_freeze",
        function_addr=SMART_ANTI_FREEZE_REGISTER,
        supported_fn=lambda data, opts: bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE")),
    ),
    "MBF_PAR_UV_MODE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_UV_MODE",
        translation_key="uv_mode",
        entity_category=EntityCategory.CONFIG,
        switch_type="uv_mode",
        function_addr=UV_MODE_REGISTER,
        supported_fn=lambda data, opts: is_valid_relay_gpio(
            data.get("MBF_PAR_UV_RELAY_GPIO", 0) or 0
        ),
    ),
    "MBF_PAR_HIDRO_COVER_ENABLE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_HIDRO_COVER_ENABLE",
        translation_key="hidro_cover_enable",
        entity_category=EntityCategory.CONFIG,
        switch_type="bitmask",
        function_addr=HIDRO_COVER_ENABLE_REGISTER,
        mask_bit=HIDRO_COVER_ENABLE_BIT,
        data_key="MBF_PAR_HIDRO_COVER_ENABLE",
        supported_fn=lambda data, opts: (
            bool(opts.get("use_cover_sensor"))
            and bool(data.get("Hydrolysis module detected"))
        ),
    ),
    "MBF_PAR_HIDRO_TEMP_SHUTDOWN": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_HIDRO_TEMP_SHUTDOWN",
        translation_key="hidro_temp_shutdown",
        entity_category=EntityCategory.CONFIG,
        switch_type="bitmask",
        function_addr=HIDRO_COVER_ENABLE_REGISTER,
        mask_bit=HIDRO_TEMP_SHUTDOWN_BIT,
        data_key="MBF_PAR_HIDRO_COVER_ENABLE",
        supported_fn=lambda data, opts: (
            bool(opts.get("use_cover_sensor"))
            and bool(data.get("Hydrolysis module detected"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
    "aux1": NeoPoolSwitchEntityDescription(
        key="aux1",
        translation_key="aux1",
        switch_type="relay_timer",
        timer_block_addr=AUX1_TIMER_BLOCK_REGISTER,
        function_addr=AUX1_FUNCTION_REGISTER,
        function_code=AUX1_FUNCTION_CODE,
        supported_fn=lambda data, opts: bool(opts.get("use_aux1")),
    ),
    "aux2": NeoPoolSwitchEntityDescription(
        key="aux2",
        translation_key="aux2",
        switch_type="relay_timer",
        timer_block_addr=AUX2_TIMER_BLOCK_REGISTER,
        function_addr=AUX2_FUNCTION_REGISTER,
        function_code=AUX2_FUNCTION_CODE,
        supported_fn=lambda data, opts: bool(opts.get("use_aux2")),
    ),
    "aux3": NeoPoolSwitchEntityDescription(
        key="aux3",
        translation_key="aux3",
        switch_type="relay_timer",
        timer_block_addr=AUX3_TIMER_BLOCK_REGISTER,
        function_addr=AUX3_FUNCTION_REGISTER,
        function_code=AUX3_FUNCTION_CODE,
        supported_fn=lambda data, opts: bool(opts.get("use_aux3")),
    ),
    "aux4": NeoPoolSwitchEntityDescription(
        key="aux4",
        translation_key="aux4",
        switch_type="relay_timer",
        timer_block_addr=AUX4_TIMER_BLOCK_REGISTER,
        function_addr=AUX4_FUNCTION_REGISTER,
        function_code=AUX4_FUNCTION_CODE,
        supported_fn=lambda data, opts: bool(opts.get("use_aux4")),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool switches from a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        NeoPoolSwitch(coordinator, entry.entry_id, key, desc)
        for key, desc in SWITCH_DESCRIPTIONS.items()
        if desc.supported_fn is None
        or desc.supported_fn(coordinator.data, entry.options)
    )


class NeoPoolSwitch(NeoPoolEntity, SwitchEntity):
    """Representation of a NeoPool switch entity."""

    entity_description: NeoPoolSwitchEntityDescription

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        description: NeoPoolSwitchEntityDescription,
    ) -> None:
        """Initialize the NeoPool switch entity."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._key = key
        self._attr_unique_id = f"{self.coordinator.entry.unique_id}_{key.lower()}"

        # The winter_mode switch itself must remain available while winter mode is on
        if description.switch_type == "winter_mode":
            self._winter_mode_active = False

        self._data_key = description.data_key or key

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch ON."""
        await self._async_set_state(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch OFF."""
        await self._async_set_state(False)

    async def _async_set_state(self, state: bool) -> None:
        """Dispatch turn_on / turn_off to the per-type writer."""
        desc = self.entity_description
        action = "turn_on" if state else "turn_off"
        if desc.switch_type not in _HA_SETTING_TYPES and self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active, ignoring %s for %s", action, self._key
            )
            return

        if desc.switch_type == "winter_mode":
            await self.coordinator.set_winter_mode(state)
            await self.coordinator.async_request_refresh()
            self.async_write_ha_state()
            return
        if desc.switch_type == "auto_time_sync":
            await self.coordinator.set_auto_time_sync(state)
            await self.coordinator.async_request_refresh()
            self.async_write_ha_state()
            return

        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers")
            return

        if desc.switch_type == "manual_filtration":
            await self._write_manual_filtration(client, state)
        elif desc.switch_type == "relay_timer":
            await self._write_relay_timer(client, state)
        elif desc.switch_type in _SIMPLE_REGISTER_TYPES:
            await self._write_simple_register(client, state)
        elif desc.switch_type == "bitmask":
            await self._write_bitmask(client, state)

        self._optimistic_update(state)
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    async def _write_manual_filtration(self, client: Any, state: bool) -> None:
        """Write the manual filtration on/off register."""
        if self.coordinator.data.get("MBF_PAR_FILT_MODE") != 0:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="filtration_not_manual_mode",
            )
        await client.async_write_register(MANUAL_FILTRATION_REGISTER, 1 if state else 0)

    async def _write_relay_timer(self, client: Any, state: bool) -> None:
        """Turn an auxiliary relay on/off via its timer block."""
        desc = self.entity_description
        if desc.timer_block_addr is None:  # pragma: no cover
            _LOGGER.error("Missing timer_block_addr for %s", self._key)
            return
        if state:
            if (
                desc.function_addr is None or desc.function_code is None
            ):  # pragma: no cover
                _LOGGER.error("Missing relay_timer function config for %s", self._key)
                return
            _LOGGER.debug(
                "Turning ON relay %s: function_addr=0x%04X, timer_block_addr=0x%04X",
                self._key,
                desc.function_addr,
                desc.timer_block_addr,
            )
            await client.async_write_register(desc.function_addr, desc.function_code)
            await client.async_write_register(
                desc.timer_block_addr, TimerRelayMode.ALWAYS_ON
            )
        else:
            _LOGGER.debug(
                "Turning OFF relay %s: timer_block_addr=0x%04X",
                self._key,
                desc.timer_block_addr,
            )
            await client.async_write_register(
                desc.timer_block_addr, TimerRelayMode.ALWAYS_OFF
            )
        await client.async_write_register(EXEC_REGISTER, 1)  # Commit

    async def _write_simple_register(self, client: Any, state: bool) -> None:
        """Write 1/0 into a simple on/off register."""
        desc = self.entity_description
        if desc.function_addr is None:  # pragma: no cover
            _LOGGER.error("Missing function_addr for %s", self._key)
            return
        _LOGGER.debug(
            "Setting %s %s via register 0x%04X",
            desc.switch_type,
            "ON" if state else "OFF",
            desc.function_addr,
        )
        await client.async_write_register(desc.function_addr, 1 if state else 0)

    async def _write_bitmask(self, client: Any, state: bool) -> None:
        """Flip a single bit inside a packed register."""
        desc = self.entity_description
        if desc.function_addr is None or desc.mask_bit is None:  # pragma: no cover
            _LOGGER.error("Missing bitmask config for %s", self._key)
            return
        current = int(self.coordinator.data.get(self._data_key, 0) or 0)
        new_value = current | desc.mask_bit if state else current & ~desc.mask_bit
        _LOGGER.debug(
            "Bitmask %s %s: reg=0x%04X mask=0x%04X current=%s new=%s",
            "ON" if state else "OFF",
            self._key,
            desc.function_addr,
            desc.mask_bit,
            current,
            new_value,
        )
        await client.async_write_register(desc.function_addr, new_value, apply=True)

    def _optimistic_update(self, state: bool) -> None:
        """Apply an optimistic state update to coordinator data."""
        desc = self.entity_description
        data = self.coordinator.data
        if desc.switch_type == "manual_filtration":
            data["Filtration Pump"] = state
        elif desc.switch_type == "relay_timer":
            data[f"relay_{self._key}_enable"] = (
                TimerRelayMode.ALWAYS_ON if state else TimerRelayMode.ALWAYS_OFF
            )
        elif desc.switch_type == "climate_mode":
            data["MBF_PAR_CLIMA_ONOFF"] = 1 if state else 0
        elif desc.switch_type == "smart_anti_freeze":
            data["MBF_PAR_SMART_ANTI_FREEZE"] = 1 if state else 0
        elif desc.switch_type == "uv_mode":
            data["MBF_PAR_UV_MODE"] = 1 if state else 0
        elif desc.switch_type == "bitmask" and desc.mask_bit is not None:
            current = int(data.get(self._data_key, 0) or 0)
            if state:
                data[self._data_key] = current | desc.mask_bit
            else:
                data[self._data_key] = current & ~desc.mask_bit

    @property
    @override
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        desc = self.entity_description
        data = self.coordinator.data
        if desc.switch_type == "manual_filtration":
            return bool(data.get("Filtration Pump"))
        if desc.switch_type == "auto_time_sync":
            return getattr(self.coordinator, "auto_time_sync", False)
        if desc.switch_type == "winter_mode":
            return getattr(self.coordinator, "winter_mode", False)
        if desc.switch_type == "relay_timer":
            enable_val = data.get(f"relay_{self._key}_enable", None)
            return enable_val == TimerRelayMode.ALWAYS_ON
        if desc.switch_type == "climate_mode":
            return bool(data.get("MBF_PAR_CLIMA_ONOFF", 0))
        if desc.switch_type == "smart_anti_freeze":
            return bool(data.get("MBF_PAR_SMART_ANTI_FREEZE", 0))
        if desc.switch_type == "uv_mode":
            return bool(data.get("MBF_PAR_UV_MODE", 0))
        if desc.switch_type == "bitmask" and desc.mask_bit is not None:
            raw = int(data.get(self._data_key, 0) or 0)
            return bool(raw & desc.mask_bit)
        return False  # pragma: no cover

    @property
    @override
    def available(self) -> bool:
        """Return True if the switch is available."""
        desc = self.entity_description
        # These switches are HA settings (not device state)
        if desc.switch_type in _HA_SETTING_TYPES:
            return True
        if not super().available:
            return False
        if desc.switch_type == "relay_timer":
            return self._relay_timer_available()
        return True

    def _relay_timer_available(self) -> bool:
        """Report a relay-timer switch as available only when it is user-controlled."""
        if self._key.startswith("aux"):
            timer_name = f"relay_{self._key}_enable"
        elif self._key == "light":  # pragma: no cover
            timer_name = "relay_light_enable"
        else:
            return True  # pragma: no cover
        mode_val = self.coordinator.data.get(timer_name, None)
        # 3 = on, 4 = off → available; 0 (disabled) or 1 (auto) → not available
        return mode_val in (3, 4)
