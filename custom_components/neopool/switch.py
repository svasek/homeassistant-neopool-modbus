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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, override

from neopool_modbus import InvalidStateReason, NeoPoolInvalidStateError
from neopool_modbus.capabilities import (
    has_heating_relay,
    is_hydrolysis_present,
    is_temperature_active,
)
from neopool_modbus.exceptions import NeoPoolError
from neopool_modbus.registers import (
    HIDRO_COVER_ENABLE_BIT,
    HIDRO_TEMP_SHUTDOWN_BIT,
    BinaryConfigFlag,
    BitmaskConfigFlag,
    RelayKind,
    TimerRelayMode,
    is_valid_relay_gpio,
)

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_AUTO_TIME_SYNC,
    CONF_USE_AUX1,
    CONF_USE_AUX2,
    CONF_USE_AUX3,
    CONF_USE_AUX4,
    CONF_USE_COVER_SENSOR,
    CONF_WINTER_MODE,
    DOMAIN,
)
from .coordinator import NeoPoolConfigEntry, NeoPoolCoordinator
from .entity import NeoPoolEntity

PARALLEL_UPDATES = 1

# Switch types that are HA-side settings, not device state: they don't need a
# client, don't participate in the winter-mode guard, and stay available even
# while winter mode is active.
_HA_SETTING_WINTER_MODE = CONF_WINTER_MODE
_HA_SETTING_AUTO_TIME_SYNC = CONF_AUTO_TIME_SYNC
_HA_SETTING_TYPES = frozenset({_HA_SETTING_WINTER_MODE, _HA_SETTING_AUTO_TIME_SYNC})


type _WriteFn = Callable[["NeoPoolSwitch", Any, bool], Awaitable[dict[str, Any]]]
type _IsOnFn = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True, kw_only=True)
class NeoPoolSwitchEntityDescription(SwitchEntityDescription):
    """Describes a NeoPool switch entity."""

    ha_setting: str | None = None
    supported_fn: Callable[[dict[str, Any]], bool] | None = None
    write_fn: _WriteFn | None = None
    is_on_fn: _IsOnFn | None = None


# ---------------------------------------------------------------------------
# Write paths (per switch flavor)
# ---------------------------------------------------------------------------


async def _write_manual_filtration(
    entity: "NeoPoolSwitch", client: Any, state: bool
) -> dict[str, Any]:
    """Toggle the manual filtration pump.

    The controller only honours the pump register while it is in manual
    filtration mode; validate up-front so the user gets a translated error
    instead of a raw library exception.
    """
    if entity.coordinator.data.get("MBF_PAR_FILT_MODE") != 0:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="filtration_not_manual_mode",
        )
    return await client.async_set_manual_filtration(state)


_RELAY_TIMER_ENABLE_KEY: dict[RelayKind, str] = {
    RelayKind.AUX1: "relay_aux1_enable",
    RelayKind.AUX2: "relay_aux2_enable",
    RelayKind.AUX3: "relay_aux3_enable",
    RelayKind.AUX4: "relay_aux4_enable",
}


def _make_write_relay_state(relay: RelayKind) -> _WriteFn:
    """Build a write_fn that drives an aux relay via the library."""
    enable_key = _RELAY_TIMER_ENABLE_KEY[relay]

    async def _write(
        entity: "NeoPoolSwitch", client: Any, state: bool
    ) -> dict[str, Any]:
        # Fail-safe: only fire when the relay is confirmed manual.
        if entity.coordinator.data.get(enable_key) not in (
            TimerRelayMode.ALWAYS_ON,
            TimerRelayMode.ALWAYS_OFF,
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="relay_in_auto_mode",
            )
        return await client.async_set_relay_state(relay, state)

    return _write


def _make_write_binary_flag(flag: BinaryConfigFlag) -> _WriteFn:
    """Build a write_fn that toggles a binary configuration flag."""

    async def _write(
        entity: "NeoPoolSwitch", client: Any, state: bool
    ) -> dict[str, Any]:
        return await client.async_set_binary_flag(flag, state)

    return _write


