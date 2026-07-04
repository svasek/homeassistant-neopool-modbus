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

"""Number platform for the NeoPool integration."""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import logging
from typing import Any, override

from neopool_modbus.decoders import is_hydrolysis_in_percent
from neopool_modbus.registers import (
    CHLORINE_SETPOINT_REGISTER,
    HEATING_SETPOINT_REGISTER,
    HIDRO_COVER_REDUCTION_MASK,
    HIDRO_COVER_REDUCTION_SHIFT,
    HIDRO_COVER_REGISTER,
    HIDRO_SETPOINT_REGISTER,
    HIDRO_SHUTDOWN_TEMP_MASK,
    HIDRO_SHUTDOWN_TEMP_SHIFT,
    INTELLIGENT_SETPOINT_REGISTER,
    PH_MAX_SETPOINT_REGISTER,
    PH_MIN_SETPOINT_REGISTER,
    REDOX_SETPOINT_REGISTER,
    SMART_TEMP_HIGH_REGISTER,
    SMART_TEMP_LOW_REGISTER,
    is_valid_relay_gpio,
)

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NeoPoolConfigEntry, NeoPoolCoordinator
from .entity import NeoPoolEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class NeoPoolNumberEntityDescription(NumberEntityDescription):
    """Describes a NeoPool number entity."""

    register: int = 0
    scale: float = 1.0
    mask: int | None = None
    shift: int = 0
    data_key: str | None = None
    supported_fn: Callable[[dict[str, Any], Mapping[str, Any]], bool] | None = None
    precision_fn: Callable[[dict[str, Any]], int | None] | None = None
    unit_fn: Callable[[dict[str, Any]], str | None] | None = None
    max_fn: Callable[[dict[str, Any]], float | None] | None = None
    step_fn: Callable[[dict[str, Any]], float | None] | None = None


def _support_heating_temp(data: dict[str, Any], opts: Mapping[str, Any]) -> bool:
    if "MBF_PAR_HEATING_GPIO" in data and not is_valid_relay_gpio(
        data["MBF_PAR_HEATING_GPIO"] or 0
    ):
        return False
    return bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))


def _hidro_precision(data: dict[str, Any]) -> int:
    """0 decimals in percent mode, 1 decimal in g/h mode."""
    return 0 if is_hydrolysis_in_percent(data) else 1


def _hidro_unit(data: dict[str, Any]) -> str:
    """Surface the hydrolysis target unit dynamically: % or g/h."""
    return PERCENTAGE if is_hydrolysis_in_percent(data) else "g/h"


def _hidro_max(data: dict[str, Any]) -> float | None:
    """Use the device-reported nominal as the hidro maximum, or fall back to the static default."""
    hidro_nom = data.get("MBF_PAR_HIDRO_NOM")
    return float(hidro_nom) if hidro_nom is not None else None


def _hidro_step(data: dict[str, Any]) -> float:
    """Step is 1 in percent mode, 0.1 in g/h mode."""
    return 1.0 if is_hydrolysis_in_percent(data) else 0.1


