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

"""Sensor platform for the NeoPool integration."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
import logging
import math
from typing import Any, override

from neopool_modbus.capabilities import has_filtvalve, is_ionization_present
from neopool_modbus.decoders import (
    decode_hidro_polarity,
    decode_ion_polarity,
    decode_ph_pump_status,
    get_filtration_pump_type,
    is_hydrolysis_in_percent,
)

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import NeoPoolConfigEntry
from .const import CONF_FILTRATION_PUMP_POWER
from .coordinator import NeoPoolCoordinator
from .entity import NeoPoolEntity
from .helpers import calculate_next_interval_time

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

_FILTRATION_MODE_OPTIONS: list[str] = [
    "manual",
    "auto",
    "heating",
    "smart",
    "intelligent",
    "backwash",
]
_FILTRATION_SPEED_OPTIONS: list[str] = ["off", "low", "mid", "high"]
_POLARITY_OPTIONS_HYDRO: list[str] = ["pol1", "pol2", "dead_time", "no_flow", "off"]
_POLARITY_OPTIONS_ION: list[str] = ["pol1", "pol2", "dead_time", "off"]

PH_STATUS_ALARM_MAP = {
    0: "ok",
    1: "ph_high",
    2: "ph_low",
    3: "pump_stopped",
    4: "ph_over",
    5: "ph_under",
    6: "tank_level",
}


def _decode_ph_alarm(data: Mapping[str, Any]) -> str | None:
    """Map the raw MBF_PH_STATUS_ALARM register value to a translation key."""
    ph_alarm: int | None = data.get("MBF_PH_STATUS_ALARM")
    return PH_STATUS_ALARM_MAP.get(ph_alarm) if ph_alarm is not None else None


def _ph_pump_options(data: Mapping[str, Any]) -> list[str]:
    """Return the pH pump status enum options narrowed by relay mode."""
    relay_ph = data.get("MBF_PAR_RELAY_PH", 0) or 0
    if relay_ph == 1:
        return ["off", "idle", "acid"]
    if relay_ph == 2:
        return ["off", "idle", "base"]
    return ["off", "idle", "acid", "base", "both"]


@dataclass(frozen=True, kw_only=True)
class NeoPoolSensorEntityDescription(SensorEntityDescription):
    """Describes a NeoPool sensor entity."""

    supported_fn: Callable[[dict[str, Any], Mapping[str, Any]], bool] | None = None
    value_fn: Callable[[Mapping[str, Any]], Any] | None = None
    options_fn: Callable[[Mapping[str, Any]], list[str]] | None = None


SENSOR_DESCRIPTIONS: dict[str, NeoPoolSensorEntityDescription] = {
    "MBF_ION_CURRENT": NeoPoolSensorEntityDescription(
        key="MBF_ION_CURRENT",
        translation_key="ion_current",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda data, opts: is_ionization_present(data),
    ),
    "MBF_HIDRO_CURRENT": NeoPoolSensorEntityDescription(
        key="MBF_HIDRO_CURRENT",
        translation_key="hidro_current",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
    "MBF_MEASURE_PH": NeoPoolSensorEntityDescription(
        key="MBF_MEASURE_PH",
        translation_key="measure_ph",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda data, opts: (
            data.get("pH measurement module detected") is True
        ),
    ),
    "MBF_MEASURE_RX": NeoPoolSensorEntityDescription(
        key="MBF_MEASURE_RX",
        translation_key="measure_rx",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda data, opts: (
            data.get("Redox measurement module detected") is True
        ),
    ),
    "MBF_MEASURE_CL": NeoPoolSensorEntityDescription(
        key="MBF_MEASURE_CL",
        translation_key="measure_cl",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda data, opts: (
            data.get("Chlorine measurement module detected") is True
        ),
    ),
    "MBF_MEASURE_CONDUCTIVITY": NeoPoolSensorEntityDescription(
        key="MBF_MEASURE_CONDUCTIVITY",
        translation_key="measure_conductivity",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        supported_fn=lambda data, opts: (
            data.get("Conductivity measurement module detected") is True
        ),
    ),
    "MBF_MEASURE_TEMPERATURE": NeoPoolSensorEntityDescription(
        key="MBF_MEASURE_TEMPERATURE",
        translation_key="measure_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=lambda data, opts: bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE")),
    ),
    "MBF_HIDRO_VOLTAGE": NeoPoolSensorEntityDescription(
        key="MBF_HIDRO_VOLTAGE",
        translation_key="hidro_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
    "MBF_PAR_FILT_MODE": NeoPoolSensorEntityDescription(
        key="MBF_PAR_FILT_MODE",
        translation_key="filt_mode",
        device_class=SensorDeviceClass.ENUM,
        options=_FILTRATION_MODE_OPTIONS,
        value_fn=lambda data: data.get("filtration_mode"),
    ),
    "MBF_PH_STATUS_ALARM": NeoPoolSensorEntityDescription(
        key="MBF_PH_STATUS_ALARM",
        translation_key="ph_status_alarm",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=list(PH_STATUS_ALARM_MAP.values()),
        value_fn=_decode_ph_alarm,
        supported_fn=lambda data, opts: (
            data.get("pH measurement module detected") is True
        ),
    ),
    "HIDRO_POLARITY": NeoPoolSensorEntityDescription(
        key="HIDRO_POLARITY",
        translation_key="hidro_polarity",
        device_class=SensorDeviceClass.ENUM,
        options=_POLARITY_OPTIONS_HYDRO,
        value_fn=lambda data: decode_hidro_polarity(data),
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
    "ION_POLARITY": NeoPoolSensorEntityDescription(
        key="ION_POLARITY",
        translation_key="ion_polarity",
        device_class=SensorDeviceClass.ENUM,
        options=_POLARITY_OPTIONS_ION,
        value_fn=lambda data: decode_ion_polarity(data),
        supported_fn=lambda data, opts: is_ionization_present(data),
    ),
    "PH_PUMP_STATUS": NeoPoolSensorEntityDescription(
        key="PH_PUMP_STATUS",
        translation_key="ph_pump_status",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options_fn=_ph_pump_options,
        value_fn=lambda data: decode_ph_pump_status(data),
        supported_fn=lambda data, opts: (
            data.get("pH measurement module detected") is True
        ),
    ),
    "FILTRATION_SPEED": NeoPoolSensorEntityDescription(
        key="FILTRATION_SPEED",
        translation_key="filtration_speed",
        device_class=SensorDeviceClass.ENUM,
        options=_FILTRATION_SPEED_OPTIONS,
        value_fn=lambda data: data.get("filtration_speed_state"),
        supported_fn=lambda data, opts: bool(
            get_filtration_pump_type(data.get("MBF_PAR_FILTRATION_CONF", 0))
        ),
    ),
    "MBF_PAR_INTELLIGENT_INTERVALS": NeoPoolSensorEntityDescription(
        key="MBF_PAR_INTELLIGENT_INTERVALS",
        translation_key="intelligent_intervals",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=lambda data, opts: (
            bool(data.get("MBF_PAR_HEATING_GPIO"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
    "MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL": NeoPoolSensorEntityDescription(
        key="MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL",
        translation_key="intelligent_tt_next_interval",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: calculate_next_interval_time(
            data.get("MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL")
        ),
        supported_fn=lambda data, opts: (
            bool(data.get("MBF_PAR_HEATING_GPIO"))
            and bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))
        ),
    ),
    "MBF_PAR_FILTVALVE_REMAINING": NeoPoolSensorEntityDescription(
        key="MBF_PAR_FILTVALVE_REMAINING",
        translation_key="filtvalve_remaining",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        supported_fn=lambda data, opts: has_filtvalve(data),
    ),
    "FILTRATION_REMAINING": NeoPoolSensorEntityDescription(
        key="FILTRATION_REMAINING",
        translation_key="filtration_remaining",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    "CELL_RUNTIME_TOTAL": NeoPoolSensorEntityDescription(
        key="CELL_RUNTIME_TOTAL",
        translation_key="cell_runtime_total",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
    "CELL_RUNTIME_PART": NeoPoolSensorEntityDescription(
        key="CELL_RUNTIME_PART",
        translation_key="cell_runtime_part",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
    "CELL_RUNTIME_POLA": NeoPoolSensorEntityDescription(
        key="CELL_RUNTIME_POLA",
        translation_key="cell_runtime_pola",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
    "CELL_RUNTIME_POLB": NeoPoolSensorEntityDescription(
        key="CELL_RUNTIME_POLB",
        translation_key="cell_runtime_polb",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
    "CELL_RUNTIME_POL_CHANGES": NeoPoolSensorEntityDescription(
        key="CELL_RUNTIME_POL_CHANGES",
        translation_key="cell_runtime_pol_changes",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
    CONF_FILTRATION_PUMP_POWER: NeoPoolSensorEntityDescription(
        key=CONF_FILTRATION_PUMP_POWER,
        translation_key=CONF_FILTRATION_PUMP_POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        supported_fn=lambda data, opts: (
            int((opts or {}).get(CONF_FILTRATION_PUMP_POWER, 0) or 0) > 0
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool sensors from a config entry."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = [
        NeoPoolSensor(coordinator, entry.entry_id, key, desc)
        for key, desc in SENSOR_DESCRIPTIONS.items()
        if desc.supported_fn is None
        or desc.supported_fn(coordinator.data, entry.options)
    ]

    pump_power = int(entry.options.get(CONF_FILTRATION_PUMP_POWER, 0) or 0)
    if pump_power > 0:
        entities.append(
            NeoPoolFiltrationEnergySensor(coordinator, entry.entry_id, pump_power)
        )

    async_add_entities(entities)


_PRODUCTION_KEYS_REQUIRING_FILTRATION = frozenset(
    {
        "MBF_HIDRO_CURRENT",
        "MBF_HIDRO_VOLTAGE",
        "MBF_ION_CURRENT",
    }
)

_MEASURE_KEYS_REQUIRING_FILTRATION = frozenset(
    {
        "MBF_MEASURE_TEMPERATURE",
        "MBF_MEASURE_PH",
        "MBF_MEASURE_RX",
        "MBF_MEASURE_CL",
        "MBF_MEASURE_CONDUCTIVITY",
        "FILTRATION_SPEED",
    }
)


class NeoPoolSensor(NeoPoolEntity, SensorEntity):
    """Representation of a NeoPool sensor."""

    _winter_mode_active = False
    entity_description: NeoPoolSensorEntityDescription

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        description: NeoPoolSensorEntityDescription,
    ) -> None:
        """Initialize the NeoPool sensor entity."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._key = key
        self._attr_unique_id = f"{self.coordinator.entry.unique_id}_{key.lower()}"

    @property
    @override
    def suggested_display_precision(self) -> int | None:
        """Return the suggested display precision for the sensor value."""
        if self._key == "MBF_HIDRO_CURRENT" and not is_hydrolysis_in_percent(
            self.coordinator.data
        ):
            return 1
        return self.entity_description.suggested_display_precision

    @property
    @override
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement for the sensor value."""
        if self._key == "MBF_HIDRO_CURRENT" and not is_hydrolysis_in_percent(
            self.coordinator.data
        ):
            return "g/h"
        return self.entity_description.native_unit_of_measurement

    def _filtration_gate_blocks(self) -> bool:
        """Return True if the filtration-off gate hides the live reading."""
        if self.coordinator.entry.options.get("measure_when_filtration_off", False):
            return False
        return self.coordinator.data.get("Filtration Pump") is False

    @property
    @override
    def native_value(self) -> float | int | str | datetime | None:
        """Return the actual sensor value from coordinator data."""
        if (
            self._key in _MEASURE_KEYS_REQUIRING_FILTRATION
            and self._filtration_gate_blocks()
        ):
            return None
        if (
            self._key in _PRODUCTION_KEYS_REQUIRING_FILTRATION
            and self._filtration_gate_blocks()
        ):
            return 0
        if (value_fn := self.entity_description.value_fn) is not None:
            return value_fn(self.coordinator.data)
        return self.coordinator.data.get(self._key)

    @property
    @override
    def options(self) -> list[str] | None:
        """Return the list of options for the sensor."""
        if (options_fn := self.entity_description.options_fn) is not None:
            return options_fn(self.coordinator.data)
        return self.entity_description.options


class NeoPoolFiltrationEnergySensor(NeoPoolEntity, RestoreSensor):
    """Cumulative energy consumed by the filtration pump (Wh).

    Integrates instantaneous power over time using coordinator update timestamps.
    Suitable for the Energy dashboard "Individual devices" energy tracking.
    """

    _winter_mode_active = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    _attr_suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 0
    _attr_translation_key = "filtration_pump_energy"

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        pump_power_w: int,
    ) -> None:
        """Initialise the filtration-pump energy sensor."""
        super().__init__(coordinator, entry_id)
        self._pump_power_w = pump_power_w
        self._attr_unique_id = f"{coordinator.entry.unique_id}_filtration_pump_energy"
        self._total_wh: float = 0.0
        self._last_update: datetime | None = None
        self._last_pump_on: bool = False

    @override
    async def async_added_to_hass(self) -> None:
        """Restore last known energy value from sensor extra data after restart."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_sensor_data()
        if last_data is None:  # pragma: no cover
            return
        value = last_data.native_value
        if not isinstance(value, (int, float, str)):  # pragma: no cover
            return
        try:
            restored = float(value)
        except (TypeError, ValueError):  # pragma: no cover
            return
        if math.isfinite(restored) and restored >= 0:  # pragma: no cover
            self._total_wh = restored

    @override
    def _handle_coordinator_update(self) -> None:
        """Accumulate energy on each coordinator update."""
        now = dt_util.utcnow()
        if self._last_update is not None and self._last_pump_on:
            elapsed_h = (now - self._last_update).total_seconds() / 3600.0
            self._total_wh += self._pump_power_w * elapsed_h
        self._last_update = now
        self._last_pump_on = bool(self.coordinator.data.get("Filtration Pump"))
        super()._handle_coordinator_update()

    @property
    @override
    def native_value(self) -> float:
        """Return accumulated energy in Wh."""
        return round(self._total_wh, 3)
