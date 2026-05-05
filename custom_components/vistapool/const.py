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

"""
VistaPool Integration for Home Assistant - Constants

This file contains metadata about the integration such as name, version, domain, etc.
The manifest file is loaded to get the integration name and version
The integration name and version are used to identify the integration
and to display information about the integration in Home Assistant
"""

import json
import logging
from pathlib import Path

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory

PLATFORMS = ["sensor", "binary_sensor", "switch", "number", "button", "select", "light"]

manifest_path = Path(__file__).parent / "manifest.json"
with open(manifest_path, encoding="utf-8") as f:
    MANIFEST = json.load(f)

INTEGRATION_VERSION = MANIFEST.get("version")

DOMAIN = (
    MANIFEST.get("domain").lower().replace("-", "_").replace(" ", "_").replace(".", "_")
    or "vistapool"
)
NAME = MANIFEST.get("name") or "VistaPool Modbus"
DEFAULT_NAME = "VistaPool"
VERSION = MANIFEST.get("version") or None

LOGGER = logging.getLogger(__name__)

DEFAULT_TIMER_RESOLUTION = 15  # in minutes
DEFAULT_SCAN_INTERVAL = 30  # in seconds
FOLLOW_UP_REFRESH_DELAY = (
    2.0  # seconds — delay before a second refresh after IO entity actions
)
DEFAULT_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_MODBUS_FRAMER = "tcp"  # "tcp" = standard Modbus TCP (MBAP header), "rtu" = RTU over TCP (no MBAP, CRC)

MANUAL_FILTRATION_REGISTER = 0x0413
EXEC_REGISTER = 0x02F5
HEATING_SETPOINT_REGISTER = 0x0416  # MBF_PAR_HEATING_TEMP
INTELLIGENT_SETPOINT_REGISTER = 0x041C  # MBF_PAR_INTELLIGENT_TEMP

# MBF_RELAY_STATE has 7 relays (bits 0-6); MBF_PAR_UV_RELAY_GPIO is a 1-based index.
MAX_RELAY_GPIO = 7


def is_valid_relay_gpio(gpio: int) -> bool:
    """Return True if the relay GPIO number is within the hardware range (1-based, 1–7)."""
    return 1 <= gpio <= MAX_RELAY_GPIO


# GPIO registers that assign physical relay outputs.
# Used for sanity-checking register values after the first Modbus read.
GPIO_REGISTERS = {
    "MBF_PAR_FILT_GPIO": "Filtration relay",
    "MBF_PAR_LIGHTING_GPIO": "Lighting relay",
    "MBF_PAR_HEATING_GPIO": "Heating relay",
    "MBF_PAR_PH_ACID_RELAY_GPIO": "pH acid pump relay",
    "MBF_PAR_PH_BASE_RELAY_GPIO": "pH base pump relay",
    "MBF_PAR_RX_RELAY_GPIO": "Redox pump relay",
    "MBF_PAR_CL_RELAY_GPIO": "Chlorine pump relay",
    "MBF_PAR_CD_RELAY_GPIO": "Conductivity pump relay",
    "MBF_PAR_UV_RELAY_GPIO": "UV lamp relay",
    "MBF_PAR_FILTVALVE_GPIO": "Filter valve relay",
}

# Capability keys that drive entity-creation logic in every platform's async_setup_entry.
# They are snapshotted when winter mode is enabled and persisted in entry.options so that
# platforms can set up the correct set of entities after a HA restart in winter mode.
CAPABILITY_KEYS = (
    "MBF_PAR_MODEL",
    "MBF_PAR_TEMPERATURE_ACTIVE",
    "MBF_PAR_FILTRATION_CONF",
    "MBF_PAR_HEATING_GPIO",
    "MBF_PAR_HIDRO_NOM",
    "MBF_PAR_HIDRO_COVER_ENABLE",
    "MBF_PAR_PH_ACID_RELAY_GPIO",
    "MBF_PAR_PH_BASE_RELAY_GPIO",
    "MBF_PAR_RX_RELAY_GPIO",
    "MBF_PAR_CL_RELAY_GPIO",
    "MBF_PAR_CD_RELAY_GPIO",
    "MBF_PAR_UV_RELAY_GPIO",
    "MBF_PAR_RELAY_PH",
    "MBF_PAR_FILT_GPIO",
    "MBF_PAR_LIGHTING_GPIO",
    "MBF_PAR_FILTVALVE_ENABLE",
    "MBF_PAR_FILTVALVE_GPIO",
    "Hydrolysis module detected",
    "pH measurement module detected",
    "Redox measurement module detected",
    "Chlorine measurement module detected",
    "Conductivity measurement module detected",
)

