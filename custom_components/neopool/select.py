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

"""Select platform for the NeoPool integration."""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import logging
from typing import Any, override

from neopool_modbus.capabilities import has_filtvalve, is_hydrolysis_present
from neopool_modbus.decoders import (
    CELL_BOOST_MODE_LABELS,
    FILTRATION_MODE_LABELS,
    FILTRATION_SPEED_LABELS,
    FILTVALVE_MODE_LABELS,
    decode_cell_boost,
    decode_filtvalve_mode,
    get_filtration_pump_type,
)
from neopool_modbus.registers import (
    AUX1_TIMER_BLOCK_REGISTER,
    AUX2_TIMER_BLOCK_REGISTER,
    AUX3_TIMER_BLOCK_REGISTER,
    AUX4_TIMER_BLOCK_REGISTER,
    CELL_BOOST_REGISTER,
    FILTRATION_CONF_REGISTER,
    FILTRATION_MODE_REGISTER,
    FILTRATION_TIMER1_SPEED_MASK,
    FILTRATION_TIMER1_SPEED_SHIFT,
    FILTRATION_TIMER2_SPEED_MASK,
    FILTRATION_TIMER2_SPEED_SHIFT,
    FILTRATION_TIMER3_SPEED_MASK,
    FILTRATION_TIMER3_SPEED_SHIFT,
    FILTVALVE_MODE_REGISTER,
    FILTVALVE_PERIOD_REGISTER,
    INTELLIGENT_FILT_MIN_TIME_REGISTER,
    LIGHT_TIMER_BLOCK_REGISTER,
    MANUAL_FILTRATION_REGISTER,
    RELAY_ACTIVATION_DELAY_REGISTER,
    TimerRelayMode,
)

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, PERIOD_MAP, PERIOD_SECONDS_TO_KEY
from .coordinator import NeoPoolConfigEntry, NeoPoolCoordinator
from .entity import NeoPoolEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

_FILTRATION_SPEED_KEYS = (
    "MBF_PAR_FILTRATION_SPEED",
    "filtration1_speed",
    "filtration2_speed",
    "filtration3_speed",
)


@dataclass(frozen=True, kw_only=True)
class NeoPoolSelectEntityDescription(SelectEntityDescription):
    """Describes a NeoPool select entity."""

    options_map: dict[int, str] = field(default_factory=dict)
    select_type: str | None = None
    register: int | None = None
    mask: int | None = None
    shift: int | None = None
    write_offset: int = 0
    fallback_suffix: str = ""
    timer_field: str = "enable"
    supported_fn: Callable[[dict[str, Any], Mapping[str, Any]], bool] | None = None
    options_fn: (
        Callable[
            ["NeoPoolSelectEntityDescription", dict[str, Any], Mapping[str, Any]],
            list[str],
        ]
        | None
    ) = None
    current_option_fn: (
        Callable[["NeoPoolSelectEntityDescription", dict[str, Any]], str | None] | None
    ) = None


def _filt_mode_options(
    desc: "NeoPoolSelectEntityDescription",
    data: dict[str, Any],
    opts: Mapping[str, Any],
) -> list[str]:
    """Narrow the filtration mode option list based on detected hardware."""
    option_keys = list(desc.options_map.keys())
    no_heating_gpio = not bool(data.get("MBF_PAR_HEATING_GPIO"))
    temp_inactive = not bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
    if no_heating_gpio or temp_inactive:
        # Remove keys for "heating" (2) and "intelligent" (4)
        option_keys = [k for k in option_keys if k not in (2, 4)]
    if temp_inactive:
        # Remove key for "smart"
        option_keys = [k for k in option_keys if k != 3]

    backwash_allowed = has_filtvalve(data)
    # CUSTOM-ONLY START, HACS-only manual override to expose backwash mode.
    backwash_allowed = backwash_allowed or opts.get("enable_backwash_option", False)
    # CUSTOM-ONLY END
    if not backwash_allowed:
        # Keep backwash (13) in the list if the device is currently in that mode.
        current_mode = data.get("MBF_PAR_FILT_MODE")
        if current_mode != 13:
            option_keys = [k for k in option_keys if k != 13]

    return [desc.options_map[k] for k in option_keys]