NUMBER_DESCRIPTIONS: dict[str, NeoPoolNumberEntityDescription] = {
    "MBF_PAR_HIDRO": NeoPoolNumberEntityDescription(
        key="MBF_PAR_HIDRO",
        translation_key="hidro",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0.0,
        native_max_value=100.0,
        native_step=1.0,
        register=HIDRO_SETPOINT_REGISTER,
        scale=10.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
        precision_fn=_hidro_precision,
        unit_fn=_hidro_unit,
        max_fn=_hidro_max,
        step_fn=_hidro_step,
    ),
    "MBF_PAR_PH1": NeoPoolNumberEntityDescription(
        key="MBF_PAR_PH1",
        translation_key="ph1",
        device_class=NumberDeviceClass.PH,
        native_min_value=0.0,
        native_max_value=14.0,
        native_step=0.1,
        register=PH_MAX_SETPOINT_REGISTER,
        scale=100.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: (
            "MBF_PAR_PH_ACID_RELAY_GPIO" not in data
            or is_valid_relay_gpio(data["MBF_PAR_PH_ACID_RELAY_GPIO"] or 0)
        ),
    ),
    "MBF_PAR_PH2": NeoPoolNumberEntityDescription(
        key="MBF_PAR_PH2",
        translation_key="ph2",
        device_class=NumberDeviceClass.PH,
        native_min_value=0.0,
        native_max_value=14.0,
        native_step=0.1,
        register=PH_MIN_SETPOINT_REGISTER,
        scale=100.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: (
            "MBF_PAR_PH_BASE_RELAY_GPIO" not in data
            or is_valid_relay_gpio(data["MBF_PAR_PH_BASE_RELAY_GPIO"] or 0)
        ),
    ),
    "MBF_PAR_RX1": NeoPoolNumberEntityDescription(
        key="MBF_PAR_RX1",
        translation_key="rx1",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        device_class=NumberDeviceClass.VOLTAGE,
        native_min_value=0.0,
        native_max_value=1000.0,
        native_step=1.0,
        register=REDOX_SETPOINT_REGISTER,
        scale=1.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: bool(
            data.get("Redox measurement module detected")
        ),
    ),
    "MBF_PAR_CL1": NeoPoolNumberEntityDescription(
        key="MBF_PAR_CL1",
        translation_key="cl1",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        native_min_value=0.0,
        native_max_value=10.0,
        native_step=0.1,
        register=CHLORINE_SETPOINT_REGISTER,
        scale=100.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: bool(
            data.get("Chlorine measurement module detected")
        ),
    ),
    "MBF_PAR_HEATING_TEMP": NeoPoolNumberEntityDescription(
        key="MBF_PAR_HEATING_TEMP",
        translation_key="heating_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=0.0,
        native_max_value=40.0,
        native_step=1.0,
        register=HEATING_SETPOINT_REGISTER,
        scale=1.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=_support_heating_temp,
        precision_fn=lambda data: 0,
    ),
    "MBF_PAR_SMART_TEMP_HIGH": NeoPoolNumberEntityDescription(
        key="MBF_PAR_SMART_TEMP_HIGH",
        translation_key="smart_temp_high",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=0.0,
        native_max_value=40.0,
        native_step=1.0,
        register=SMART_TEMP_HIGH_REGISTER,
        scale=1.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE")),
    ),
    "MBF_PAR_SMART_TEMP_LOW": NeoPoolNumberEntityDescription(
        key="MBF_PAR_SMART_TEMP_LOW",
        translation_key="smart_temp_low",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=0.0,
        native_max_value=40.0,
        native_step=1.0,
        register=SMART_TEMP_LOW_REGISTER,
        scale=1.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE")),
    ),
    "MBF_PAR_HIDRO_COVER_REDUCTION": NeoPoolNumberEntityDescription(
        key="MBF_PAR_HIDRO_COVER_REDUCTION",
        translation_key="hidro_cover_reduction",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0.0,
        native_max_value=100.0,
        native_step=1.0,
        register=HIDRO_COVER_REGISTER,
        data_key="MBF_PAR_HIDRO_COVER_REDUCTION",
        mask=HIDRO_COVER_REDUCTION_MASK,
        shift=HIDRO_COVER_REDUCTION_SHIFT,
        scale=1.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: bool(opts.get("use_cover_sensor")),
    ),
    "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE": NeoPoolNumberEntityDescription(
        key="MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE",
        translation_key="hidro_shutdown_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=1.0,
        native_max_value=40.0,
        native_step=1.0,
        register=HIDRO_COVER_REGISTER,
        data_key="MBF_PAR_HIDRO_COVER_REDUCTION",
        mask=HIDRO_SHUTDOWN_TEMP_MASK,
        shift=HIDRO_SHUTDOWN_TEMP_SHIFT,
        scale=1.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: (
            bool(opts.get("use_cover_sensor"))
            and bool(data.get("Hydrolysis module detected"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool number entities from a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        NeoPoolNumber(coordinator, entry.entry_id, key, desc)
        for key, desc in NUMBER_DESCRIPTIONS.items()
        if desc.supported_fn is None
        or desc.supported_fn(coordinator.data, entry.options)
    )


class NeoPoolNumber(NeoPoolEntity, NumberEntity):
    """Representation of a NeoPool number entity."""

    entity_description: NeoPoolNumberEntityDescription
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        description: NeoPoolNumberEntityDescription,
    ) -> None:
        """Initialize the NeoPool number entity."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._key = key
        self._data_key = description.data_key or key
        self._attr_unique_id = f"{self.coordinator.entry.unique_id}_{key.lower()}"

        self._pending_write_task: asyncio.Task[None] | None = None
        self._pending_value: float | None = None
        self._debounce_delay = 2.0

    @override
    async def async_added_to_hass(self) -> None:
        """Run when the entity is added to hass."""
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for reading registers")
            return
        await super().async_added_to_hass()

        val = self.coordinator.data.get(self._data_key)
        if val is not None and self.entity_description.mask is not None:
            val = (
                int(val) & self.entity_description.mask
            ) >> self.entity_description.shift
        self._attr_native_value = (
            round(val, 2) if isinstance(val, (int, float)) else None
        )

        self.async_write_ha_state()

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the native value of the number entity."""
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active, ignoring set_native_value for %s", self._key
            )
            return
        self._pending_value = value
        if (
            self._pending_write_task is not None and not self._pending_write_task.done()
        ):  # pragma: no cover
            self._pending_write_task.cancel()
        self._pending_write_task = asyncio.create_task(self._debounced_write())
        # Show the pending value optimistically. Write happens after debounce.
        self.async_write_ha_state()

    async def _debounced_write(self) -> None:
        """Debounced write to the Modbus register."""
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers")
            return
        desc = self.entity_description
        try:
            await asyncio.sleep(self._debounce_delay)
            if self.coordinator.winter_mode:  # pragma: no cover
                _LOGGER.warning(
                    "Winter mode is active, debounced write cancelled for %s",
                    self._key,
                )
                return
            raw = int((self._pending_value or 0) * desc.scale)
            if desc.mask is not None:
                current = int(self.coordinator.data.get(self._data_key, 0) or 0)
                raw = (current & ~desc.mask) | ((raw << desc.shift) & desc.mask)
                await client.async_write_register(desc.register, raw, apply=True)
            elif desc.register in (
                HEATING_SETPOINT_REGISTER,
                INTELLIGENT_SETPOINT_REGISTER,
            ):
                await client.async_set_temp_setpoint(raw)
            else:
                await client.async_write_register(desc.register, raw, apply=True)
            await self.coordinator.async_request_refresh()
        except asyncio.CancelledError:  # pragma: no cover
            pass

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested display precision for the number value."""
        if (precision_fn := self.entity_description.precision_fn) is not None:
            return precision_fn(self.coordinator.data)
        return None

    @property
    @override
    def native_value(self) -> float | None:
        """Return the actual number value."""
        raw = self.coordinator.data.get(self._data_key)
        if raw is not None and self.entity_description.mask is not None:
            raw = (
                int(raw) & self.entity_description.mask
            ) >> self.entity_description.shift
        if (
            self.suggested_display_precision == 0 and raw is not None
        ):  # pragma: no cover
            return float(round(raw))
        if raw is None:
            return self._attr_native_value
        return round(float(raw), 2)

    @property
    @override
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement for the number value."""
        if (unit_fn := self.entity_description.unit_fn) is not None:
            return unit_fn(self.coordinator.data)
        return self.entity_description.native_unit_of_measurement

    @property
    @override
    def native_max_value(self) -> float:
        """Return the maximum value for the number entity."""
        if (max_fn := self.entity_description.max_fn) is not None:
            if (dynamic_max := max_fn(self.coordinator.data)) is not None:
                return dynamic_max
        return self.entity_description.native_max_value or super().native_max_value

    @property
    @override
    def native_step(self) -> float | None:
        """Return the step value for the number entity."""
        if (step_fn := self.entity_description.step_fn) is not None:
            return step_fn(self.coordinator.data)
        return self.entity_description.native_step
