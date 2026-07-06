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

from collections.abc import Awaitable, Callable, Mapping
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
_HA_SETTING_WINTER_MODE = "winter_mode"
_HA_SETTING_AUTO_TIME_SYNC = "auto_time_sync"
_HA_SETTING_TYPES = frozenset({_HA_SETTING_WINTER_MODE, _HA_SETTING_AUTO_TIME_SYNC})


type _WriteFn = Callable[["NeoPoolSwitch", Any, bool], Awaitable[None]]
type _IsOnFn = Callable[[dict[str, Any]], bool]
type _OptimisticFn = Callable[["NeoPoolSwitch", bool], None]


@dataclass(frozen=True, kw_only=True)
class NeoPoolSwitchEntityDescription(SwitchEntityDescription):
    """Describes a NeoPool switch entity."""

    ha_setting: str | None = None
    supported_fn: Callable[[dict[str, Any], Mapping[str, Any]], bool] | None = None
    write_fn: _WriteFn | None = None
    is_on_fn: _IsOnFn | None = None
    optimistic_fn: _OptimisticFn | None = None


# ---------------------------------------------------------------------------
# Write paths (per switch flavor)
# ---------------------------------------------------------------------------


async def _write_manual_filtration(
    entity: "NeoPoolSwitch", client: Any, state: bool
) -> None:
    """Toggle the pump only when the controller is in manual filtration mode."""
    if entity.coordinator.data.get("MBF_PAR_FILT_MODE") != 0:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="filtration_not_manual_mode",
        )
    await client.async_write_register(MANUAL_FILTRATION_REGISTER, 1 if state else 0)


def _make_write_relay_timer(
    timer_block_addr: int, function_addr: int, function_code: int
) -> _WriteFn:
    """Build a write_fn that drives an aux relay via its timer block."""

    async def _write(entity: "NeoPoolSwitch", client: Any, state: bool) -> None:
        current_mode = entity.coordinator.data.get(f"relay_{entity.key}_enable")
        if current_mode not in (
            TimerRelayMode.ALWAYS_ON,
            TimerRelayMode.ALWAYS_OFF,
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="relay_in_auto_mode",
            )
        if state:
            _LOGGER.debug(
                "Turning ON relay %s: function_addr=0x%04X, timer_block_addr=0x%04X",
                entity.key,
                function_addr,
                timer_block_addr,
            )
            await client.async_write_register(function_addr, function_code)
            await client.async_write_register(
                timer_block_addr, TimerRelayMode.ALWAYS_ON
            )
        else:
            _LOGGER.debug(
                "Turning OFF relay %s: timer_block_addr=0x%04X",
                entity.key,
                timer_block_addr,
            )
            await client.async_write_register(
                timer_block_addr, TimerRelayMode.ALWAYS_OFF
            )
        await client.async_write_register(EXEC_REGISTER, 1)  # Commit

    return _write


def _make_write_simple_register(addr: int) -> _WriteFn:
    """Build a write_fn that writes 1/0 into a simple on/off register."""

    async def _write(entity: "NeoPoolSwitch", client: Any, state: bool) -> None:
        _LOGGER.debug(
            "Setting %s %s via register 0x%04X",
            entity.key,
            "ON" if state else "OFF",
            addr,
        )
        await client.async_write_register(addr, 1 if state else 0)

    return _write


def _make_write_bitmask(addr: int, mask: int, data_key: str) -> _WriteFn:
    """Build a write_fn that flips a single bit inside a packed register."""

    async def _write(entity: "NeoPoolSwitch", client: Any, state: bool) -> None:
        current = int(entity.coordinator.data.get(data_key, 0) or 0)
        new_value = current | mask if state else current & ~mask
        _LOGGER.debug(
            "Bitmask %s %s: reg=0x%04X mask=0x%04X current=%s new=%s",
            "ON" if state else "OFF",
            entity.key,
            addr,
            mask,
            current,
            new_value,
        )
        await client.async_write_register(addr, new_value, apply=True)

    return _write


# ---------------------------------------------------------------------------
# is_on readers
# ---------------------------------------------------------------------------


def _make_is_on_from_key(data_key: str) -> _IsOnFn:
    """Read a truthy value from a specific coordinator-data key."""
    return lambda data: bool(data.get(data_key))


def _make_is_on_int_flag(data_key: str) -> _IsOnFn:
    """Read a coordinator-data integer flag (0 = off, non-zero = on)."""
    return lambda data: bool(data.get(data_key, 0))


def _make_is_on_bitmask(data_key: str, mask: int) -> _IsOnFn:
    """Read a single bit from a packed coordinator-data register."""
    return lambda data: bool(int(data.get(data_key, 0) or 0) & mask)


# ---------------------------------------------------------------------------
# Optimistic-update helpers
# ---------------------------------------------------------------------------


