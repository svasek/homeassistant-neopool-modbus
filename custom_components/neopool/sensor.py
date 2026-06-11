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

from datetime import datetime
import logging
import math
from typing import Any

from neopool_modbus.decoders import get_filtration_pump_type, is_hydrolysis_in_percent

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import NeoPoolConfigEntry
from .const import CONF_FILTRATION_PUMP_POWER, SENSOR_DEFINITIONS
from .coordinator import NeoPoolCoordinator
from .entity import NeoPoolEntity
from .helpers import calculate_next_interval_time, has_filtvalve

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

# Add mapping for MBF_PAR_FILT_MODE values
# fmt: off
FILTRATION_MODE_MAP = {
    0: "manual",        # This mode allows to turn the filtration (and all other systems that depend on it) on and off manually
    1: "auto",          # This mode allows filtering to be turned on and off according to the settings of the TIMER1, TIMER2 and TIMER3 timers.
    2: "heating",       # This mode is similar to the AUTO mode, but includes setting the temperature for the heating function. This mode is activated only if the MBF_PAR_HEATING_MODE register is at 1 and there is a heating relay assigned.
    3: "smart",         # This filtration mode adjusts the pump operating times depending on the temperature. This mode is activated only if the MBF_PAR_TEMPERATURE_ACTIVE register is at 1.
    4: "intelligent",   # This mode performs an intelligent filtration process in combination with the heating function. This mode is activated only if the MBF_PAR_HEATING_MODE register is at 1 and there is a heating relay assigned.
    13: "backwash",     # This filter mode is started when the backwash operation is activated.
}
# fmt: on

FILTRATION_SPEED_MAP = {
    0: "off",
    1: "low",
    2: "mid",
    3: "high",
}

PH_STATUS_ALARM_MAP = {
    0: "ok",
    1: "ph_high",
    2: "ph_low",
    3: "pump_stopped",
    4: "ph_over",
    5: "ph_under",
    6: "tank_level",
}


def _should_skip_sensor(key: str, data: dict, options: dict | None = None) -> bool:
    """Return True if a sensor entity should not be created."""
    if key == CONF_FILTRATION_PUMP_POWER:
        return int((options or {}).get(CONF_FILTRATION_PUMP_POWER, 0) or 0) <= 0
    if key == "MBF_MEASURE_TEMPERATURE" and not bool(
        data.get("MBF_PAR_TEMPERATURE_ACTIVE")
    ):
        return True
    if (
        key in ("MBF_MEASURE_PH", "MBF_PH_STATUS_ALARM")
        and data.get("pH measurement module detected") is not True
    ):
        return True
    if (
        key == "MBF_MEASURE_RX"
        and data.get("Redox measurement module detected") is not True
    ):
        return True
    if (
        key == "MBF_MEASURE_CL"
        and data.get("Chlorine measurement module detected") is not True
    ):
        return True
    if (
        key == "MBF_MEASURE_CONDUCTIVITY"
        and data.get("Conductivity measurement module detected") is not True
    ):
        return True
    if key == "MBF_ION_CURRENT" and not bool((data.get("MBF_PAR_MODEL") or 0) & 0x0001):
        return True
    if key in (
        "MBF_HIDRO_CURRENT",
        "MBF_HIDRO_VOLTAGE",
        "HIDRO_POLARITY",
    ) and not data.get("Hydrolysis module detected"):
        return True
    if key == "ION_POLARITY" and not bool((data.get("MBF_PAR_MODEL") or 0) & 0x0001):
        return True
    if key == "FILTRATION_SPEED" and not get_filtration_pump_type(
        data.get("MBF_PAR_FILTRATION_CONF", 0)
    ):
        return True
    if key in ("MBF_PAR_INTELLIGENT_INTERVALS", "MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL"):
        if not bool(data.get("MBF_PAR_HEATING_GPIO")) or not bool(
            data.get("MBF_PAR_TEMPERATURE_ACTIVE")
        ):
            return True
    if key == "MBF_PAR_FILTVALVE_REMAINING" and not has_filtvalve(data):
        return True
    if (
        key == "PH_PUMP_STATUS"
        and data.get("pH measurement module detected") is not True
    ):
        return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NeoPool sensors from a config entry."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    if coordinator.data is None:
        _LOGGER.warning("No data from Modbus, skipping sensor setup!")
        return

    options = dict(entry.options)
    for key, props in SENSOR_DEFINITIONS.items():
        if _should_skip_sensor(key, coordinator.data, options):
            continue

        entities.append(
            NeoPoolSensor(
                coordinator,
                entry.entry_id,  # Pass entry_id explicitly to the sensor entity
                key,
                props,
            )
        )

    pump_power = int(entry.options.get(CONF_FILTRATION_PUMP_POWER, 0) or 0)
    if pump_power > 0:
        entities.append(
            NeoPoolFiltrationEnergySensor(coordinator, entry.entry_id, pump_power)
        )

    async_add_entities(entities)


