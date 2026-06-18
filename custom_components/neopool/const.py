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

"""Constants for the NeoPool integration."""

import logging
from typing import Any

from neopool_modbus.capabilities import CAPABILITY_KEYS as LIB_CAPABILITY_KEYS

from homeassistant.components.number import NumberDeviceClass
from homeassistant.const import EntityCategory, Platform

DOMAIN = "neopool"
NAME = "NeoPool"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

LOGGER = logging.getLogger(__name__)

DEFAULT_TIMER_RESOLUTION = 15  # in minutes
DEFAULT_SCAN_INTERVAL = 20  # in seconds
FOLLOW_UP_REFRESH_DELAY = (
    2.0  # seconds — delay before a second refresh after IO entity actions
)
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
CONF_FILTRATION_PUMP_POWER = "filtration_pump_power"

CURRENT_VERSION = 4


# Persisted in entry.options for winter-mode restarts.
_CUSTOM_CAPABILITY_KEYS: tuple[str, ...] = (
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
)

CAPABILITY_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys((*LIB_CAPABILITY_KEYS, *_CUSTOM_CAPABILITY_KEYS))
)

REMOVED_ENTITY_KEYS = (
    # Removed in PR #117
    "ion in dead time",
    "ion in pol1",
    "ion in pol2",
    "hidro in dead time",
    "hidro in pol1",
    "hidro in pol2",
    # Removed in PR #118
    "hidro on target",
    "hidro chlorine flow indicator fl2",
    "hidro cell flow fl1",
    # Removed in PR #119
    "ph acid pump active",
    "ph pump active",
    # Added in PR #140
    "ph regulation out of range",
    "redox regulation out of range",
    "chlorine regulation out of range",
    "conductivity regulation out of range",
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


NUMBER_DEFINITIONS: dict[str, dict[str, Any]] = {
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
    },
    "MBF_PAR_PH1": {
        "name": "pH Max Limit",
        "min": 0.0,
        "max": 14.0,
        "step": 0.1,
        "register": 0x0504,  # MBF_PAR_PH1
        "scale": 100.0,
        "device_class": NumberDeviceClass.PH,
        "entity_category": EntityCategory.CONFIG,
    },
    "MBF_PAR_PH2": {
        "name": "pH Min Limit",
        "min": 0.0,
        "max": 14.0,
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
        "option": "use_cover_sensor",
    },
}

BUTTON_DEFINITIONS: dict[str, dict[str, Any]] = {
    "SYNC_TIME": {
        "name": "Synchronize Device Time",
        "entity_category": EntityCategory.CONFIG,
    },
    "MBF_ESCAPE": {
        "name": "Clear Errors",
        "entity_category": EntityCategory.CONFIG,
    },
    "BACKWASH": {
        "name": "Start Backwash",
    },
    "RESET_CELL_PARTIAL": {
        "name": "Reset Partial Cell Runtime",
        "entity_category": EntityCategory.CONFIG,
        "entity_registry_enabled_default": False,
    },
}

