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

"""VistaPool Integration for Home Assistant - Number Module"""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VistaPoolConfigEntry
from .const import (
    HEATING_SETPOINT_REGISTER,
    INTELLIGENT_SETPOINT_REGISTER,
    NUMBER_DEFINITIONS,
    is_valid_relay_gpio,
)
from .entity import VistaPoolEntity
from .helpers import is_hydrolysis_in_percent

_LOGGER = logging.getLogger(__name__)


def _should_skip_number(
    key: str,
    props: dict[str, Any],
    data: dict[str, Any],
    entry_options: Mapping[str, Any],
) -> bool:
    """Return True if a number entity should not be created."""
    # Only create number entities if enabled in options
    option_key = props.get("option")
    if option_key and not entry_options.get(option_key, False):
        return True
    # Skip smart temperature numbers if no temperature sensor is active
    if key in ("MBF_PAR_SMART_TEMP_HIGH", "MBF_PAR_SMART_TEMP_LOW"):
        if not bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE")):
            return True
    # Conditionally add heating setpoint only if heating relay is assigned.
    # Only enforce when the GPIO key is present in data; a missing key
    # (e.g. old capability snapshot) must not suppress the entity.
    if key == "MBF_PAR_HEATING_TEMP":
        if "MBF_PAR_HEATING_GPIO" in data and not is_valid_relay_gpio(
            data["MBF_PAR_HEATING_GPIO"] or 0
        ):
            return True
        if not bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE")):
            return True
    # Conditionally add pH high limit only if acid pump relay is assigned.
    # Only enforce when the GPIO key is present in data.
    if key == "MBF_PAR_PH1":
        if "MBF_PAR_PH_ACID_RELAY_GPIO" in data and not is_valid_relay_gpio(
            data["MBF_PAR_PH_ACID_RELAY_GPIO"] or 0
        ):
            return True
    # Conditionally add pH low limit only if base pump relay is assigned.
    # Only enforce when the GPIO key is present in data.
    if key == "MBF_PAR_PH2":
        if "MBF_PAR_PH_BASE_RELAY_GPIO" in data and not is_valid_relay_gpio(
            data["MBF_PAR_PH_BASE_RELAY_GPIO"] or 0
        ):
            return True
    # Conditionally add redox setpoint only if redox module is detected
    if key == "MBF_PAR_RX1":
        if not bool(data.get("Redox measurement module detected")):
            return True
    # Conditionally add chlorine setpoint only if chlorine module is detected
    if key == "MBF_PAR_CL1":
        if not bool(data.get("Chlorine measurement module detected")):
            return True
    # Skip hydrolysis target if no hydrolysis module is installed
    if key == "MBF_PAR_HIDRO" and not data.get("Hydrolysis module detected"):
        return True
    # Cover reduction numbers only visible when hydrolysis module present
    if key == "MBF_PAR_HIDRO_COVER_REDUCTION":
        if not data.get("Hydrolysis module detected"):
            return True
    # Shutdown temperature needs hydrolysis and temperature sensor
    if key == "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE":
        if (
            not data.get("Hydrolysis module detected")
            or data.get("MBF_PAR_TEMPERATURE_ACTIVE", 0) == 0
        ):
            return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VistaPool number entities from a config entry."""
    coordinator = entry.runtime_data
    entry_id = entry.entry_id

    entities = []

    if coordinator.data is None:
        _LOGGER.warning("No data from Modbus, skipping number setup!")
        return

    for key, props in NUMBER_DEFINITIONS.items():
        if _should_skip_number(key, props, coordinator.data, entry.options):
            continue

        entities.append(VistaPoolNumber(coordinator, entry_id, key, props))

    async_add_entities(entities)


class VistaPoolNumber(VistaPoolEntity, NumberEntity):  # type: ignore[reportIncompatibleVariableOverride]
    """Representation of a VistaPool number entity."""

    def __init__(self, coordinator, entry_id, key, props) -> None:
        """Initialize the VistaPool number entity."""
        super().__init__(coordinator, entry_id)
        self._key = key
        self._register = props.get("register", None)
        self._scale = props.get("scale", 1.0)
        # Optional bitmask support for compound registers
        self._mask: int | None = props.get("mask", None)
        self._shift: int = props.get("shift", 0)
        self._data_key: str = props.get("data_key", key)

        self._attr_suggested_object_id = (
            f"{self.coordinator.device_slug}_{VistaPoolEntity.slugify(self._key)}"
        )
        # Use entry.unique_id (serial-based in v2+) for stable identity, fallback to entry_id
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{self._key.lower()}"
        self._attr_translation_key = VistaPoolEntity.slugify(self._key)

        self._attr_native_unit_of_measurement = props.get("unit", None)
        self._attr_native_min_value = props.get("min", None)
        self._attr_native_max_value = props.get("max", None)
        self._attr_native_step = props.get("step", 1.0)
        self._attr_mode = NumberMode.BOX

        self._attr_device_class = props.get("device_class") or None
        self._attr_entity_category = props.get("entity_category") or None
        self._attr_icon = props.get("icon")
        self._pending_write_task = None
        self._pending_value = None
        self._debounce_delay = 2.0

        _LOGGER.debug(
            "INIT: suggested_object_id=%s, translation_key=%s, has_entity_name=%s",
            self._attr_suggested_object_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )

    async def async_added_to_hass(self) -> None:
        """Run when the entity is added to hass."""
        _LOGGER.debug(
            "ADDED: entity_id=%s, translation_key=%s, has_entity_name=%s",
            self.entity_id,
            self._attr_translation_key,
            getattr(self, "has_entity_name", None),
        )
        client = getattr(self.coordinator, "client", None)
        if client is None:
            _LOGGER.error("Modbus client not available for reading registers.")
            return
        await super().async_added_to_hass()

        # Read full register map and get the value using string key
        # Use coordinator cache instead of hitting Modbus again
        val = self.coordinator.data.get(self._data_key)
        if val is not None and self._mask is not None:
            val = (int(val) & self._mask) >> self._shift
        self._attr_native_value = (
            round(val, 2) if isinstance(val, (int, float)) else None
        )

        self.async_write_ha_state()

    async def async_set_native_value(self, value: float | int | str) -> None:
        """Set the native value of the number entity."""
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active — ignoring set_native_value for %s", self._key
            )
            return
        self._pending_value = value
        if (
            self._pending_write_task is not None and not self._pending_write_task.done()
        ):  # pragma: no cover
            self._pending_write_task.cancel()
        self._pending_write_task = asyncio.create_task(self._debounced_write())
        # Optimistic UI update: show the pending value immediately.
        # The actual Modbus write and coordinator refresh happen after the
        # debounce delay inside _debounced_write().
        self.async_write_ha_state()

    async def _debounced_write(self) -> None:
        """Debounced write to the Modbus register."""
        client = getattr(self.coordinator, "client", None)
        if client is None:
            _LOGGER.error("Modbus client not available for writing registers.")
            return
        try:
            await asyncio.sleep(self._debounce_delay)
            if self.coordinator.winter_mode:
                _LOGGER.warning(
                    "Winter mode is active — debounced write cancelled for %s",
                    self._key,
                )
                return
            raw = int(self._pending_value * self._scale)
            if self._mask is not None:
                # Read-Modify-Write: preserve bits outside our mask
                current = int(self.coordinator.data.get(self._data_key, 0) or 0)
                raw = (current & ~self._mask) | ((raw << self._shift) & self._mask)
                await client.async_write_register(self._register, raw, apply=True)
            # If user changes heating or intelligent setpoint, mirror the value
            # to both registers so a single UI control can keep them in sync.
            elif self._register in (
                HEATING_SETPOINT_REGISTER,
                INTELLIGENT_SETPOINT_REGISTER,
            ):
                # Write both sequentially to ensure both modes share same target
                await client.async_write_register(HEATING_SETPOINT_REGISTER, raw)
                await client.async_write_register(
                    INTELLIGENT_SETPOINT_REGISTER, raw, apply=True
                )
            else:
                await client.async_write_register(self._register, raw, apply=True)
            await self.coordinator.async_request_refresh()
        except asyncio.CancelledError:  # pragma: no cover
            pass

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested display precision for the number value."""
        if self._key == "MBF_PAR_HIDRO":
            # 0 decimals in percent mode, 1 decimal in g/h mode
            return 0 if is_hydrolysis_in_percent(self.coordinator.data) else 1
        if self._key == "MBF_PAR_HEATING_TEMP":
            return 0
        return None

    @property
    def icon(self) -> str | None:  # type: ignore[override]
        """Return custom icon depending on state."""
        return self._attr_icon or None

    @property
    def native_value(self) -> float | int | str | None:  # type: ignore[override]
        """Return the actual number value."""
        raw = self.coordinator.data.get(self._data_key)
        if raw is not None and self._mask is not None:
            raw = (int(raw) & self._mask) >> self._shift
        if (
            self.suggested_display_precision == 0 and raw is not None
        ):  # pragma: no cover
            return int(round(raw))
        if raw is None:
            return self._attr_native_value  # fallback if coordinator is not updated yet
        return round(raw, 2)

    # Property to set correct native value for hydrolysis
    @property
    def native_unit_of_measurement(self) -> str | None:  # type: ignore[override]
        """Return the unit of measurement for the number value."""
        if self._key == "MBF_PAR_HIDRO":
            # Dynamically determine unit based on machine configuration using the same logic as Tasmota
            return "%" if is_hydrolysis_in_percent(self.coordinator.data) else "g/h"
        return self._attr_native_unit_of_measurement

    # Property to set correct native max value for hydrolysis
    @property
    def native_max_value(self) -> float | None:  # type: ignore[override]
        """Return the maximum value for the number entity."""
        if self._key == "MBF_PAR_HIDRO":
            hidro_nom = self.coordinator.data.get("MBF_PAR_HIDRO_NOM")
            if hidro_nom is not None:
                return hidro_nom
        return self._attr_native_max_value

    @property
    def native_step(self) -> float | None:  # type: ignore[override]
        """Return the step value for the number entity."""
        if self._key == "MBF_PAR_HIDRO":
            # 1.0 step in percent mode, 0.1 step in g/h mode (matches display precision and register scale)
            return 1.0 if is_hydrolysis_in_percent(self.coordinator.data) else 0.1
        return self._attr_native_step