# Entity keys removed in past releases. async_setup_entry() uses this list to
# purge orphaned entity-registry entries so they don't linger as "unavailable".
REMOVED_ENTITY_KEYS = (
    # Removed in PR #117 — merged into polarity enum sensors
    "ion in dead time",
    "ion in pol1",
    "ion in pol2",
    "hidro in dead time",
    "hidro in pol1",
    "hidro in pol2",
    # Removed in PR #118 — redundant / not useful as sensors
    "hidro on target",
    "hidro chlorine flow indicator fl2",
    "hidro cell flow fl1",
    # Removed in PR #119 — merged into PH_PUMP_STATUS enum sensor
    "ph acid pump active",
    "ph pump active",
)

PERIOD_MAP = {
    "1_day": 86400,
    "2_days": 2 * 86400,
    "3_days": 3 * 86400,
    "4_days": 4 * 86400,
    "5_days": 5 * 86400,
    "1_week": 7 * 86400,
    "2_weeks": 14 * 86400,
    "3_weeks": 21 * 86400,
    "4_weeks": 28 * 86400,
}

PERIOD_SECONDS_TO_KEY = {v: k for k, v in PERIOD_MAP.items()}

""" Read timer blocks (0x0434-0x04E8) in blocks of *15* due to device limits """
TIMER_BLOCKS = {
    "filtration1": 0x0434,
    "filtration2": 0x0443,
    "filtration3": 0x0452,
    "relay_light": 0x0470,
    "relay_aux1": 0x04AC,
    "relay_aux1b": 0x0461,
    "relay_aux2": 0x04BB,
    "relay_aux2b": 0x047F,
    "relay_aux3": 0x04CA,
    "relay_aux3b": 0x048E,
    "relay_aux4": 0x04D9,
    "relay_aux4b": 0x049D,
}

