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