SELECT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "MBF_PAR_FILT_MODE": {
        "name": "Filtration Mode",
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
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "register": 0x050F,
        "mask": 0x0070,
        "shift": 4,
    },
    "MBF_CELL_BOOST": {
        "name": "Boost Mode",
        "options_map": {
            0: "inactive",
            1: "active",
            2: "active_redox",
        },
        "register": 0x020C,
    },
    "MBF_PAR_FILTVALVE_MODE": {
        "name": "Backwash Valve Mode",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {
            # 0: "disabled",     # valve disabled - hidden (covered by MBF_PAR_FILTVALVE_ENABLE)
            1: "enabled",  # timer-controlled (MBV_PAR_CTIMER_ENABLED)
            # 2: "auto_linked",  # linked to parent relay - not applicable for filtvalve
            3: "always_on",  # MBV_PAR_CTIMER_ALWAYS_ON
            4: "always_off",  # MBV_PAR_CTIMER_ALWAYS_OFF
        },
        "register": 0x04E9,
    },
    "MBF_PAR_FILTVALVE_PERIOD_MINUTES": {
        "name": "Backwash Repeat Interval",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "mapped_register",
        "fallback_suffix": "m",
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
    "MBF_PAR_INTELLIGENT_FILT_MIN_TIME": {
        "name": "Intelligent Min Filtration Time",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "mapped_register",
        "fallback_suffix": "m",
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
    "MBF_PAR_RELAY_ACTIVATION_DELAY": {
        "register": 0x0433,
        "entity_category": EntityCategory.CONFIG,
        "select_type": "mapped_register",
        "write_offset": -10,  # Device adds +10s internally
        "options_map": {
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
    },
    "filtration1_start": {
        "name": "Filtration Timer 1 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration1",
    },
    "filtration1_stop": {
        "name": "Filtration Timer 1 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration1",
    },
    "filtration2_start": {
        "name": "Filtration Timer 2 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration2",
    },
    "filtration2_stop": {
        "name": "Filtration Timer 2 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration2",
    },
    "filtration3_start": {
        "name": "Filtration Timer 3 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration3",
    },
    "filtration3_stop": {
        "name": "Filtration Timer 3 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_filtration3",
    },
    "filtration1_speed": {
        "name": "Timer 1 - Filtration Speed",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "register": 0x050F,
        "mask": 0x0380,
        "shift": 7,
        "option": "use_filtration1",
    },
    "filtration2_speed": {
        "name": "Timer 2 - Filtration Speed",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "register": 0x050F,
        "mask": 0x1C00,
        "shift": 10,
        "option": "use_filtration2",
    },
    "filtration3_speed": {
        "name": "Timer 3 - Filtration Speed",
        "entity_category": EntityCategory.CONFIG,
        "options_map": {0: "low", 1: "mid", 2: "high"},
        "register": 0x050F,
        "mask": 0xE000,
        "shift": 13,
        "option": "use_filtration3",
    },
    "relay_aux1_start": {
        "name": "Relay AUX1 Timer 1 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1_stop": {
        "name": "Relay AUX1 Timer 1 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1_period": {
        "name": "Relay AUX1 Timer 1 Repeat",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1b_start": {
        "name": "Relay AUX1 Timer 2 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1b_stop": {
        "name": "Relay AUX1 Timer 2 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux1b_period": {
        "name": "Relay AUX1 Timer 2 Repeat",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux1",
    },
    "relay_aux2_start": {
        "name": "Relay AUX2 Timer 1 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2_stop": {
        "name": "Relay AUX2 Timer 1 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2_period": {
        "name": "Relay AUX2 Timer 1 Repeat",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2b_start": {
        "name": "Relay AUX2 Timer 2 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2b_stop": {
        "name": "Relay AUX2 Timer 2 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux2b_period": {
        "name": "Relay AUX2 Timer 2 Repeat",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux2",
    },
    "relay_aux3_start": {
        "name": "Relay AUX3 Timer 1 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3_stop": {
        "name": "Relay AUX3 Timer 1 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3_period": {
        "name": "Relay AUX3 Timer 1 Repeat",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3b_start": {
        "name": "Relay AUX3 Timer 2 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3b_stop": {
        "name": "Relay AUX3 Timer 2 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux3b_period": {
        "name": "Relay AUX3 Timer 2 Repeat",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux3",
    },
    "relay_aux4_start": {
        "name": "Relay AUX4 Timer 1 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4_stop": {
        "name": "Relay AUX4 Timer 1 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4_period": {
        "name": "Relay AUX4 Timer 1 Repeat",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4b_start": {
        "name": "Relay AUX4 Timer 2 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4b_stop": {
        "name": "Relay AUX4 Timer 2 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_aux4",
    },
    "relay_aux4b_period": {
        "name": "Relay AUX4 Timer 2 Repeat",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_aux4",
    },
    "relay_light_start": {
        "name": "Relay Light Timer 1 Start",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_light",
    },
    "relay_light_stop": {
        "name": "Relay Light Timer 1 Stop",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_time",
        "register": None,
        "option": "use_light",
    },
    "relay_light_period": {
        "name": "Relay Light Timer 1 Repeat",
        "entity_category": EntityCategory.CONFIG,
        "select_type": "timer_period",
        "register": None,
        "option": "use_light",
    },
    "relay_aux1_mode": {
        "name": "AUX1 Mode",
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
}

SWITCH_DEFINITIONS: dict[str, dict[str, Any]] = {
    "WINTER_MODE": {
        "name": "Winter Mode",
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "winter_mode",
    },
    "TIME_AUTO_SYNC": {
        "name": "Automatic Time Sync",
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "auto_time_sync",
    },
    "MBF_PAR_FILT_MANUAL_STATE": {
        "name": "Manual Filtration",
        "entity_category": None,
        "switch_type": "manual_filtration",
    },
    "MBF_PAR_CLIMA_ONOFF": {
        "name": "Climate mode",
        "function_addr": 0x0417,
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "climate_mode",
    },
    "MBF_PAR_SMART_ANTI_FREEZE": {
        "name": "Smart antifreeze",
        "function_addr": 0x041A,
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "smart_anti_freeze",
    },
    "MBF_PAR_UV_MODE": {
        "name": "UV Mode",
        "function_addr": 0x0427,
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "uv_mode",
    },
    # "MBF_PAR_UV_HIDE_WARN_CLEAN": {
    #     "name": "Suppress UV Clean Warning",
    #     "function_addr": 0x0428,
    #     "mask_bit": 0x0001,
    #     "data_key": "MBF_PAR_UV_HIDE_WARN",
    #     "entity_category": EntityCategory.CONFIG,
    #     "switch_type": "bitmask",
    # },
    # "MBF_PAR_UV_HIDE_WARN_REPLACE": {
    #     "name": "Suppress UV Replace Warning",
    #     "function_addr": 0x0428,
    #     "mask_bit": 0x0002,
    #     "data_key": "MBF_PAR_UV_HIDE_WARN",
    #     "entity_category": EntityCategory.CONFIG,
    #     "switch_type": "bitmask",
    # },
    "MBF_PAR_HIDRO_COVER_ENABLE": {
        "name": "Hydrolysis Cover Reduction",
        "function_addr": 0x042C,
        "mask_bit": 0x0001,
        "data_key": "MBF_PAR_HIDRO_COVER_ENABLE",
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "bitmask",
        "option": "use_cover_sensor",
    },
    "MBF_PAR_HIDRO_TEMP_SHUTDOWN": {
        "name": "Hydrolysis Temperature Shutdown",
        "function_addr": 0x042C,
        "mask_bit": 0x0002,
        "data_key": "MBF_PAR_HIDRO_COVER_ENABLE",
        "entity_category": EntityCategory.CONFIG,
        "switch_type": "bitmask",
        "option": "use_cover_sensor",
    },
    "aux1": {
        "name": "Auxiliary Relay 1",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x04AC,
        "function_addr": 0x04B7,
        "function_code": 0x0800,  # AUX1 relay code
        "option": "use_aux1",
    },
    "aux2": {
        "name": "Auxiliary Relay 2",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x04BB,
        "function_addr": 0x04C6,
        "function_code": 0x1000,  # AUX2 relay code
        "option": "use_aux2",
    },
    "aux3": {
        "name": "Auxiliary Relay 3",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x04CA,
        "function_addr": 0x04D5,
        "function_code": 0x2000,  # AUX3 relay code
        "option": "use_aux3",
    },
    "aux4": {
        "name": "Auxiliary Relay 4",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x04D9,
        "function_addr": 0x04E4,
        "function_code": 0x4000,  # AUX4 relay code
        "option": "use_aux4",
    },
}

LIGHT_DEFINITIONS: dict[str, dict[str, Any]] = {
    "light": {
        "name": "Pool Light",
        "switch_type": "relay_timer",
        "timer_block_addr": 0x0470,
        "function_addr": 0x047B,
        "function_code": 2,  # LIGHTING
        "option": "use_light",
    },
}