def _optimistic_manual_filtration(entity: "NeoPoolSwitch", state: bool) -> None:
    entity.coordinator.data["Filtration Pump"] = state


def _optimistic_relay_timer(entity: "NeoPoolSwitch", state: bool) -> None:
    data = entity.coordinator.data
    data[f"relay_{entity.key}_enable"] = (
        TimerRelayMode.ALWAYS_ON if state else TimerRelayMode.ALWAYS_OFF
    )
    data[entity.key.upper()] = state


def _make_optimistic_int_flag(data_key: str) -> _OptimisticFn:
    """Return an optimistic updater that stores 0/1 into a coordinator-data key."""

    def _apply(entity: "NeoPoolSwitch", state: bool) -> None:
        entity.coordinator.data[data_key] = 1 if state else 0

    return _apply


def _make_optimistic_bitmask(data_key: str, mask: int) -> _OptimisticFn:
    """Return an optimistic updater that flips a bit in a packed register."""

    def _apply(entity: "NeoPoolSwitch", state: bool) -> None:
        current = int(entity.coordinator.data.get(data_key, 0) or 0)
        entity.coordinator.data[data_key] = current | mask if state else current & ~mask

    return _apply


# ---------------------------------------------------------------------------
# Entity descriptions
# ---------------------------------------------------------------------------