def _make_write_bitmask_flag(flag: BitmaskConfigFlag) -> _WriteFn:
    """Build a write_fn that flips a bit in the shared HIDRO cover register."""

    async def _write(
        entity: "NeoPoolSwitch", client: Any, state: bool
    ) -> dict[str, Any]:
        return await client.async_set_bitmask_flag(flag, state)

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
# Entity descriptions
# ---------------------------------------------------------------------------


SWITCH_DESCRIPTIONS: dict[str, NeoPoolSwitchEntityDescription] = {
    "WINTER_MODE": NeoPoolSwitchEntityDescription(
        key="WINTER_MODE",
        translation_key=CONF_WINTER_MODE,
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
    ),
    "MBF_PAR_CLIMA_ONOFF": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_CLIMA_ONOFF",
        translation_key="clima_onoff",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_binary_flag(BinaryConfigFlag.CLIMA_ONOFF),
        is_on_fn=_make_is_on_int_flag("MBF_PAR_CLIMA_ONOFF"),
        supported_fn=lambda data: (
            has_heating_relay(data) and is_temperature_active(data)
        ),
    ),
    "MBF_PAR_SMART_ANTI_FREEZE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_SMART_ANTI_FREEZE",
        translation_key="smart_anti_freeze",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_binary_flag(BinaryConfigFlag.SMART_ANTI_FREEZE),
        is_on_fn=_make_is_on_int_flag("MBF_PAR_SMART_ANTI_FREEZE"),
        supported_fn=is_temperature_active,
    ),
    "MBF_PAR_UV_MODE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_UV_MODE",
        translation_key="uv_mode",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_binary_flag(BinaryConfigFlag.UV_MODE),
        is_on_fn=_make_is_on_int_flag("MBF_PAR_UV_MODE"),
        supported_fn=lambda data: is_valid_relay_gpio(
            data.get("MBF_PAR_UV_RELAY_GPIO", 0) or 0
        ),
    ),
    "MBF_PAR_HIDRO_COVER_ENABLE": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_HIDRO_COVER_ENABLE",
        translation_key="hidro_cover_enable",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_bitmask_flag(BitmaskConfigFlag.HIDRO_COVER_ENABLE),
        is_on_fn=_make_is_on_bitmask(
            "MBF_PAR_HIDRO_COVER_ENABLE", HIDRO_COVER_ENABLE_BIT
        ),
        supported_fn=is_hydrolysis_present,
    ),
    "MBF_PAR_HIDRO_TEMP_SHUTDOWN": NeoPoolSwitchEntityDescription(
        key="MBF_PAR_HIDRO_TEMP_SHUTDOWN",
        translation_key="hidro_temp_shutdown",
        entity_category=EntityCategory.CONFIG,
        write_fn=_make_write_bitmask_flag(BitmaskConfigFlag.HIDRO_TEMP_SHUTDOWN),
        is_on_fn=_make_is_on_bitmask(
            "MBF_PAR_HIDRO_COVER_ENABLE", HIDRO_TEMP_SHUTDOWN_BIT
        ),
        supported_fn=lambda data: (
            is_hydrolysis_present(data) and is_temperature_active(data)
        ),
    ),
    "aux1": NeoPoolSwitchEntityDescription(
        key="aux1",
        translation_key="aux1",
        write_fn=_make_write_relay_state(RelayKind.AUX1),
        is_on_fn=_make_is_on_from_key("AUX1"),
    ),
    "aux2": NeoPoolSwitchEntityDescription(
        key="aux2",
        translation_key="aux2",
        write_fn=_make_write_relay_state(RelayKind.AUX2),
        is_on_fn=_make_is_on_from_key("AUX2"),
    ),
    "aux3": NeoPoolSwitchEntityDescription(
        key="aux3",
        translation_key="aux3",
        write_fn=_make_write_relay_state(RelayKind.AUX3),
        is_on_fn=_make_is_on_from_key("AUX3"),
    ),
    "aux4": NeoPoolSwitchEntityDescription(
        key="aux4",
        translation_key="aux4",
        write_fn=_make_write_relay_state(RelayKind.AUX4),
        is_on_fn=_make_is_on_from_key("AUX4"),
    ),
}