def _cell_boost_options(
    desc: "NeoPoolSelectEntityDescription",
    data: dict[str, Any],
    opts: Mapping[str, Any],
) -> list[str]:
    """Drop the active_redox option when no redox module is detected."""
    option_keys = list(desc.options_map.keys())
    if not bool(data.get("Redox measurement module detected")):
        option_keys = [k for k in option_keys if k != 2]
    return [desc.options_map[k] for k in option_keys]


def _decode_cell_boost(
    desc: "NeoPoolSelectEntityDescription", data: dict[str, Any]
) -> str | None:
    """Surface the current cell boost mode via the lib decoder."""
    reg_val = data.get("MBF_CELL_BOOST")
    if reg_val is None:  # pragma: no cover
        return None
    return decode_cell_boost(reg_val) or desc.options_map[0]


def _decode_filtration_speed(
    desc: "NeoPoolSelectEntityDescription", data: dict[str, Any]
) -> str | None:
    """Decode the filtration speed from the packed MBF_PAR_FILTRATION_CONF register."""
    raw = data.get("MBF_PAR_FILTRATION_CONF")
    if raw is None:  # pragma: no cover
        return None
    if desc.mask is None or desc.shift is None:  # pragma: no cover
        return None
    speed_value = (int(raw) & desc.mask) >> desc.shift
    return desc.options_map.get(speed_value)


def _decode_filtvalve_mode(
    desc: "NeoPoolSelectEntityDescription", data: dict[str, Any]
) -> str | None:
    """Map the raw MBF_PAR_FILTVALVE_MODE register to its translation key."""
    del desc
    return decode_filtvalve_mode(data.get("MBF_PAR_FILTVALVE_MODE"))