SWITCH_DESCRIPTIONS: dict[str, NeoPoolSwitchEntityDescription] = {
    "WINTER_MODE": NeoPoolSwitchEntityDescription(
        key="WINTER_MODE",
        translation_key="winter_mode",
        entity_category=EntityCategory.CONFIG,
        ha_setting=_HA_SETTING_WINTER_MODE,
    ),
    "TIME_AUTO_SYNC": NeoPoolSwitchEntityDescription(
        key="TIME_AUTO_SYNC",
        translation_key="time_auto_sync",
        entity_category=EntityCategory.CONFIG,
        ha_setting=_HA_SETTING_AUTO_TIME_SYNC,
    ),
    "MBF_PAR_FILT_MANUAL_STATE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_FILT_MANUAL_STATE",
        translation_key="filt_manual_state",
        write_fn=_write_manual_filtration,
        is_on_fn=_make_is_on_from_key("Filtration Pump"),
        optimistic_fn=_optimistic_manual_filtration,
    ),
    "MBF_PAR_CLIMA_ONOFF": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_CLIMA_ONOFF",
        translation_key="clima_onoff",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_simple_register(CLIMA_ONOFF_REGISTER),
        is_on_fn=_make_is_on_int_flag("MBF_PAR_CLIMA_ONOFF"),
        optimistic_fn=_make_optimistic_int_flag("MBF_PAR_CLIMA_ONOFF"),
        supported_fn=lambda data, opts: (
            bool(data.get("MBF_PAR_HEATING_GPIO"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
    "MBF_PAR_SMART_ANTI_FREEZE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_SMART_ANTI_FREEZE",
        translation_key="smart_anti_freeze",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_simple_register(SMART_ANTI_FREEZE_REGISTER),
        is_on_fn=_make_is_on_int_flag("MBF_PAR_SMART_ANTI_FREEZE"),
        optimistic_fn=_make_optimistic_int_flag("MBF_PAR_SMART_ANTI_FREEZE"),
        supported_fn=lambda data, opts: bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE")),
    ),
    "MBF_PAR_UV_MODE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_UV_MODE",
        translation_key="uv_mode",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_simple_register(UV_MODE_REGISTER),
        is_on_fn=_make_is_on_int_flag("MBF_PAR_UV_MODE"),
        optimistic_fn=_make_optimistic_int_flag("MBF_PAR_UV_MODE"),
        supported_fn=lambda data, opts: is_valid_relay_gpio(
            data.get("MBF_PAR_UV_RELAY_GPIO", 0) or 0
        ),
    ),
    "MBF_PAR_HIDRO_COVER_ENABLE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_HIDRO_COVER_ENABLE",
        translation_key="hidro_cover_enable",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_bitmask(
            HIDRO_COVER_ENABLE_REGISTER,
            HIDRO_COVER_ENABLE_BIT,
            "MBF_PAR_HIDRO_COVER_ENABLE",
        ),
        is_on_fn=_make_is_on_bitmask(
            "MBF_PAR_HIDRO_COVER_ENABLE", HIDRO_COVER_ENABLE_BIT
        ),
        optimistic_fn=_make_optimistic_bitmask(
            "MBF_PAR_HIDRO_COVER_ENABLE", HIDRO_COVER_ENABLE_BIT
        ),
        supported_fn=lambda data, opts: (
            bool(opts.get("use_cover_sensor"))
            and bool(data.get("Hydrolysis module detected"))
        ),
    ),
    "MBF_PAR_HIDRO_TEMP_SHUTDOWN": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_HIDRO_TEMP_SHUTDOWN",
        translation_key="hidro_temp_shutdown",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_bitmask(
            HIDRO_COVER_ENABLE_REGISTER,
            HIDRO_TEMP_SHUTDOWN_BIT,
            "MBF_PAR_HIDRO_COVER_ENABLE",
        ),
        is_on_fn=_make_is_on_bitmask(
            "MBF_PAR_HIDRO_COVER_ENABLE", HIDRO_TEMP_SHUTDOWN_BIT
        ),
        optimistic_fn=_make_optimistic_bitmask(
            "MBF_PAR_HIDRO_COVER_ENABLE", HIDRO_TEMP_SHUTDOWN_BIT
        ),
        supported_fn=lambda data, opts: (
            bool(opts.get("use_cover_sensor"))
            and bool(data.get("Hydrolysis module detected"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
    "aux1": NeoPoolSwitchEntityDescription(
        key="aux1",
        translation_key="aux1",
        write_fn=_make_write_relay_timer(
            AUX1_TIMER_BLOCK_REGISTER, AUX1_FUNCTION_REGISTER, AUX1_FUNCTION_CODE
        ),
        is_on_fn=_make_is_on_from_key("AUX1"),
        optimistic_fn=_optimistic_relay_timer,
        supported_fn=lambda data, opts: bool(opts.get("use_aux1")),
    ),
    "aux2": NeoPoolSwitchEntityDescription(
        key="aux2",
        translation_key="aux2",
        write_fn=_make_write_relay_timer(
            AUX2_TIMER_BLOCK_REGISTER, AUX2_FUNCTION_REGISTER, AUX2_FUNCTION_CODE
        ),
        is_on_fn=_make_is_on_from_key("AUX2"),
        optimistic_fn=_optimistic_relay_timer,
        supported_fn=lambda data, opts: bool(opts.get("use_aux2")),
    ),
    "aux3": NeoPoolSwitchEntityDescription(
        key="aux3",
        translation_key="aux3",
        write_fn=_make_write_relay_timer(
            AUX3_TIMER_BLOCK_REGISTER, AUX3_FUNCTION_REGISTER, AUX3_FUNCTION_CODE
        ),
        is_on_fn=_make_is_on_from_key("AUX3"),
        optimistic_fn=_optimistic_relay_timer,
        supported_fn=lambda data, opts: bool(opts.get("use_aux3")),
    ),
    "aux4": NeoPoolSwitchEntityDescription(
        key="aux4",
        translation_key="aux4",
        write_fn=_make_write_relay_timer(
            AUX4_TIMER_BLOCK_REGISTER, AUX4_FUNCTION_REGISTER, AUX4_FUNCTION_CODE
        ),
        is_on_fn=_make_is_on_from_key("AUX4"),
        optimistic_fn=_optimistic_relay_timer,
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
        self.key = key
        self._attr_unique_id = f"{self.coordinator.entry.unique_id}_{key.lower()}"

        # The winter_mode switch itself must remain available while winter mode is on.
        if description.ha_setting == _HA_SETTING_WINTER_MODE:
            self._winter_mode_active = False

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch ON."""
        await self._async_set_state(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch OFF."""
        await self._async_set_state(False)

    async def _async_set_state(self, state: bool) -> None:
        """Dispatch turn_on / turn_off via the description callables."""
        desc = self.entity_description
        action = "turn_on" if state else "turn_off"
        if desc.ha_setting not in _HA_SETTING_TYPES and self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active, ignoring %s for %s", action, self.key
            )
            return

        # HA-side settings live entirely outside the Modbus client.
        if desc.ha_setting == _HA_SETTING_WINTER_MODE:
            await self.coordinator.set_winter_mode(state)
            await self.coordinator.async_request_refresh()
            self.async_write_ha_state()
            return
        if desc.ha_setting == _HA_SETTING_AUTO_TIME_SYNC:
            await self.coordinator.set_auto_time_sync(state)
            await self.coordinator.async_request_refresh()
            self.async_write_ha_state()
            return

        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers")
            return

        if desc.write_fn is not None:
            await desc.write_fn(self, client, state)

        if desc.optimistic_fn is not None:
            desc.optimistic_fn(self, state)
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    @property
    @override
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        desc = self.entity_description
        if desc.is_on_fn is not None:
            return desc.is_on_fn(self.coordinator.data)
        if desc.ha_setting == _HA_SETTING_AUTO_TIME_SYNC:
            return getattr(self.coordinator, "auto_time_sync", False)
        if desc.ha_setting == _HA_SETTING_WINTER_MODE:
            return getattr(self.coordinator, "winter_mode", False)
        return False  # pragma: no cover

    @property
    @override
    def available(self) -> bool:
        """Return True if the switch is available."""
        # HA settings are always available (not device state).
        if self.entity_description.ha_setting in _HA_SETTING_TYPES:
            return True
        return super().available
