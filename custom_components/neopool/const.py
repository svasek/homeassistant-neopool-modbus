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

from neopool_modbus.capabilities import CAPABILITY_KEYS as LIB_CAPABILITY_KEYS

from homeassistant.const import Platform

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
    Platform.TIME,
]

DEFAULT_SCAN_INTERVAL = 20  # in seconds
FOLLOW_UP_REFRESH_DELAY = 2.0  # seconds  (delay before a 2nd refresh for IO entity)
DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
CONF_FILTRATION_PUMP_POWER = "filtration_pump_power"

CURRENT_VERSION = 6

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
