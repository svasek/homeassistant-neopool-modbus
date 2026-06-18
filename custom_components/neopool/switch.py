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
from typing import Any

from neopool_modbus.registers import (
    EXEC_REGISTER,
    MANUAL_FILTRATION_REGISTER,
    TimerRelayMode,
    is_valid_relay_gpio,
)

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NeoPoolConfigEntry
from .coordinator import NeoPoolCoordinator
from .entity import NeoPoolEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

type SupportedFn = Callable[[dict[str, Any], Mapping[str, Any]], bool]


@dataclass(frozen=True, kw_only=True)
class NeoPoolSwitchEntityDescription(SwitchEntityDescription):
    """Describes a NeoPool switch entity."""

    switch_type: str = ""
    function_addr: int | None = None
    function_code: int | None = None
    timer_block_addr: int | None = None
    mask_bit: int | None = None
    data_key: str | None = None
    supported_fn: SupportedFn | None = None


SWITCH_DESCRIPTIONS: dict[str, NeoPoolSwitchEntityDescription] = {
    "WINTER_MODE": NeoPoolSwitchEntityDescription(
        key="WINTER_MODE",
        entity_category=EntityCategory.CONFIG,
        switch_type="winter_mode",
    ),
    "TIME_AUTO_SYNC": NeoPoolSwitchEntityDescription(
        key="TIME_AUTO_SYNC",
        entity_category=EntityCategory.CONFIG,
        switch_type="auto_time_sync",
    ),
    "MBF_PAR_FILT_MANUAL_STATE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_FILT_MANUAL_STATE",
        switch_type="manual_filtration",
    ),
    "MBF_PAR_CLIMA_ONOFF": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_CLIMA_ONOFF",
        entity_category=EntityCategory.CONFIG,
        switch_type="climate_mode",
        function_addr=0x0417,
        supported_fn=lambda data, opts: (
            bool(data.get("MBF_PAR_HEATING_GPIO"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
    "MBF_PAR_SMART_ANTI_FREEZE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_SMART_ANTI_FREEZE",
        entity_category=EntityCategory.CONFIG,
        switch_type="smart_anti_freeze",
        function_addr=0x041A,
        supported_fn=lambda data, opts: bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE")),
    ),
    "MBF_PAR_UV_MODE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_UV_MODE",
        entity_category=EntityCategory.CONFIG,
        switch_type="uv_mode",
        function_addr=0x0427,
        supported_fn=lambda data, opts: (
            "MBF_PAR_UV_RELAY_GPIO" not in data
            or is_valid_relay_gpio(data["MBF_PAR_UV_RELAY_GPIO"] or 0)
        ),
    ),
    "MBF_PAR_HIDRO_COVER_ENABLE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_HIDRO_COVER_ENABLE",
        entity_category=EntityCategory.CONFIG,
        switch_type="bitmask",
        function_addr=0x042C,
        mask_bit=0x0001,
        data_key="MBF_PAR_HIDRO_COVER_ENABLE",
        supported_fn=lambda data, opts: (
            bool(opts.get("use_cover_sensor"))
            and bool(data.get("Hydrolysis module detected"))
        ),
    ),
    "MBF_PAR_HIDRO_TEMP_SHUTDOWN": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_HIDRO_TEMP_SHUTDOWN",
        entity_category=EntityCategory.CONFIG,
        switch_type="bitmask",
        function_addr=0x042C,
        mask_bit=0x0002,
        data_key="MBF_PAR_HIDRO_COVER_ENABLE",
        supported_fn=lambda data, opts: (
            bool(opts.get("use_cover_sensor"))
            and bool(data.get("Hydrolysis module detected"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
    "aux1": NeoPoolSwitchEntityDescription(
        key="aux1",
        switch_type="relay_timer",
        timer_block_addr=0x04AC,
        function_addr=0x04B7,
        function_code=0x0800,  # AUX1 relay code
        supported_fn=lambda data, opts: bool(opts.get("use_aux1")),
    ),
    "aux2": NeoPoolSwitchEntityDescription(
        key="aux2",
        switch_type="relay_timer",
        timer_block_addr=0x04BB,
        function_addr=0x04C6,
        function_code=0x1000,  # AUX2 relay code
        supported_fn=lambda data, opts: bool(opts.get("use_aux2")),
    ),
    "aux3": NeoPoolSwitchEntityDescription(
        key="aux3",
        switch_type="relay_timer",
        timer_block_addr=0x04CA,
        function_addr=0x04D5,
        function_code=0x2000,  # AUX3 relay code
        supported_fn=lambda data, opts: bool(opts.get("use_aux3")),
    ),
    "aux4": NeoPoolSwitchEntityDescription(
        key="aux4",
        switch_type="relay_timer",
        timer_block_addr=0x04D9,
        function_addr=0x04E4,
        function_code=0x4000,  # AUX4 relay code
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
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{key.lower()}"
        self._attr_translation_key = NeoPoolEntity.slugify(key)

        # The winter_mode switch itself must remain available while winter mode is on
        if description.switch_type == "winter_mode":
            self._winter_mode_active = False

        self._data_key = description.data_key or key

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch ON."""
        desc = self.entity_description
        if (
            desc.switch_type not in ("winter_mode", "auto_time_sync")
            and self.coordinator.winter_mode
        ):
            _LOGGER.warning(
                "Winter mode is active — ignoring turn_on for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers")
            return
        if desc.switch_type == "manual_filtration":
            await client.async_write_register(MANUAL_FILTRATION_REGISTER, 1)
        elif desc.switch_type == "auto_time_sync":
            await self.coordinator.set_auto_time_sync(True)
        elif desc.switch_type == "winter_mode":
            await self.coordinator.set_winter_mode(True)
        elif desc.switch_type == "relay_timer":
            if (
                desc.function_addr is None
                or desc.function_code is None
                or desc.timer_block_addr is None
            ):  # pragma: no cover
                _LOGGER.error("Missing relay_timer config for %s", self._key)
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
            await client.async_write_register(EXEC_REGISTER, 1)  # Commit
        elif desc.switch_type in ("climate_mode", "smart_anti_freeze", "uv_mode"):
            if desc.function_addr is None:  # pragma: no cover
                _LOGGER.error("Missing function_addr for %s", self._key)
                return
            _LOGGER.debug(
                "Setting %s ON via register 0x%04X",
                desc.switch_type,
                desc.function_addr,
            )
            await client.async_write_register(desc.function_addr, 1)
        elif desc.switch_type == "bitmask":
            if desc.function_addr is None or desc.mask_bit is None:  # pragma: no cover
                _LOGGER.error("Missing bitmask config for %s", self._key)
                return
            current = int(self.coordinator.data.get(self._data_key, 0) or 0)
            new_value = current | desc.mask_bit
            _LOGGER.debug(
                "Bitmask ON %s: reg=0x%04X mask=0x%04X current=%s new=%s",
                self._key,
                desc.function_addr,
                desc.mask_bit,
                current,
                new_value,
            )
            await client.async_write_register(desc.function_addr, new_value, apply=True)

        if desc.switch_type not in ("auto_time_sync", "winter_mode"):
            self._optimistic_update(True)
            self.coordinator.async_set_updated_data(self.coordinator.data)
            self.coordinator.request_refresh_with_followup()
        else:
            await self.coordinator.async_request_refresh()
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch OFF."""
        desc = self.entity_description
        if (
            desc.switch_type not in ("winter_mode", "auto_time_sync")
            and self.coordinator.winter_mode
        ):
            _LOGGER.warning(
                "Winter mode is active — ignoring turn_off for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers")
            return
        if desc.switch_type == "manual_filtration":
            await client.async_write_register(MANUAL_FILTRATION_REGISTER, 0)
        elif desc.switch_type == "auto_time_sync":
            await self.coordinator.set_auto_time_sync(False)
        elif desc.switch_type == "winter_mode":
            await self.coordinator.set_winter_mode(False)
        elif desc.switch_type == "relay_timer":
            if desc.timer_block_addr is None:  # pragma: no cover
                _LOGGER.error("Missing timer_block_addr for %s", self._key)
                return
            _LOGGER.debug(
                "Turning OFF relay %s: timer_block_addr=0x%04X",
                self._key,
                desc.timer_block_addr,
            )
            await client.async_write_register(
                desc.timer_block_addr, TimerRelayMode.ALWAYS_OFF
            )
            await client.async_write_register(EXEC_REGISTER, 1)  # Commit
        elif desc.switch_type in ("climate_mode", "smart_anti_freeze", "uv_mode"):
            if desc.function_addr is None:  # pragma: no cover
                _LOGGER.error("Missing function_addr for %s", self._key)
                return
            _LOGGER.debug(
                "Setting %s OFF via register 0x%04X",
                desc.switch_type,
                desc.function_addr,
            )
            await client.async_write_register(desc.function_addr, 0)
        elif desc.switch_type == "bitmask":
            if desc.function_addr is None or desc.mask_bit is None:  # pragma: no cover
                _LOGGER.error("Missing bitmask config for %s", self._key)
                return
            current = int(self.coordinator.data.get(self._data_key, 0) or 0)
            new_value = current & ~desc.mask_bit
            _LOGGER.debug(
                "Bitmask OFF %s: reg=0x%04X mask=0x%04X current=%s new=%s",
                self._key,
                desc.function_addr,
                desc.mask_bit,
                current,
                new_value,
            )
            await client.async_write_register(desc.function_addr, new_value, apply=True)

        if desc.switch_type not in ("auto_time_sync", "winter_mode"):
            self._optimistic_update(False)
            self.coordinator.async_set_updated_data(self.coordinator.data)
            self.coordinator.request_refresh_with_followup()
        else:
            await self.coordinator.async_request_refresh()
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added to hass."""
        _LOGGER.debug(
            "ADDED: entity_id=%s, translation_key=%s, has_entity_name=%s",
            self.entity_id,
            self.entity_description.translation_key,
            getattr(self, "has_entity_name", None),
        )
        await super().async_added_to_hass()

    def _optimistic_update(self, state: bool) -> None:
        """Apply an optimistic state update to coordinator data."""
        desc = self.entity_description
        data = self.coordinator.data
        if desc.switch_type == "manual_filtration":
            data["MBF_PAR_FILT_MANUAL_STATE"] = 1 if state else 0
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
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        desc = self.entity_description
        if desc.switch_type == "manual_filtration":
            if self.coordinator.data.get("MBF_PAR_FILT_MODE") == 1:
                return False
            return self.coordinator.data.get("MBF_PAR_FILT_MANUAL_STATE") == 1
        if desc.switch_type == "auto_time_sync":
            return getattr(self.coordinator, "auto_time_sync", False)
        if desc.switch_type == "winter_mode":
            return getattr(self.coordinator, "winter_mode", False)
        if desc.switch_type == "relay_timer":
            enable_val = self.coordinator.data.get(f"relay_{self._key}_enable", None)
            return enable_val == TimerRelayMode.ALWAYS_ON
        if desc.switch_type == "climate_mode":
            return bool(self.coordinator.data.get("MBF_PAR_CLIMA_ONOFF", 0))
        if desc.switch_type == "smart_anti_freeze":
            return bool(self.coordinator.data.get("MBF_PAR_SMART_ANTI_FREEZE", 0))
        if desc.switch_type == "uv_mode":
            return bool(self.coordinator.data.get("MBF_PAR_UV_MODE", 0))
        if desc.switch_type == "bitmask" and desc.mask_bit is not None:
            raw = int(self.coordinator.data.get(self._data_key, 0) or 0)
            return bool(raw & desc.mask_bit)
        return False  # pragma: no cover

    @property
    def available(self) -> bool:
        """Return True if the switch is available."""
        desc = self.entity_description
        # These switches are HA settings (not device state)
        if desc.switch_type in ("winter_mode", "auto_time_sync"):
            return True
        if not super().available:
            return False
        if desc.switch_type == "manual_filtration":
            return self.coordinator.data.get("MBF_PAR_FILT_MODE") == 0
        if desc.switch_type == "relay_timer":
            if self._key.startswith("aux"):
                timer_name = f"relay_{self._key}_enable"
            elif self._key == "light":  # pragma: no cover
                timer_name = "relay_light_enable"
            else:
                return True  # pragma: no cover
            mode_val = self.coordinator.data.get(timer_name, None)
            # 3 = on, 4 = off → available; 0 (disabled) or 1 (auto) → not available
            return mode_val in (3, 4)
        return True