SELECT_DESCRIPTIONS: dict[str, NeoPoolSelectEntityDescription] = {
    "MBF_PAR_FILT_MODE": NeoPoolSelectEntityDescription(
        key="MBF_PAR_FILT_MODE",
        translation_key="filt_mode",
        options_map=FILTRATION_MODE_LABELS,
        register=FILTRATION_MODE_REGISTER,
        options_fn=_filt_mode_options,
    ),
    "MBF_PAR_FILTRATION_SPEED": NeoPoolSelectEntityDescription(
        key="MBF_PAR_FILTRATION_SPEED",
        translation_key="filtration_speed",
        options_map=FILTRATION_SPEED_LABELS,
        register=FILTRATION_CONF_REGISTER,
        shift=4,
        supported_fn=lambda data, opts: bool(  # pragma: no cover
            get_filtration_pump_type(data.get("MBF_PAR_FILTRATION_CONF", 0))
        ),
        current_option_fn=_decode_filtration_speed,
    ),
    "MBF_CELL_BOOST": NeoPoolSelectEntityDescription(
        key="MBF_CELL_BOOST",
        translation_key="cell_boost",
        options_map=CELL_BOOST_MODE_LABELS,
        register=CELL_BOOST_REGISTER,
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: is_hydrolysis_present(data),  # pragma: no cover
        options_fn=_cell_boost_options,
        current_option_fn=_decode_cell_boost,
    ),
    "MBF_PAR_FILTVALVE_MODE": NeoPoolSelectEntityDescription(
        key="MBF_PAR_FILTVALVE_MODE",
        translation_key="filtvalve_mode",
        entity_category=EntityCategory.CONFIG,
        options_map=FILTVALVE_MODE_LABELS,
        register=FILTVALVE_MODE_REGISTER,
        supported_fn=lambda data, opts: has_filtvalve(data),
        current_option_fn=_decode_filtvalve_mode,
    ),
    "MBF_PAR_FILTVALVE_PERIOD_MINUTES": NeoPoolSelectEntityDescription(
        key="MBF_PAR_FILTVALVE_PERIOD_MINUTES",
        translation_key="filtvalve_period_minutes",
        entity_category=EntityCategory.CONFIG,
        select_type="mapped_register",
        fallback_suffix="m",
        options_map={
            1440: "1_day",
            2880: "2_days",
            4320: "3_days",
            5760: "4_days",
            7200: "5_days",
            10080: "1_week",
            20160: "2_weeks",
            30240: "3_weeks",
            40320: "4_weeks",
        },
        register=FILTVALVE_PERIOD_REGISTER,
        supported_fn=lambda data, opts: has_filtvalve(data),
    ),
    "MBF_PAR_INTELLIGENT_FILT_MIN_TIME": NeoPoolSelectEntityDescription(
        key="MBF_PAR_INTELLIGENT_FILT_MIN_TIME",
        translation_key="intelligent_filt_min_time",
        entity_category=EntityCategory.CONFIG,
        select_type="mapped_register",
        fallback_suffix="m",
        options_map={
            120: "2h",
            180: "3h",
            240: "4h",
            300: "5h",
            360: "6h",
            420: "7h",
            480: "8h",
            540: "9h",
            600: "10h",
            660: "11h",
            720: "12h",
        },
        register=INTELLIGENT_FILT_MIN_TIME_REGISTER,
        supported_fn=lambda data, opts: (
            bool(data.get("MBF_PAR_HEATING_GPIO"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
    "MBF_PAR_RELAY_ACTIVATION_DELAY": NeoPoolSelectEntityDescription(
        key="MBF_PAR_RELAY_ACTIVATION_DELAY",
        translation_key="relay_activation_delay",
        entity_category=EntityCategory.CONFIG,
        select_type="mapped_register",
        write_offset=-10,  # Device adds +10s internally
        options_map={
            10: "10",
            20: "20",
            30: "30",
            40: "40",
            50: "50",
            60: "60",
            120: "120",
            180: "180",
            300: "300",
            900: "900",
            1800: "1800",
            3600: "3600",
            10800: "10800",
        },
        register=RELAY_ACTIVATION_DELAY_REGISTER,
        supported_fn=lambda data, opts: (
            data.get("pH measurement module detected") is True
        ),
    ),
    "filtration1_speed": NeoPoolSelectEntityDescription(
        key="filtration1_speed",
        translation_key="filtration1_speed",
        entity_category=EntityCategory.CONFIG,
        options_map=FILTRATION_SPEED_LABELS,
        register=FILTRATION_CONF_REGISTER,
        mask=FILTRATION_TIMER1_SPEED_MASK,
        shift=FILTRATION_TIMER1_SPEED_SHIFT,
        supported_fn=lambda data, opts: (
            bool(opts.get("use_filtration1"))
            and bool(get_filtration_pump_type(data.get("MBF_PAR_FILTRATION_CONF", 0)))
        ),
        current_option_fn=_decode_filtration_speed,
    ),
    "filtration2_speed": NeoPoolSelectEntityDescription(
        key="filtration2_speed",
        translation_key="filtration2_speed",
        entity_category=EntityCategory.CONFIG,
        options_map=FILTRATION_SPEED_LABELS,
        register=FILTRATION_CONF_REGISTER,
        mask=FILTRATION_TIMER2_SPEED_MASK,
        shift=FILTRATION_TIMER2_SPEED_SHIFT,
        supported_fn=lambda data, opts: (
            bool(opts.get("use_filtration2"))
            and bool(get_filtration_pump_type(data.get("MBF_PAR_FILTRATION_CONF", 0)))
        ),
        current_option_fn=_decode_filtration_speed,
    ),
    "filtration3_speed": NeoPoolSelectEntityDescription(
        key="filtration3_speed",
        translation_key="filtration3_speed",
        entity_category=EntityCategory.CONFIG,
        options_map=FILTRATION_SPEED_LABELS,
        register=FILTRATION_CONF_REGISTER,
        mask=FILTRATION_TIMER3_SPEED_MASK,
        shift=FILTRATION_TIMER3_SPEED_SHIFT,
        supported_fn=lambda data, opts: (
            bool(opts.get("use_filtration3"))
            and bool(get_filtration_pump_type(data.get("MBF_PAR_FILTRATION_CONF", 0)))
        ),
        current_option_fn=_decode_filtration_speed,
    ),
    "relay_aux1_period": NeoPoolSelectEntityDescription(
        key="relay_aux1_period",
        translation_key="relay_aux1_period",
        entity_category=EntityCategory.CONFIG,
        select_type="timer_period",
        supported_fn=lambda data, opts: bool(opts.get("use_aux1")),
    ),
    "relay_aux1b_period": NeoPoolSelectEntityDescription(
        key="relay_aux1b_period",
        translation_key="relay_aux1b_period",
        entity_category=EntityCategory.CONFIG,
        select_type="timer_period",
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(opts.get("use_aux1")),
    ),
    "relay_aux2_period": NeoPoolSelectEntityDescription(
        key="relay_aux2_period",
        translation_key="relay_aux2_period",
        entity_category=EntityCategory.CONFIG,
        select_type="timer_period",
        supported_fn=lambda data, opts: bool(opts.get("use_aux2")),
    ),
    "relay_aux2b_period": NeoPoolSelectEntityDescription(
        key="relay_aux2b_period",
        translation_key="relay_aux2b_period",
        entity_category=EntityCategory.CONFIG,
        select_type="timer_period",
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(opts.get("use_aux2")),
    ),
    "relay_aux3_period": NeoPoolSelectEntityDescription(
        key="relay_aux3_period",
        translation_key="relay_aux3_period",
        entity_category=EntityCategory.CONFIG,
        select_type="timer_period",
        supported_fn=lambda data, opts: bool(opts.get("use_aux3")),
    ),
    "relay_aux3b_period": NeoPoolSelectEntityDescription(
        key="relay_aux3b_period",
        translation_key="relay_aux3b_period",
        entity_category=EntityCategory.CONFIG,
        select_type="timer_period",
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(opts.get("use_aux3")),
    ),
    "relay_aux4_period": NeoPoolSelectEntityDescription(
        key="relay_aux4_period",
        translation_key="relay_aux4_period",
        entity_category=EntityCategory.CONFIG,
        select_type="timer_period",
        supported_fn=lambda data, opts: bool(opts.get("use_aux4")),
    ),
    "relay_aux4b_period": NeoPoolSelectEntityDescription(
        key="relay_aux4b_period",
        translation_key="relay_aux4b_period",
        entity_category=EntityCategory.CONFIG,
        select_type="timer_period",
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(opts.get("use_aux4")),
    ),
    "relay_light_period": NeoPoolSelectEntityDescription(
        key="relay_light_period",
        translation_key="relay_light_period",
        entity_category=EntityCategory.CONFIG,
        select_type="timer_period",
        supported_fn=lambda data, opts: bool(opts.get("use_light")),
    ),
    "relay_aux1_mode": NeoPoolSelectEntityDescription(
        key="relay_aux1_mode",
        translation_key="relay_aux1_mode",
        options_map={1: "auto", 4: "manual"},
        register=AUX1_TIMER_BLOCK_REGISTER,
        select_type="relay_mode",
        supported_fn=lambda data, opts: bool(opts.get("use_aux1")),
    ),
    "relay_aux2_mode": NeoPoolSelectEntityDescription(
        key="relay_aux2_mode",
        translation_key="relay_aux2_mode",
        options_map={1: "auto", 4: "manual"},
        register=AUX2_TIMER_BLOCK_REGISTER,
        select_type="relay_mode",
        supported_fn=lambda data, opts: bool(opts.get("use_aux2")),
    ),
    "relay_aux3_mode": NeoPoolSelectEntityDescription(
        key="relay_aux3_mode",
        translation_key="relay_aux3_mode",
        options_map={1: "auto", 4: "manual"},
        register=AUX3_TIMER_BLOCK_REGISTER,
        select_type="relay_mode",
        supported_fn=lambda data, opts: bool(opts.get("use_aux3")),
    ),
    "relay_aux4_mode": NeoPoolSelectEntityDescription(
        key="relay_aux4_mode",
        translation_key="relay_aux4_mode",
        options_map={1: "auto", 4: "manual"},
        register=AUX4_TIMER_BLOCK_REGISTER,
        select_type="relay_mode",
        supported_fn=lambda data, opts: bool(opts.get("use_aux4")),
    ),
    "relay_light_mode": NeoPoolSelectEntityDescription(
        key="relay_light_mode",
        translation_key="relay_light_mode",
        options_map={1: "auto", 4: "manual"},
        register=LIGHT_TIMER_BLOCK_REGISTER,
        select_type="relay_mode",
        supported_fn=lambda data, opts: bool(opts.get("use_light")),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool select entities from a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        NeoPoolSelect(coordinator, entry.entry_id, key, desc)
        for key, desc in SELECT_DESCRIPTIONS.items()
        if desc.supported_fn is None
        or desc.supported_fn(coordinator.data, entry.options)
    )


class NeoPoolSelect(NeoPoolEntity, SelectEntity):
    """Representation of a NeoPool select entity."""

    entity_description: NeoPoolSelectEntityDescription

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        description: NeoPoolSelectEntityDescription,
    ) -> None:
        """Initialize the NeoPool select entity."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._key = key
        self._attr_unique_id = f"{self.coordinator.entry.unique_id}_{key.lower()}"

    async def _select_mapped_register(self, client: Any, option: str) -> None:
        """Reverse-lookup the option label and write to a register."""
        desc = self.entity_description
        reverse_map = {v: k for k, v in desc.options_map.items()}
        value = reverse_map.get(option)
        if value is None:
            try:  # pragma: no cover
                value = int(option.rstrip("ms"))
            except (TypeError, ValueError):  # pragma: no cover
                return
        write_val = value + desc.write_offset
        await client.async_write_register(desc.register, max(0, write_val))
        await asyncio.sleep(0.2)
        self._optimistic_update(value)
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    async def _select_timer_period(self, option: str) -> None:
        """Update the repeat period of a timer via the set_timer service."""
        timer_name = self._key.rsplit("_", 1)[0]
        period_value = PERIOD_MAP.get(option)
        if period_value is None:
            try:  # pragma: no cover
                period_value = int(option)
            except (TypeError, ValueError):  # pragma: no cover
                return
        await self.hass.services.async_call(
            DOMAIN,
            "set_timer",
            {
                "entry_id": self._entry_id,
                "timer": timer_name,
                "period": period_value,
            },
        )

    async def _select_relay_mode(self, client: Any, option: str) -> None:
        """Switch the relay between automatic (timer-driven) and manual modes."""
        timer_name = self._key.rsplit("_", 1)[0]
        current = int(self.coordinator.data.get(f"{timer_name}_enable", 0) or 0)
        if option == "manual" and current in (
            TimerRelayMode.ALWAYS_ON,
            TimerRelayMode.ALWAYS_OFF,
        ):
            # Already in a manual mode; do not touch the physical relay state.
            return
        target = 1 if option == "auto" else TimerRelayMode.ALWAYS_OFF
        await client.write_timer(timer_name, {"enable": target})
        self._optimistic_update(target)
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    async def _select_cell_boost(self, client: Any, option: str) -> None:
        """Encode the cell boost mode into the composite cell-status register."""
        await client.async_set_cell_boost(option)
        await asyncio.sleep(0.2)

    async def _select_filtration_speed(self, client: Any, option: str) -> None:
        """Pack the filtration speed into the composite filtration_conf register."""
        if (
            self._key == "MBF_PAR_FILTRATION_SPEED"
            and self.coordinator.data.get("MBF_PAR_FILT_MODE") != 0
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="filtration_speed_not_manual_mode",
            )
        await client.async_set_filtration_speed(option)
        await asyncio.sleep(0.2)

    async def _select_filt_mode(self, client: Any, option: str) -> None:
        """Drive the MBF_PAR_FILT_MODE transition (with manual-mode exit + backwash log)."""
        current_name = self.coordinator.data.get("filtration_mode")
        has_auto_valve = has_filtvalve(self.coordinator.data)
        if current_name == "manual" and option != "manual":
            if not (option == "backwash" and has_auto_valve):
                await client.async_write_register(MANUAL_FILTRATION_REGISTER, 0)
                await asyncio.sleep(0.1)
        await client.async_set_filtration_mode(option)
        if option == "backwash":
            _LOGGER.info(
                'Your pool "%s" has been switched to the BACKWASH mode!',
                NeoPoolEntity.slugify(self.coordinator.entry.title),
            )
        value = next(
            (k for k, v in self.entity_description.options_map.items() if v == option),
            None,
        )
        self._optimistic_update(value)
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    async def _select_default_register(self, client: Any, option: str) -> None:
        """Write the option's mapped value to the entity's register."""
        desc = self.entity_description
        value = next(
            (k for k, v in desc.options_map.items() if v == option),
            None,
        )
        if value is None:  # pragma: no cover
            return
        await client.async_write_register(desc.register, value)
        self._optimistic_update(value)
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    @override
    async def async_select_option(self, option: str) -> None:
        """Handle option selection by dispatching to the per-type writer."""
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active, ignoring select_option for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers")
            return
        desc = self.entity_description
        if desc.select_type == "mapped_register":
            await self._select_mapped_register(client, option)
            return
        if desc.select_type == "timer_period":
            await self._select_timer_period(option)
            return
        if desc.select_type == "relay_mode":
            await self._select_relay_mode(client, option)
            return
        if self._key == "MBF_CELL_BOOST":
            await self._select_cell_boost(client, option)
            return
        if self._key in _FILTRATION_SPEED_KEYS:
            await self._select_filtration_speed(client, option)
            return
        if self._key == "MBF_PAR_FILT_MODE":
            await self._select_filt_mode(client, option)
            return
        await self._select_default_register(client, option)

    @property
    @override
    def options(self) -> list[str]:
        """Return the list of options for the select entity."""
        desc = self.entity_description
        data = self.coordinator.data

        if (options_fn := desc.options_fn) is not None:
            return options_fn(desc, data, self.coordinator.entry.options)

        if desc.select_type == "timer_period":
            options_list = list(PERIOD_MAP.keys())
            value = data.get(self._key)
            if value is not None:
                current_key = PERIOD_SECONDS_TO_KEY.get(value)
                if current_key and current_key not in options_list:  # pragma: no cover
                    options_list.insert(0, current_key)
            return options_list

        if desc.select_type == "relay_mode":
            options = list(dict.fromkeys(desc.options_map.values()))
            timer_name = self._key.rsplit("_", 1)[0]
            value = data.get(f"{timer_name}_enable")
            if value == 0 and "disabled" not in options:
                options = ["disabled", *options]
            if value == 2 and "auto_linked" not in options:  # pragma: no cover
                options = ["auto_linked", *options]
            return options

        # If device holds an unknown value, prepend raw fallback string.
        if desc.select_type == "mapped_register":
            options = list(desc.options_map.values())
            value = data.get(self._key)
            if (
                isinstance(value, int) and value not in desc.options_map
            ):  # pragma: no cover
                suffix = desc.fallback_suffix
                return [f"{value}{suffix}", *options]
            return options

        return list(desc.options_map.values())

    def _optimistic_update(self, value: int | None) -> None:
        """Apply an optimistic state update to coordinator data."""
        if value is None:  # pragma: no cover
            return
        desc = self.entity_description
        data = self.coordinator.data
        if desc.select_type == "relay_mode":
            timer_name = self._key.rsplit("_", 1)[0]
            data[f"{timer_name}_{desc.timer_field}"] = value
        elif self._key in (
            "MBF_PAR_FILT_MODE",
            "MBF_PAR_FILTVALVE_MODE",
        ):
            data[self._key] = value
        elif desc.select_type == "mapped_register":
            data[self._key] = value

    @property
    @override
    def current_option(self) -> str | None:
        """Return the current option for the select entity."""
        desc = self.entity_description
        data = self.coordinator.data

        if (current_option_fn := desc.current_option_fn) is not None:
            return current_option_fn(desc, data)

        if desc.select_type == "timer_period":
            value = data.get(self._key)
            if value is None:  # pragma: no cover
                return None
            return PERIOD_SECONDS_TO_KEY.get(int(value), str(value))

        if desc.select_type == "relay_mode":
            timer_name = self._key.rsplit("_", 1)[0]
            value = data.get(f"{timer_name}_enable")
            if value is None:  # pragma: no cover
                return None
            int_value = int(value)
            if int_value == 0:
                return "disabled"
            if int_value == 2:  # pragma: no cover
                return "auto_linked"
            if int_value in (TimerRelayMode.ALWAYS_ON, TimerRelayMode.ALWAYS_OFF):
                return "manual"
            return desc.options_map.get(int_value)  # pragma: no cover

        if desc.select_type == "mapped_register":
            value = data.get(self._key)
            if value is None:  # pragma: no cover
                return None
            suffix = desc.fallback_suffix
            return desc.options_map.get(int(value), f"{value}{suffix}")

        value = data.get(self._key)
        if value is None:  # pragma: no cover
            return None
        return desc.options_map.get(value)