SENSOR_DEFINITIONS = {
    "MBF_ION_CURRENT": {
        "name": "Ionization Level",
        "unit": "%",
        "device_class": SensorDeviceClass.POWER_FACTOR,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:atom",
    },
    "MBF_HIDRO_CURRENT": {
        "name": "Hydrolysis Intensity",
        "unit": "%",
        "device_class": SensorDeviceClass.POWER_FACTOR,
        "state_class": SensorStateClass.MEASUREMENT,
        "display_precision": 0,
    },
    "MBF_MEASURE_PH": {
        "name": "pH Level",
        "device_class": SensorDeviceClass.PH,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:ph",
    },
    "MBF_MEASURE_RX": {
        "name": "Redox Potential",
        "unit": "mV",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:gradient-vertical",
    },
    "MBF_MEASURE_CL": {
        "name": "Salt Level",
        "unit": "ppm",
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:shaker-outline",
    },
    "MBF_MEASURE_CONDUCTIVITY": {
        "name": "Conductivity Level",
        "unit": "%",
        "device_class": SensorDeviceClass.POWER_FACTOR,
        "state_class": SensorStateClass.MEASUREMENT,
        "display_precision": 0,
    },
    "MBF_MEASURE_TEMPERATURE": {
        "name": "Water Temperature",
        "unit": "°C",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "MBF_HIDRO_VOLTAGE": {
        "name": "Hydrolysis Voltage",
        "unit": "V",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "display_precision": 1,
    },
    "MBF_PAR_FILT_MODE": {
        "name": "Filtration Mode",
        "unit": None,
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "icon": "mdi:water-sync",
    },
    "MBF_PH_STATUS_ALARM": {
        "name": "pH Alarm",
        "unit": None,
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:ph",
    },
    "HIDRO_POLARITY": {
        "name": "Hydrolysis Polarity",
        "unit": None,
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "icon": "mdi:plus-minus-variant",
    },
    "ION_POLARITY": {
        "name": "Ionizer Polarity",
        "unit": None,
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "icon": "mdi:plus-minus-variant",
    },
    "PH_PUMP_STATUS": {
        "name": "pH Pump Status",
        "unit": None,
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:pump",
    },
    "FILTRATION_SPEED": {
        "name": "Filtration Current Speed",
        "unit": None,
        "device_class": SensorDeviceClass.ENUM,
        "state_class": None,
        "icon": "mdi:fan",
    },
    "MBF_PAR_INTELLIGENT_INTERVALS": {
        "name": "Intelligent Mode Intervals",
        "unit": None,
        "device_class": None,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:counter",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "MBF_PAR_INTELLIGENT_TT_NEXT_INTERVAL": {
        "name": "Intelligent Mode Next Interval",
        "unit": None,
        "device_class": SensorDeviceClass.TIMESTAMP,
        "state_class": None,
        "icon": "mdi:timeline-clock-outline",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "MBF_PAR_FILTVALVE_REMAINING": {
        "name": "Backwash Time Remaining",
        "unit": "s",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:timer-sand",
        "display_precision": 0,
    },
    "FILTRATION_REMAINING": {
        "name": "Filtration Time Remaining",
        "unit": "s",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": None,
        "icon": "mdi:timer-sand",
        "display_precision": 0,
    },
}

BINARY_SENSOR_DEFINITIONS = {
    "Device Time Out Of Sync": {
        "name": "Device Time Out Of Sync",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:clock-alert",
        "icon_off": "mdi:clock-check-outline",
    },
    # Relay states
    "pH Acid Pump": {
        "name": "pH Regulating",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:pump",
        "icon_off": "mdi:pump-off",
    },
    "Filtration Pump": {
        "name": "Filtration Running",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "icon_on": "mdi:pump",
        "icon_off": "mdi:pump-off",
    },
    "Pool Light": {
        "name": "Pool Light",
        "device_class": BinarySensorDeviceClass.LIGHT,
        "icon_on": "mdi:lightbulb-on",
        "icon_off": "mdi:lightbulb-outline",
        "option": "use_light",
    },
    "AUX1": {
        "name": "Auxiliary Relay 1",
        "device_class": BinarySensorDeviceClass.POWER,
        "icon_on": "mdi:electric-switch-closed",
        "icon_off": "mdi:electric-switch",
        "option": "use_aux1",
    },
    "AUX2": {
        "name": "Auxiliary Relay 2",
        "device_class": BinarySensorDeviceClass.POWER,
        "icon_on": "mdi:electric-switch-closed",
        "icon_off": "mdi:electric-switch",
        "option": "use_aux2",
    },
    "AUX3": {
        "name": "Auxiliary Relay 3",
        "device_class": BinarySensorDeviceClass.POWER,
        "icon_on": "mdi:electric-switch-closed",
        "icon_off": "mdi:electric-switch",
        "option": "use_aux3",
    },
    "AUX4": {
        "name": "Auxiliary Relay 4",
        "device_class": BinarySensorDeviceClass.POWER,
        "icon_on": "mdi:electric-switch-closed",
        "icon_off": "mdi:electric-switch",
        "option": "use_aux4",
    },
    # pH/Redox/CL/CD status bits from decode_ph_rx_cl_cd_status_bits
    # pH
    "pH module control status": {
        "name": "pH Flow Detection Control",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Note: "pH acid pump active" and "pH pump active" (MBF_PH_STATUS bits 11/12)
    # are merged into the PH_PUMP_STATUS enum sensor.
    "pH control module": {
        "name": "pH Regulation Active",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "pH measurement active": {
        "name": "pH Measurement",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:scale",
        "icon_off": "mdi:scale-off",
    },
    "pH measurement module detected": {
        "name": "pH Measurement Module Detected",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Redox
    "Redox pump active": {
        "name": "Redox Pump Active",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:pump",
        "icon_off": "mdi:pump-off",
    },
    "Redox control module": {
        "name": "Redox Regulation Active",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "Redox measurement active": {
        "name": "Redox Measurement",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:scale",
        "icon_off": "mdi:scale-off",
    },
    "Redox measurement module detected": {
        "name": "Redox Measurement Module Detected",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Chlorine
    "Chlorine flow sensor problem": {
        "name": "Chlorine Flow Sensor",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "Chlorine pump active": {
        "name": "Chlorine Pump Active",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:pump",
        "icon_off": "mdi:pump-off",
    },
    "Chlorine control module": {
        "name": "Chlorine Regulation Active",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "Chlorine measurement active": {
        "name": "Chlorine Measurement",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:scale",
        "icon_off": "mdi:scale-off",
    },
    "Chlorine measurement module detected": {
        "name": "Chlorine Measurement Module Detected",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Conductivity
    "Conductivity pump active": {
        "name": "Conductivity Pump Active",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:pump",
        "icon_off": "mdi:pump-off",
    },
    "Conductivity control module": {
        "name": "Conductivity Regulation Active",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "Conductivity measurement active": {
        "name": "Conductivity Measurement",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:scale",
        "icon_off": "mdi:scale-off",
    },
    "Conductivity measurement module detected": {
        "name": "Conductivity Measurement Module Detected",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Ion status bits
    "ION On Target": {
        "name": "Ionizer On Target",
        "device_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "ION Low Flow": {
        "name": "Ionizer Production Problem",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # "ION Reserved": {
    #     "name": "Ionizer Reserved",
    #     "device_class": None,
    #     "entity_category": EntityCategory.DIAGNOSTIC,
    # },
    "ION Program time exceeded": {
        "name": "Ionizer Program Time Exceeded",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Hydrolysis status bits
    # Note: "HIDRO On Target" (bit 0, MBMSK_HIDRO_STATUS_ON_TARGET) removed —
    # indicates setpoint reached, which is derivable from hidro_current vs hidro
    # setpoint. Even Tasmota defines this bit but never displays it.
    "HIDRO Low Flow": {
        "name": "Hydrolysis Production Problem",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # "HIDRO Reserved": {
    #     "name": "Hydrolysis Reserved",
    #     "device_class": None,
    #     "entity_category": EntityCategory.DIAGNOSTIC,
    # },
    # Note: "HIDRO Cell Flow FL1" (bit 3, MBMSK_HIDRO_STATUS_FL1) removed —
    # merged into the HIDRO_POLARITY enum sensor as "no_flow" state.
    "Pool Cover": {
        "name": "Pool Cover",
        "device_class": BinarySensorDeviceClass.OPENING,
        "option": "use_cover_sensor",
    },
    "HIDRO Module active": {
        "name": "Hydrolysis Enabled",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "HIDRO Module regulated": {
        "name": "Hydrolysis Regulation Active",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "HIDRO Activated by the RX module": {
        "name": "Hydrolysis Activated by Redox Module",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "HIDRO Chlorine shock mode": {
        "name": "Hydrolysis Chlorine Shock Mode",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Note: "HIDRO Chlorine flow indicator FL2" (bit 9, MBMSK_HIDRO_STATUS_FL2) removed —
    # redundant with "Chlorine flow sensor problem" (MBF_CL_STATUS bit 3) for devices
    # with a chlorine module, and irrelevant for devices without one.
    "HIDRO Activated by the CL module": {
        "name": "Hydrolysis Activated by Chlorine Module",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "Heating": {
        "name": "Heating",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:radiator",
        "icon_off": "mdi:radiator-off",
    },
    "UV Lamp": {
        "name": "UV Lamp",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon_on": "mdi:lightbulb-fluorescent-tube",
        "icon_off": "mdi:lightbulb-fluorescent-tube-outline",
    },
    # Note: "HIDRO in dead time", "HIDRO in Pol1" and "HIDRO in Pol2" are merged
    # into the HIDRO_POLARITY enum sensor.
    # Similarly, "ION in dead time", "ION in Pol1" and "ION in Pol2" are merged
    # into the ION_POLARITY enum sensor.
}

NUMBER_DEFINITIONS = {
    "MBF_PAR_HIDRO": {
        "name": "Hydrolysis target production level",
        "unit": "%",
        "min": 0.0,
        "max": 100.0,
        "step": 1.0,
        "register": 0x0502,  # MBF_PAR_HIDRO
        "scale": 10.0,
        "device_class": None,
        "entity_category": EntityCategory.CONFIG,
        "icon": "mdi:air-humidifier",
    },
    "MBF_PAR_PH1": {
        "name": "pH Max Limit",
        "min": 5.0,
        "max": 9.0,
        "step": 0.1,
        "register": 0x0504,  # MBF_PAR_PH1
        "scale": 100.0,
        "device_class": NumberDeviceClass.PH,
        "entity_category": EntityCategory.CONFIG,
    },
    "MBF_PAR_PH2": {
        "name": "pH Min Limit",
        "min": 5.0,
        "max": 9.0,
        "step": 0.1,
        "register": 0x0505,  # MBF_PAR_PH2
        "scale": 100.0,
        "device_class": NumberDeviceClass.PH,
        "entity_category": EntityCategory.CONFIG,
    },
    "MBF_PAR_RX1": {
        "name": "Redox Setpoint",
        "unit": "mV",
        "min": 0.0,
        "max": 1000.0,
        "step": 1.0,
        "register": 0x0508,  # MBF_PAR_RX1
        "scale": 1.0,
        "device_class": NumberDeviceClass.VOLTAGE,
        "entity_category": EntityCategory.CONFIG,
        "icon": "mdi:gradient-vertical",
    },
    "MBF_PAR_CL1": {
        "name": "Chlorine Setpoint",
        "unit": "ppm",
        "min": 0.0,
        "max": 10.0,
        "step": 0.1,
        "register": 0x050A,  # MBF_PAR_CL1
        "scale": 100.0,
        "device_class": None,
        "entity_category": EntityCategory.CONFIG,
        "icon": "mdi:test-tube",
    },
    "MBF_PAR_HEATING_TEMP": {
        "name": "Temperature Setpoint",
        "unit": "°C",
        "min": 0.0,
        "max": 40.0,
        "step": 1.0,
        "register": 0x0416,  # MBF_PAR_HEATING_TEMP
        "scale": 1.0,
        "device_class": NumberDeviceClass.TEMPERATURE,
        "entity_category": EntityCategory.CONFIG,
    },
    "MBF_PAR_SMART_TEMP_HIGH": {
        "name": "Smart Upper Temperature",
        "unit": "°C",
        "min": 0.0,
        "max": 40.0,
        "step": 1.0,
        "register": 0x0418,  # MBF_PAR_SMART_TEMP_HIGH
        "scale": 1.0,
        "device_class": NumberDeviceClass.TEMPERATURE,
        "entity_category": EntityCategory.CONFIG,
        "icon": "mdi:thermometer-chevron-up",
    },
    "MBF_PAR_SMART_TEMP_LOW": {
        "name": "Smart Lower Temperature",
        "unit": "°C",
        "min": 0.0,
        "max": 40.0,
        "step": 1.0,
        "register": 0x0419,  # MBF_PAR_SMART_TEMP_LOW
        "scale": 1.0,
        "device_class": NumberDeviceClass.TEMPERATURE,
        "entity_category": EntityCategory.CONFIG,
        "icon": "mdi:thermometer-chevron-down",
    },
    "MBF_PAR_HIDRO_COVER_REDUCTION": {
        "name": "Hydrolysis Cover Reduction Percentage",
        "unit": "%",
        "min": 0.0,
        "max": 100.0,
        "step": 1.0,
        "register": 0x042D,  # MBF_PAR_HIDRO_COVER_REDUCTION
        "data_key": "MBF_PAR_HIDRO_COVER_REDUCTION",  # coordinator data key (combined register)
        "mask": 0x00FF,
        "shift": 0,
        "scale": 1.0,
        "device_class": None,
        "entity_category": EntityCategory.CONFIG,
        "icon": "mdi:pool",
        "option": "use_cover_sensor",
    },
    "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE": {
        "name": "Hydrolysis Shutdown Temperature",
        "unit": "°C",
        "min": 1.0,
        "max": 40.0,
        "step": 1.0,
        "register": 0x042D,  # MBF_PAR_HIDRO_COVER_REDUCTION (upper byte)
        "data_key": "MBF_PAR_HIDRO_COVER_REDUCTION",  # coordinator data key (combined register)
        "mask": 0xFF00,
        "shift": 8,
        "scale": 1.0,
        "device_class": NumberDeviceClass.TEMPERATURE,
        "entity_category": EntityCategory.CONFIG,
        "icon": "mdi:thermometer-alert",
        "option": "use_cover_sensor",
    },
}

BUTTON_DEFINITIONS = {
    "SYNC_TIME": {
        "name": "Synchronize Device Time",
        "icon": "mdi:clock-check-outline",
        "entity_category": EntityCategory.CONFIG,
    },
    "MBF_ESCAPE": {
        "name": "Clear Errors",
        "icon": "mdi:reload-alert",
        "entity_category": EntityCategory.CONFIG,
    },
    "BACKWASH": {
        "name": "Start Backwash",
        "icon": "mdi:waves-arrow-left",
    },
}

SELECT_DEFINITIONS = {
    "MBF_PAR_FILT_MODE": {
        "name": "Filtration Mode",
        "icon": "mdi:water-sync",
        "options_map": {
            0: "manual",
            1: "auto",
            2: "heating",
            3: "smart",
            4: "intelligent",
            13: "backwash",
        },
        "register": 0x0411,  # FILTRATION_MODE_REGISTER
    },
    "MBF_PAR_FILTRATION_SPEED": {
        "name": "Filtration Speed",
        "icon": "mdi:fan-speed-3",
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "register": 0x050F,
        "mask": 0x0070,
        "shift": 4,
    },
    "MBF_CELL_BOOST": {
        "name": "Boost Mode",
        "icon": "mdi:flash-outline",
        "options_map": {
            0: "inactive",
            1: "active",
            2: "active_redox",
        },
        "register": 0x020C,
    },
    "MBF_PAR_FILTVALVE_PERIOD_MINUTES": {
        "name": "Backwash Repeat Interval",
        "icon": "mdi:timer-refresh-outline",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {
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
        "register": 0x04ED,
    },
    "MBF_PAR_FILTVALVE_MODE": {
        "name": "Backwash Valve Mode",
        "icon": "mdi:valve",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {
            # 0: "disabled",     # valve disabled – hidden (covered by MBF_PAR_FILTVALVE_ENABLE)
            1: "enabled",  # timer-controlled (MBV_PAR_CTIMER_ENABLED)
            # 2: "auto_linked",  # linked to parent relay – not applicable for filtvalve
            3: "always_on",  # MBV_PAR_CTIMER_ALWAYS_ON
            4: "always_off",  # MBV_PAR_CTIMER_ALWAYS_OFF
        },
        "register": 0x04E9,
    },
    "MBF_PAR_INTELLIGENT_FILT_MIN_TIME": {
        "name": "Intelligent Min Filtration Time",
        "icon": "mdi:timer-lock-outline",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {
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
        "register": 0x041D,
    },
    "filtration1_start": {
        "name": "Filtration Timer 1 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration1",
    },
    "filtration1_stop": {
        "name": "Filtration Timer 1 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration1",
    },
    "filtration2_start": {
        "name": "Filtration Timer 2 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration2",
    },
    "filtration2_stop": {
        "name": "Filtration Timer 2 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration2",
    },
    "filtration3_start": {
        "name": "Filtration Timer 3 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration3",
    },
    "filtration3_stop": {
        "name": "Filtration Timer 3 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration3",
    },
    "filtration1_speed": {
        "name": "Timer 1 - Filtration Speed",
        "icon": "mdi:fan-speed-3",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "register": 0x050F,
        "mask": 0x0380,
        "shift": 7,
        "option": "use_filtration1",
    },
    "filtration2_speed": {
        "name": "Timer 2 - Filtration Speed",
        "icon": "mdi:fan-speed-3",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "register": 0x050F,
        "mask": 0x1C00,
        "shift": 10,
        "option": "use_filtration2",
    },
    "filtration3_speed": {
        "name": "Timer 3 - Filtration Speed",
        "icon": "mdi:fan-speed-3",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "register": 0x050F,
        "mask": 0xE000,
        "shift": 13,
        "option": "use_filtration3",
    },
    "relay_aux1_start": {
        "name": "Relay AUX1 Timer 1 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1_stop": {
        "name": "Relay AUX1 Timer 1 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1_period": {
        "name": "Relay AUX1 Timer 1 Repeat",
        "icon": "mdi:repeat-variant",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1b_start": {
        "name": "Relay AUX1 Timer 2 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1b_stop": {
        "name": "Relay AUX1 Timer 2 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1b_period": {
        "name": "Relay AUX1 Timer 2 Repeat",
        "icon": "mdi:repeat-variant",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux2_start": {
        "name": "Relay AUX2 Timer 1 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2_stop": {
        "name": "Relay AUX2 Timer 1 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2_period": {
        "name": "Relay AUX2 Timer 1 Repeat",
        "icon": "mdi:repeat-variant",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2b_start": {
        "name": "Relay AUX2 Timer 2 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2b_stop": {
        "name": "Relay AUX2 Timer 2 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2b_period": {
        "name": "Relay AUX2 Timer 2 Repeat",
        "icon": "mdi:repeat-variant",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux3_start": {
        "name": "Relay AUX3 Timer 1 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3_stop": {
        "name": "Relay AUX3 Timer 1 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3_period": {
        "name": "Relay AUX3 Timer 1 Repeat",
        "icon": "mdi:repeat-variant",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3b_start": {
        "name": "Relay AUX3 Timer 2 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3b_stop": {
        "name": "Relay AUX3 Timer 2 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3b_period": {
        "name": "Relay AUX3 Timer 2 Repeat",
        "icon": "mdi:repeat-variant",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux4_start": {
        "name": "Relay AUX4 Timer 1 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4_stop": {
        "name": "Relay AUX4 Timer 1 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4_period": {
        "name": "Relay AUX4 Timer 1 Repeat",
        "icon": "mdi:repeat-variant",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4b_start": {
        "name": "Relay AUX4 Timer 2 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4b_stop": {
        "name": "Relay AUX4 Timer 2 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4b_period": {
        "name": "Relay AUX4 Timer 2 Repeat",
        "icon": "mdi:repeat-variant",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux4",
    },
    "relay_light_start": {
        "name": "Relay Light Timer 1 Start",
        "icon": "mdi:clock-start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_light",
    },
    "relay_light_stop": {
        "name": "Relay Light Timer 1 Stop",
        "icon": "mdi:clock-end",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_light",
    },
    "relay_light_period": {
        "name": "Relay Light Timer 1 Repeat",
        "icon": "mdi:repeat-variant",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_light",
    },
    "relay_aux1_mode": {
        "name": "AUX1 Mode",
        "icon": "mdi:speedometer-medium",
        "options_map": {
            # 0: "disabled",
            1: "auto",
            # 2: "auto_linked",
            3: "on",
            4: "off",
        },
        "register": 0x04AC,
        "register_offset": 0,
        "select_type": "relay_mode",
        "option": "use_aux1",
    },
    "relay_aux2_mode": {
        "name": "AUX2 Mode",
        "icon": "mdi:speedometer-medium",
        "options_map": {
            # 0: "disabled",
            1: "auto",
            # 2: "auto_linked",
            3: "on",
            4: "off",
        },
        "register": 0x04BB,
        "register_offset": 0,
        "select_type": "relay_mode",
        "option": "use_aux2",
    },
    "relay_aux3_mode": {
        "name": "AUX3 Mode",
        "icon": "mdi:speedometer-medium",
        "options_map": {
            # 0: "disabled",
            1: "auto",
            # 2: "auto_linked",
            3: "on",
            4: "off",
        },
        "register": 0x04CA,
        "register_offset": 0,
        "select_type": "relay_mode",
        "option": "use_aux3",
    },
    "relay_aux4_mode": {
        "name": "AUX4 Mode",
        "icon": "mdi:speedometer-medium",
        "options_map": {
            # 0: "disabled",
            1: "auto",
            # 2: "auto_linked",
            3: "on",
            4: "off",
        },
        "register": 0x04D9,
        "register_offset": 0,
        "select_type": "relay_mode",
        "option": "use_aux4",
    },
    "relay_light_mode": {
        "name": "Light Mode",
        "icon": "mdi:speedometer-medium",
        "options_map": {
            # 0: "disabled",
            1: "auto",
            # 2: "auto_linked",
            3: "on",
            4: "off",
        },
        "register": 0x0470,
        "register_offset": 0,
        "select_type": "relay_mode",
        "option": "use_light",
    },
    "MBF_PAR_RELAY_ACTIVATION_DELAY": {
        "icon": "mdi:timer-plus-outline",
        "register": 0x0433,
        "entity_category": EntityCategory.CONFIG,
    },
}

SWITCH_DEFINITIONS = {
    "WINTER_MODE": {
        "name": "Winter Mode",
        "icon_on": "mdi:snowflake",
        "icon_off": "mdi:weather-sunny",
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "winter_mode",
    },
    "TIME_AUTO_SYNC": {
        "name": "Automatic Time Sync",
        "icon": "mdi:home-clock-outline",
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "auto_time_sync",
    },
    "MBF_PAR_FILT_MANUAL_STATE": {
        "name": "Manual Filtration",
        "icon": "mdi:pump",
        "entity_category": None,
        "switch_type": "manual_filtration",
    },
    "MBF_PAR_CLIMA_ONOFF": {
        "name": "Climate mode",
        "icon_on": "mdi:hvac",
        "icon_off": "mdi:hvac-off",
        "function_addr": 0x0417,
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "climate_mode",
    },
    "MBF_PAR_SMART_ANTI_FREEZE": {
        "name": "Smart antifreeze",
        "icon_on": "mdi:snowflake-melt",
        "icon_off": "mdi:snowflake-alert",
        "function_addr": 0x041A,
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "smart_anti_freeze",
    },
    "MBF_PAR_UV_MODE": {
        "name": "UV Mode",
        "icon_on": "mdi:lightbulb-fluorescent-tube",
        "icon_off": "mdi:lightbulb-fluorescent-tube-outline",
        "function_addr": 0x0427,
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "uv_mode",
    },
    # "MBF_PAR_UV_HIDE_WARN_CLEAN": {
    #     "name": "Suppress UV Clean Warning",
    #     "icon": "mdi:alert-minus-outline",
    #     "function_addr": 0x0428,
    #     "mask_bit": 0x0001,
    #     "data_key": "MBF_PAR_UV_HIDE_WARN",
    #     "entity_category": EntityCategory.CONFIG,
    #     "switch_type": "bitmask",
    # },
    # "MBF_PAR_UV_HIDE_WARN_REPLACE": {
    #     "name": "Suppress UV Replace Warning",
    #     "icon": "mdi:alert-minus-outline",
    #     "function_addr": 0x0428,
    #     "mask_bit": 0x0002,
    #     "data_key": "MBF_PAR_UV_HIDE_WARN",
    #     "entity_category": EntityCategory.CONFIG,
    #     "switch_type": "bitmask",
    # },
    "MBF_PAR_HIDRO_COVER_ENABLE": {
        "name": "Hydrolysis Cover Reduction",
        "icon_on": "mdi:pool",
        "icon_off": "mdi:pool-thermometer",
        "function_addr": 0x042C,
        "mask_bit": 0x0001,
        "data_key": "MBF_PAR_HIDRO_COVER_ENABLE",
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "bitmask",
        "option": "use_cover_sensor",
    },
    "MBF_PAR_HIDRO_TEMP_SHUTDOWN": {
        "name": "Hydrolysis Temperature Shutdown",
        "icon_on": "mdi:thermometer-alert",
        "icon_off": "mdi:thermometer-off",
        "function_addr": 0x042C,
        "mask_bit": 0x0002,
        "data_key": "MBF_PAR_HIDRO_COVER_ENABLE",
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "bitmask",
        "option": "use_cover_sensor",
    },
    "aux1": {
        "name": "Auxiliary Relay 1",
        "icon_on": "mdi:electric-switch-closed",
        "icon_off": "mdi:electric-switch",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x04AC,
        "function_addr": 0x04B7,
        "function_code": 0x0800,  # AUX1 relay code
        "option": "use_aux1",
    },
    "aux2": {
        "name": "Auxiliary Relay 2",
        "icon_on": "mdi:electric-switch-closed",
        "icon_off": "mdi:electric-switch",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x04BB,
        "function_addr": 0x04C6,
        "function_code": 0x1000,  # AUX2 relay code
        "option": "use_aux2",
    },
    "aux3": {
        "name": "Auxiliary Relay 3",
        "icon_on": "mdi:electric-switch-closed",
        "icon_off": "mdi:electric-switch",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x04CA,
        "function_addr": 0x04D5,
        "function_code": 0x2000,  # AUX3 relay code
        "option": "use_aux3",
    },
    "aux4": {
        "name": "Auxiliary Relay 4",
        "icon_on": "mdi:electric-switch-closed",
        "icon_off": "mdi:electric-switch",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x04D9,
        "function_addr": 0x04E4,
        "function_code": 0x4000,  # AUX4 relay code
        "option": "use_aux4",
    },
}

LIGHT_DEFINITIONS = {
    "light": {
        "name": "Pool Light",
        "icon_on": "mdi:lightbulb-on",
        "icon_off": "mdi:lightbulb-off",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x0470,
        "function_addr": 0x047B,
        "function_code": 2,  # LIGHTING
        "option": "use_light",
    },
}