class NeoPoolSensor(NeoPoolEntity, SensorEntity):
    """Representation of a NeoPool sensor."""

    _winter_mode_active = False  # sensors stay available during winter mode

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        props: dict[str, Any],
    ) -> None:
        """Initialize the NeoPool sensor entity."""
        super().__init__(coordinator, entry_id)  # Pass entry_id to the parent class
        self._key = key
        self._attr_suggested_object_id = (
            f"{self.coordinator.device_slug}_{NeoPoolEntity.slugify(self._key)}"
        )
        # Use entry.unique_id (serial-based in v2+) for stable identity, fallback to entry_id
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{self._key.lower()}"
        self._attr_translation_key = NeoPoolEntity.slugify(self._key)

        self._attr_native_unit_of_measurement = props.get("unit") or None
        self._attr_device_class = props.get("device_class") or None
        self._attr_state_class = props.get("state_class") or None
        self._attr_entity_category = props.get("entity_category") or None
        self._attr_suggested_display_precision = props.get("display_precision")

        # Disable some entities by default.
        if props.get("entity_registry_enabled_default") is False:
            self._attr_entity_registry_enabled_default = False

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
        await super().async_added_to_hass()

    @property
    def suggested_display_precision(self) -> int | None:
        """Return the suggested display precision for the sensor value."""
        if self._key == "MBF_HIDRO_CURRENT" and not is_hydrolysis_in_percent(
            self.coordinator.data
        ):
            return 1
        return self._attr_suggested_display_precision

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement for the sensor value."""
        if self._key == "MBF_HIDRO_CURRENT" and not is_hydrolysis_in_percent(
            self.coordinator.data
        ):
            return "g/h"
        return self._attr_native_unit_of_measurement

    _MEASURE_KEYS_REQUIRING_FILTRATION = frozenset(
        {
            "MBF_MEASURE_TEMPERATURE",
            "MBF_MEASURE_PH",
            "MBF_MEASURE_RX",
            "MBF_MEASURE_CONDUCTIVITY",
            "MBF_HIDRO_VOLTAGE",
            "FILTRATION_SPEED",
        }
    )

    def _is_measurement_suppressed(self) -> bool:
        """Return True if a measurement sensor should report None.

        Some chemical / temperature sensors only return meaningful values
        while the filtration pump is running. The 'measure_when_filtration_off'
        option lets the user opt out of this gating.
        """
        if self._key not in self._MEASURE_KEYS_REQUIRING_FILTRATION:
            return False
        if self.coordinator.entry.options.get("measure_when_filtration_off", False):
            return False
        return self.coordinator.data.get("Filtration Pump") is False

    def _compute_ph_pump_status(self) -> str | None:
        """Decode the pH pump status from the control + per-pump bits."""
        ctrl = self.coordinator.data.get("pH control module")
        acid_bit = self.coordinator.data.get("pH acid pump active")
        pump_bit = self.coordinator.data.get("pH pump active")
        if ctrl is None and acid_bit is None and pump_bit is None:
            return None
        if ctrl is None:
            return None  # partial data — cannot determine status
        if not ctrl:
            return "off"
        # MBF_PAR_RELAY_PH determines the pH pump configuration:
        #   0 = acid + base (bit 11 = acid, bit 12 = base)
        #   1 = acid only   (bit 12 = acid pump; bit 11 unused)
        #   2 = base only   (bit 12 = base pump; bit 11 unused)
        relay_ph = self.coordinator.data.get("MBF_PAR_RELAY_PH", 0) or 0
        if relay_ph == 1:
            return "acid" if pump_bit else "idle"
        if relay_ph == 2:
            return "base" if pump_bit else "idle"
        # Both pumps (relay_ph == 0): bit 11 = acid, bit 12 = base
        if acid_bit and pump_bit:
            return "both"
        if acid_bit:
            return "acid"
        if pump_bit:
            return "base"
        return "idle"

    def _compute_hidro_polarity(self) -> str | None:
        """Decode the hydrolysis polarity from the cell status bits."""
        pol1 = self.coordinator.data.get("HIDRO in Pol1")
        pol2 = self.coordinator.data.get("HIDRO in Pol2")
        dead = self.coordinator.data.get("HIDRO in dead time")
        if pol1 is None and pol2 is None and dead is None:
            return None
        filtration = self.coordinator.data.get("Filtration Pump")
        if filtration is not None and filtration is False:
            return "off"
        fl1 = self.coordinator.data.get("HIDRO Cell Flow FL1")
        if filtration is True and fl1 is False:
            return "no_flow"
        if dead:
            return "dead_time"
        if pol1:
            return "pol1"
        if pol2:
            return "pol2"
        return "off"

    def _compute_ion_polarity(self) -> str | None:
        """Decode the ionizer polarity from the cell status bits."""
        pol1 = self.coordinator.data.get("ION in Pol1")
        pol2 = self.coordinator.data.get("ION in Pol2")
        dead = self.coordinator.data.get("ION in dead time")
        if pol1 is None and pol2 is None and dead is None:
            return None
        if dead:
            return "dead_time"
        if pol1:
            return "pol1"
        if pol2:
            return "pol2"
        return "off"

    @property
    def native_value(self) -> float | int | str | datetime | None:
        """Return the actual sensor value from coordinator data."""
        if self._is_measurement_suppressed():
            return None
        if self._key == "PH_PUMP_STATUS":
            return self._compute_ph_pump_status()
        if self._key == "HIDRO_POLARITY":
            return self._compute_hidro_polarity()
        if self._key == "ION_POLARITY":
            return self._compute_ion_polarity()
        if self._key == "MBF_PAR_FILT_MODE":
            filt_mode: int | None = self.coordinator.data.get(self._key)
            return FILTRATION_MODE_MAP.get(filt_mode) if filt_mode is not None else None
        if self._key == "FILTRATION_SPEED":
            filt_speed: int | None = self.coordinator.data.get(self._key)
            return (
                FILTRATION_SPEED_MAP.get(filt_speed) if filt_speed is not None else None
            )
        if self._key == "MBF_PH_STATUS_ALARM":
            ph_alarm: int | None = self.coordinator.data.get(self._key)
            return PH_STATUS_ALARM_MAP.get(ph_alarm) if ph_alarm is not None else None
        if self._key == "MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL":
            # Convert seconds to timestamp using helper function
            seconds = self.coordinator.data.get(self._key)
            return calculate_next_interval_time(seconds, self.hass)
        return self.coordinator.data.get(self._key)

    @property
    def options(self) -> list[str] | None:
        """Return the list of options for the sensor."""
        if self._key == "MBF_PAR_FILT_MODE":
            return list(FILTRATION_MODE_MAP.values())
        if self._key == "FILTRATION_SPEED":
            return list(FILTRATION_SPEED_MAP.values())
        if self._key == "MBF_PH_STATUS_ALARM":
            return list(PH_STATUS_ALARM_MAP.values())
        if self._key == "HIDRO_POLARITY":
            return ["pol1", "pol2", "dead_time", "no_flow", "off"]
        if self._key == "ION_POLARITY":
            return ["pol1", "pol2", "dead_time", "off"]
        if self._key == "PH_PUMP_STATUS":
            relay_ph = self.coordinator.data.get("MBF_PAR_RELAY_PH", 0) or 0
            if relay_ph == 1:
                return ["off", "idle", "acid"]
            if relay_ph == 2:
                return ["off", "idle", "base"]
            return ["off", "idle", "acid", "base", "both"]
        return None  # pragma: no cover


class NeoPoolFiltrationEnergySensor(NeoPoolEntity, SensorEntity, RestoreEntity):
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
        """Initialise the filtration-pump energy accumulator sensor."""
        super().__init__(coordinator, entry_id)
        self._pump_power_w = pump_power_w
        self._attr_suggested_object_id = (
            f"{coordinator.device_slug}_filtration_pump_energy"
        )
        device_id = coordinator.entry.unique_id or entry_id
        self._attr_unique_id = f"{device_id}_filtration_pump_energy"
        self._total_wh: float = 0.0
        self._last_update: datetime | None = None
        self._last_pump_on: bool = False

    async def async_added_to_hass(self) -> None:
        """Restore last known energy value from entity state after restart."""
        await super().async_added_to_hass()
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (
            None,
            "unavailable",
            "unknown",
        ):
            try:
                restored = float(last_state.state)
                if math.isfinite(restored) and restored >= 0:
                    self._total_wh = restored
            except ValueError:
                pass

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
    def native_value(self) -> float:  # type: ignore[override]
        """Return accumulated energy in Wh."""
        return round(self._total_wh, 3)
