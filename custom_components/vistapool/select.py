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

"""VistaPool Integration for Home Assistant - Select Module"""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VistaPoolConfigEntry
from .const import (
    DEFAULT_TIMER_RESOLUTION,
    DOMAIN,
    MANUAL_FILTRATION_REGISTER,
    PERIOD_MAP,
    PERIOD_SECONDS_TO_KEY,
    SELECT_DEFINITIONS,
)
from .entity import VistaPoolEntity
from .helpers import (
    generate_time_options,
    get_filtration_pump_type,
    has_filtvalve,
    hhmm_to_seconds,
    seconds_to_hhmm,
)

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

_FILTRATION_SPEED_KEYS = (
    "MBF_PAR_FILTRATION_SPEED",
    "filtration1_speed",
    "filtration2_speed",
    "filtration3_speed",
)


def _should_skip_select(
    key: str,
    props: dict[str, Any],
    data: dict[str, Any],
    entry_options: Mapping[str, Any],
) -> bool:
    """Return True if a select entity should not be created."""
    # Skip filtration speed selects if pump type is not set
    if key in _FILTRATION_SPEED_KEYS and not bool(
        get_filtration_pump_type(data.get("MBF_PAR_FILTRATION_CONF", 0))
    ):
        return True  # pragma: no cover
    # Skip boost mode select if model does not support "Hydro/Electrolysis"
    if key == "MBF_CELL_BOOST":
        mbf_par_model = data.get("MBF_PAR_MODEL", 0)
        if not (mbf_par_model & 0x0002):  # pragma: no cover
            return True
    # Conditionally add Intelligent min. filtration time only if heating relay is assigned
    if key == "MBF_PAR_INTELLIGENT_FILT_MIN_TIME":
        if not bool(data.get("MBF_PAR_HEATING_GPIO")) or not bool(
            data.get("MBF_PAR_TEMPERATURE_ACTIVE")
        ):
            return True
    # Besgo-valve selects: only when a Besgo valve is detected
    if key in (
        "MBF_PAR_FILTVALVE_PERIOD_MINUTES",
        "MBF_PAR_FILTVALVE_MODE",
    ) and not has_filtvalve(data):
        return True
    # Skip relay activation delay if no pH module is detected
    if (
        key == "MBF_PAR_RELAY_ACTIVATION_DELAY"
        and data.get("pH measurement module detected") is not True
    ):
        return True
    # Option-gated select
    option_key = props.get("option")
    if option_key and not entry_options.get(option_key, False):
        return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VistaPool select entities from a config entry."""
    coordinator = entry.runtime_data
    entry_id = entry.entry_id
    entities = []

    if coordinator.data is None:
        _LOGGER.warning("No data from Modbus, skipping select setup!")
        return

    for key, props in SELECT_DEFINITIONS.items():
        if _should_skip_select(key, props, coordinator.data, entry.options):
            continue

        entities.append(VistaPoolSelect(coordinator, entry_id, key, props))
    async_add_entities(entities)


class VistaPoolSelect(VistaPoolEntity, SelectEntity):  # type: ignore[reportIncompatibleVariableOverride]
    """Representation of a VistaPool select entity."""

    def __init__(self, coordinator, entry_id, key, props) -> None:
        """Initialize the VistaPool select entity."""
        super().__init__(coordinator, entry_id)
        self._key = key
        self._attr_suggested_object_id = (
            f"{self.coordinator.device_slug}_{VistaPoolEntity.slugify(self._key)}"
        )
        # Use entry.unique_id (serial-based in v2+) for stable identity, fallback to entry_id
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{self._key.lower()}"
        self._attr_translation_key = VistaPoolEntity.slugify(self._key)

        self._attr_icon = props.get("icon") or None
        self._options_map = dict(props.get("options_map") or {})
        self._attr_entity_category = props.get("entity_category") or None
        self._select_type = props.get("select_type") or None
        self._register = props.get("register") or None
        self._attr_mask = props.get("mask") or None
        self._attr_shift = props.get("shift") or None
        self._props = props

        # Disable some entities by default. Mostly for secondary timers.
        if any(
            self._key.startswith(f"relay_aux{n}b") for n in range(1, 5)
        ) or self._key.startswith("MBF_CELL_BOOST"):
            self._attr_entity_registry_enabled_default = False

        _LOGGER.debug(
            "INIT: suggested_object_id=%s, translation_key=%s, has_entity_name=%s",
            self._attr_suggested_object_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active — ignoring select_option for %s", self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers.")
            return
        # Mapped register selects (INTELLIGENT_FILT_MIN_TIME, FILTVALVE_PERIOD_MINUTES,
        # RELAY_ACTIVATION_DELAY): reverse-lookup option label to register value,
        # apply optional write_offset, and write to register.
        if self._select_type == "mapped_register":
            reverse_map = {v: k for k, v in self._options_map.items()}
            value = reverse_map.get(option)
            if value is None:
                try:
                    value = int(option.rstrip("ms"))
                except Exception:  # pragma: no cover
                    return
            write_val = value + self._props.get("write_offset", 0)
            await client.async_write_register(self._register, max(0, write_val))
            await asyncio.sleep(0.2)
            self._optimistic_update(value)
            if self.coordinator.data is not None:
                self.coordinator.async_set_updated_data(self.coordinator.data)
            self.coordinator.request_refresh_with_followup()
            return
        if self._select_type == "timer_time":
            timer_name, field = self._key.rsplit("_", 1)
            entry_id = self._entry_id
            data = self.coordinator.data
            if field == "start":
                start = option
                stop = seconds_to_hhmm(data.get(f"{timer_name}_stop", 0))
            elif field == "stop":
                start = seconds_to_hhmm(data.get(f"{timer_name}_start", 0))
                stop = option
            else:  # pragma: no cover
                return

            await self.hass.services.async_call(
                DOMAIN,
                "set_timer",
                {
                    "entry_id": entry_id,
                    "timer": timer_name,
                    "start": start,
                    "stop": stop,
                },
            )
            return

        if self._select_type == "timer_period":
            timer_name = self._key.rsplit("_", 1)[0]  # for example, "relay_aux1"
            entry_id = self._entry_id

            period_value = PERIOD_MAP.get(option)
            if period_value is None:
                # fallback to integer conversion
                try:
                    period_value = int(option)
                except Exception:  # pragma: no cover
                    return

            await self.hass.services.async_call(
                DOMAIN,
                "set_timer",
                {
                    "entry_id": entry_id,
                    "timer": timer_name,
                    "period": period_value,
                },
            )
            return

        if self._select_type == "relay_mode":
            timer_field = self._props.get("timer_field", "enable")
            timer_name = self._key.rsplit("_", 1)[0]  # for example, "relay_aux1"
            reverse_map = {v: k for k, v in self._options_map.items()}
            value = reverse_map.get(option)
            if value is None:  # pragma: no cover
                return
            entry_id = self._entry_id
            await self.hass.services.async_call(
                DOMAIN,
                "set_timer",
                {
                    "entry_id": entry_id,
                    "timer": timer_name,
                    timer_field: value,
                },
            )
            self._optimistic_update(value)
            if self.coordinator.data is not None:
                self.coordinator.async_set_updated_data(self.coordinator.data)
            return

        if self._key == "MBF_CELL_BOOST":
            value = None
            for k, v in self._options_map.items():
                if v == option:
                    value = k
                    break

            reg = SELECT_DEFINITIONS[self._key]["register"]
            if value is not None:
                if value == 0:  # pragma: no cover
                    write_val = 0
                elif value == 1:  # pragma: no cover
                    write_val = (
                        0x0500 | 0x00A0 | 0x8000
                    )  # 0x85A0 = Boost active, redox control DISABLED
                elif value == 2:
                    write_val = (
                        0x0500 | 0x00A0
                    )  # 0x05A0 = Boost active, redox control ENABLED
                else:  # pragma: no cover
                    return

                await client.async_write_register(reg, write_val)
                await asyncio.sleep(0.2)
            return

        if self._key in _FILTRATION_SPEED_KEYS:
            rev_map = {v: k for k, v in self._options_map.items()}
            value = rev_map.get(option)
            if value is None:  # pragma: no cover
                return

            current = self.coordinator.data.get("MBF_PAR_FILTRATION_CONF")
            if current is None or self._attr_mask is None or self._attr_shift is None:
                return  # pragma: no cover

            new_val = (current & ~self._attr_mask) | (value << self._attr_shift)
            _LOGGER.debug(
                "Setting new filtration speed: current=0x%04X, new_val=0x%04X, mask=0x%04X, shift=%s",
                current,
                new_val,
                self._attr_mask,
                self._attr_shift,
            )
            await client.async_write_register(self._register, new_val, apply=True)
            await asyncio.sleep(0.2)
            return

        value = None
        for k, v in self._options_map.items():
            if v == option:
                value = k
                break

        if value is not None:
            # Special: MBF_PAR_FILT_MODE needs to handle manual → other
            # We have to turn off manual filtration first (set register 0x0413 to 0)
            # and then set the new mode
            if self._key == "MBF_PAR_FILT_MODE":
                current_mode = self.coordinator.data.get(self._key)
                current_name = self._options_map.get(current_mode)
                has_auto_valve = has_filtvalve(self.coordinator.data)
                # When leaving manual mode, stop the pump first - EXCEPT when
                # switching to backwash on a device WITH an automatic valve (Besgo).
                # In that case the pump must keep running so the valve opens correctly.
                # For manual valve users the pump must stop so the user can safely
                # rotate the multi-way valve before the backwash cycle begins.
                if current_name == "manual" and option != "manual":
                    if not (option == "backwash" and has_auto_valve):
                        await client.async_write_register(MANUAL_FILTRATION_REGISTER, 0)
                        await asyncio.sleep(0.1)
            # Set the new mode
            await client.async_write_register(self._register, value)
            if self._key == "MBF_PAR_FILT_MODE" and option == "backwash":
                _LOGGER.info(
                    f'Your pool "{VistaPoolEntity.slugify(self.coordinator.device_name)}" has been switched to the BACKWASH mode!'
                )

            # Optimistic update + schedule follow-up
            self._optimistic_update(value)
            if self.coordinator.data is not None:
                self.coordinator.async_set_updated_data(self.coordinator.data)
            self.coordinator.request_refresh_with_followup()

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
    def options(self) -> list[str]:  # type: ignore[override]
        """Return the list of options for the select entity."""
        option_keys = list(self._options_map.keys())

        # Hide heating and intelligent if either is not supported:
        # - requires heating relay assigned (MBF_PAR_HEATING_GPIO)
        # - requires active temperature sensor (MBF_PAR_TEMPERATURE_ACTIVE != 0)
        if self._key == "MBF_PAR_FILT_MODE":
            no_heating_gpio = not bool(
                self.coordinator.data.get("MBF_PAR_HEATING_GPIO")
            )
            temp_inactive = not bool(
                self.coordinator.data.get("MBF_PAR_TEMPERATURE_ACTIVE")
            )
            if no_heating_gpio or temp_inactive:
                # Remove keys for "heating" (2) and "intelligent" (4)
                option_keys = [k for k in option_keys if k not in (2, 4)]

        # Hide smart if temperature sensor is not active
        if self._key == "MBF_PAR_FILT_MODE" and not bool(
            self.coordinator.data.get("MBF_PAR_TEMPERATURE_ACTIVE")
        ):
            # Remove key for "smart"
            option_keys = [k for k in option_keys if k != 3]

        # Show backwash option only if:
        # - explicitly enabled in advanced config options, OR
        # - a Besgo automatic filter valve is configured
        # The mapping (13 -> "backwash") is always present in options_map so that
        # current_option and async_select_option work correctly regardless of
        # whether options() has been evaluated first.
        if self._key == "MBF_PAR_FILT_MODE":
            backwash_allowed = self.coordinator.entry.options.get(
                "enable_backwash_option", False
            ) or has_filtvalve(self.coordinator.data)
            if not backwash_allowed:
                # Keep backwash (13) in the list if the device is currently in that
                # mode, so current_option always matches one of the available options.
                current_mode = self.coordinator.data.get("MBF_PAR_FILT_MODE")
                if current_mode != 13:
                    option_keys = [k for k in option_keys if k != 13]

        # Hide "Active (Redox control)" if no Redox module
        if self._key == "MBF_CELL_BOOST" and not bool(
            self.coordinator.data.get("Redox measurement module detected")
        ):
            option_keys = [k for k in option_keys if k != 2]

        # Generate options list based on config entry options
        # Also, handle Timer options in cases where doesn't fit the options_map
        if self._select_type == "timer_time":
            resolution = max(
                1,
                self.coordinator.entry.options.get(
                    "timer_resolution", DEFAULT_TIMER_RESOLUTION
                ),
            )
            options_map = {
                hhmm_to_seconds(opt): opt for opt in generate_time_options(resolution)
            }
            option_keys = list(options_map.keys())

            value = self.coordinator.data.get(self._key)
            options_list = [options_map[k] for k in option_keys]
            if value is not None:
                current_hhmm = seconds_to_hhmm(value)
                if current_hhmm not in options_list:  # pragma: no cover
                    return [current_hhmm] + options_list
            return options_list

        # Handle Timer Period options
        # If the select type is "timer_period", we need to generate a list of periods
        # based on the PERIOD_MAP and the current value in the coordinator data
        if self._select_type == "timer_period":
            options_list = list(PERIOD_MAP.keys())
            value = self.coordinator.data.get(f"{self._key}")
            if value is not None:
                current_key = PERIOD_SECONDS_TO_KEY.get(value)
                if current_key and current_key not in options_list:  # pragma: no cover
                    options_list.insert(0, current_key)
            return options_list

        if self._select_type == "relay_mode":
            options = list(dict.fromkeys(self._options_map.values()))
            timer_name = self._key.rsplit("_", 1)[0]
            value = self.coordinator.data.get(f"{timer_name}_enable")
            # Dynamically add "disabled" at the beginning if enable==0
            if value == 0 and "disabled" not in options:
                options = ["disabled"] + options
            if value == 2 and "auto_linked" not in options:  # pragma: no cover
                options = ["auto_linked"] + options
            return options

        # Mapped register selects: return labels from options_map.
        # If device holds an unknown value, prepend raw fallback string.
        if self._select_type == "mapped_register":
            options = [self._options_map[k] for k in option_keys]
            value = self.coordinator.data.get(self._key)
            if isinstance(value, int) and value not in self._options_map:
                suffix = self._props.get("fallback_suffix", "")
                return [f"{value}{suffix}"] + options
            return options

        return [self._options_map[k] for k in option_keys]

    def _optimistic_update(self, value: int | None) -> None:
        """Apply an optimistic state update to coordinator data."""
        data = self.coordinator.data
        if data is None or value is None:
            return
        if self._select_type == "relay_mode":
            timer_field = self._props.get("timer_field", "enable")
            timer_name = self._key.rsplit("_", 1)[0]
            data[f"{timer_name}_{timer_field}"] = value
        elif self._key in (
            "MBF_PAR_FILT_MODE",
            "MBF_PAR_FILTVALVE_MODE",
        ):
            data[self._key] = value
        elif self._select_type == "mapped_register":
            data[self._key] = value

    @property
    def current_option(self) -> str | None:  # type: ignore[override]
        """Return the current option for the select entity."""
        if self._key == "MBF_CELL_BOOST":
            reg_val = self.coordinator.data.get(self._key)
            if reg_val is None:  # pragma: no cover
                return None
            # 0: Inactive
            if reg_val == 0:
                return self._options_map[0]
            # 1: Active (redox control disabled) – bit 0x8000 set
            elif reg_val & 0x8000:
                return self._options_map[1]
            # 2: Active (Redox control) – bits 0x0500 | 0x00A0 set and 0x8000 NOT set
            elif (reg_val & (0x0500 | 0x00A0)) == (0x0500 | 0x00A0):
                return self._options_map[2]
            # fallback (should not occur)
            return self._options_map[0]

        if self._key in _FILTRATION_SPEED_KEYS:
            raw = self.coordinator.data.get("MBF_PAR_FILTRATION_CONF")
            if raw is None:  # pragma: no cover
                return None
            if self._attr_mask is None or self._attr_shift is None:  # pragma: no cover
                return None
            value = (raw & self._attr_mask) >> self._attr_shift
            return self._options_map.get(value)

        if self._select_type == "timer_period":
            value = self.coordinator.data.get(self._key)
            if value is None:  # pragma: no cover
                return None
            return PERIOD_SECONDS_TO_KEY.get(value, str(value))

        if self._select_type == "relay_mode":
            # Get the timer_block and timer_field from properties
            timer_name = self._key.rsplit("_", 1)[0]
            value = self.coordinator.data.get(f"{timer_name}_enable")
            if value == 0:
                return "disabled"
            if value == 2:
                return "auto_linked"
            return self._options_map.get(value)  # pragma: no cover

        # Mapped register selects: return label from options_map or raw fallback
        if self._select_type == "mapped_register":
            value = self.coordinator.data.get(self._key)
            if value is None:  # pragma: no cover
                return None
            suffix = self._props.get("fallback_suffix", "")
            return self._options_map.get(value, f"{value}{suffix}")

        if self._key == "MBF_PAR_FILTVALVE_MODE":
            value = self.coordinator.data.get(self._key)
            return self._options_map.get(value)

        value = self.coordinator.data.get(self._key)
        if value is None:  # pragma: no cover
            return None
        if self._options_map:
            # If not exactly in options_map, always return current HH:MM
            return self._options_map.get(value) or seconds_to_hhmm(value)
        return seconds_to_hhmm(value)  # pragma: no cover

    @property
    def available(self) -> bool:  # type: ignore[override]
        if self._key == "MBF_PAR_FILTRATION_SPEED":
            if not super().available:
                return False
            return self.coordinator.data.get("MBF_PAR_FILT_MODE", 0) == 0
        return super().available