# Entities gated on a config-entry option (in addition to their supported_fn).
_ENTITY_OPTION_KEY: dict[str, str] = {
    "MBF_PAR_HIDRO_COVER_ENABLE": CONF_USE_COVER_SENSOR,
    "MBF_PAR_HIDRO_TEMP_SHUTDOWN": CONF_USE_COVER_SENSOR,
    "aux1": CONF_USE_AUX1,
    "aux2": CONF_USE_AUX2,
    "aux3": CONF_USE_AUX3,
    "aux4": CONF_USE_AUX4,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool switches from a config entry."""
    coordinator = entry.runtime_data
    options = entry.options

    async_add_entities(
        NeoPoolSwitch(coordinator, key, desc)
        for key, desc in SWITCH_DESCRIPTIONS.items()
        if (
            (option_key := _ENTITY_OPTION_KEY.get(key)) is None
            or bool(options.get(option_key))
        )
        and (desc.supported_fn is None or desc.supported_fn(coordinator.data))
    )


# Translation key used when the library's rejection has no reason attached
# (older lib versions) or an unknown reason surfaces.
_INVALID_STATE_TRANSLATION_KEY: dict[InvalidStateReason, str] = {
    InvalidStateReason.RELAY_IN_AUTO_MODE: "relay_in_auto_mode",
    InvalidStateReason.FILTRATION_NOT_IN_MANUAL_MODE: "filtration_not_manual_mode",
}


class NeoPoolSwitch(NeoPoolEntity, SwitchEntity):
    """Representation of a NeoPool switch entity."""

    entity_description: NeoPoolSwitchEntityDescription

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        key: str,
        description: NeoPoolSwitchEntityDescription,
    ) -> None:
        """Initialize the NeoPool switch entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self.key = key
        self._attr_unique_id = (
            f"{self.coordinator.config_entry.unique_id}_{key.lower()}"
        )

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

        if (
            desc.write_fn is None
        ):  # pragma: no cover - all non-HA switches wire write_fn
            return

        try:
            overrides = await desc.write_fn(self, self.coordinator.client, state)
        except NeoPoolInvalidStateError as err:
            translation_key = _INVALID_STATE_TRANSLATION_KEY.get(
                err.reason, "relay_in_auto_mode"
            )
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=translation_key,
            ) from err
        except (NeoPoolError, OSError, TimeoutError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="modbus_communication_error",
                translation_placeholders={"error": str(err)},
            ) from err

        # Merge the library's optimistic-update dict into the coordinator cache
        # so the UI reflects the new state immediately.
        self.coordinator.async_set_updated_data({**self.coordinator.data, **overrides})
        self.coordinator.request_refresh_with_followup()

    @property
    @override
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        desc = self.entity_description
        if desc.is_on_fn is not None:
            return desc.is_on_fn(self.coordinator.data)
        if desc.ha_setting == _HA_SETTING_AUTO_TIME_SYNC:
            return getattr(self.coordinator, CONF_AUTO_TIME_SYNC, False)
        if desc.ha_setting == _HA_SETTING_WINTER_MODE:
            return getattr(self.coordinator, CONF_WINTER_MODE, False)
        return False  # pragma: no cover

    @property
    @override
    def available(self) -> bool:
        """Return True if the switch is available."""
        # HA settings are always available (not device state).
        if self.entity_description.ha_setting in _HA_SETTING_TYPES:
            return True
        return super().available
