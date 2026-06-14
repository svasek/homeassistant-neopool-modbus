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

"""Binary sensor platform for the NeoPool integration."""

from collections.abc import Mapping
import logging
from typing import Any

from neopool_modbus.registers import is_valid_relay_gpio

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NeoPoolConfigEntry
from .const import BINARY_SENSOR_DEFINITIONS
from .coordinator import NeoPoolCoordinator
from .entity import NeoPoolEntity
from .helpers import is_device_time_out_of_sync

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

DISABLED_SUFFIXES = [
    " control module",
    " module regulated",
    " measurement active",
    " pump active",
    " on target",
    " module control status",
]

# Pump status sensors are only relevant when the corresponding relay is assigned.
# MBF_PAR_*_RELAY_GPIO = 0 means no pump is configured for that function.
PUMP_RELAY_GPIO_MAP = {
    "Redox pump active": "MBF_PAR_RX_RELAY_GPIO",
    "Chlorine pump active": "MBF_PAR_CL_RELAY_GPIO",
    "Conductivity pump active": "MBF_PAR_CD_RELAY_GPIO",
}

# Binary sensors that require a valid relay GPIO to be created.
# Maps entity key → MBF_PAR register key for the relay GPIO.
RELAY_GPIO_GUARD_MAP = {
    "pH Acid Pump": "MBF_PAR_PH_ACID_RELAY_GPIO",
    "Filtration Pump": "MBF_PAR_FILT_GPIO",
    "Pool Light": "MBF_PAR_LIGHTING_GPIO",
    "Heating": "MBF_PAR_HEATING_GPIO",
}

# Suffixes used to match sensors against their measurement module detection status.
_MODULE_SUFFIXES = (
    "flow sensor problem",
    "module control status",
    "control status",
    "pump active",
    "control module",
    "measurement active",
)


def _should_skip_binary_sensor(
    key: str,
    props: dict[str, Any],
    data: dict[str, Any],
    entry_options: Mapping[str, Any],
) -> bool:
    """Return True if a binary sensor entity should not be created."""
    # Option-gated sensor
    option_key = props.get("option")
    if option_key and not entry_options.get(option_key, False):
        return True

    # Skip ION entities if ionization module not present
    if key.startswith("ION ") and not bool((data.get("MBF_PAR_MODEL") or 0) & 0x0001):
        return True  # pragma: no cover

    # Skip HIDRO entities if no hydrolysis module is installed
    if key.startswith("HIDRO ") and not data.get("Hydrolysis module detected"):
        return True

    # Skip sensors whose relay GPIO is not assigned.
    # Only enforce when the GPIO key is present in data; a missing key
    # (e.g. old capability snapshot) must not suppress the entity.
    if key in RELAY_GPIO_GUARD_MAP:
        gpio_key = RELAY_GPIO_GUARD_MAP[key]
        if gpio_key in data and not is_valid_relay_gpio(data[gpio_key] or 0):
            return True

    # Skip UV Lamp if UV relay is not assigned
    if key == "UV Lamp" and "MBF_PAR_UV_RELAY_GPIO" in data:
        if not is_valid_relay_gpio(data["MBF_PAR_UV_RELAY_GPIO"] or 0):
            return True

    # Skip pump status sensors if no relay is assigned for that pump
    if key in PUMP_RELAY_GPIO_MAP:
        gpio_key = PUMP_RELAY_GPIO_MAP[key]
        if gpio_key in data and not is_valid_relay_gpio(data[gpio_key] or 0):
            return True

    # Hide all "measurement module detected" sensors
    if "measurement module detected" in key.lower():
        return True

    # Skip chlorine related sensors
    if (
        key.endswith("Activated by the CL module")
        and data.get("Chlorine measurement module detected") is not True
    ):
        return True

    # Skip redox related sensors
    if (
        key.endswith("Activated by the RX module")
        and data.get("Redox measurement module detected") is not True
    ):
        return True  # pragma: no cover

    # Hide selected sensors if their 'measurement module detected' status is False.
    key_lower = key.lower()
    for suffix in _MODULE_SUFFIXES:
        if key_lower.endswith(suffix):
            prefix = key_lower[: -len(suffix)].strip()
            for data_key in data:
                if data_key.lower().startswith(prefix) and data_key.lower().endswith(
                    "measurement module detected"
                ):
                    if not data.get(data_key):  # pragma: no cover
                        return True
            break  # Only one suffix can match; no need to continue

    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool binary sensors from a config entry."""
    coordinator = entry.runtime_data
    entities = []

    if coordinator.data is None:
        _LOGGER.warning("No data from Modbus, skipping binary_sensor setup!")
        return

    for key, props in BINARY_SENSOR_DEFINITIONS.items():
        if _should_skip_binary_sensor(key, props, coordinator.data, entry.options):
            continue

        sensor_props = dict(props)

        # Check if the entity should be enabled by default
        # Disable some entities by default based on their key
        if any(key.lower().endswith(suf.lower()) for suf in DISABLED_SUFFIXES):
            sensor_props["enabled_default"] = False
        else:
            sensor_props["enabled_default"] = True

        entities.append(
            NeoPoolBinarySensor(
                coordinator,
                entry.entry_id,  # Pass entry_id explicitly
                key,  # Pass key as a positional argument
                sensor_props,
            )
        )
    async_add_entities(entities)


class NeoPoolBinarySensor(NeoPoolEntity, BinarySensorEntity):
    """Representation of a NeoPool binary sensor."""

    _winter_mode_active = False  # binary sensors stay available during winter mode

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        props: dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry_id)
        self._key = key
        self._bit: str | None = None
        self._base: str | None = None

        # Parse key if it is a status flag (e.g., "PH_STATUS_regulating")
        if "_STATUS_" in key:  # pragma: no cover
            self._base, self._bit = key.split("_STATUS_", 1)

        self._key = key
        # Use entry.unique_id (serial-based in v2+) for stable identity, fallback to entry_id
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{self._key.lower()}"
        self._attr_translation_key = NeoPoolEntity.slugify(self._key)

        self._attr_device_class = props.get("device_class") or None
        self._attr_entity_category = props.get("entity_category") or None

        self._attr_entity_registry_enabled_default = props.get("enabled_default", True)

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
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on."""
        if self._key == "Device Time Out Of Sync":
            if self.coordinator.data.get("MBF_PAR_TIME_LOW") is None:
                return None
            return is_device_time_out_of_sync(self.coordinator.data, self.hass)

        # Pool Cover: Invert logic for OPENING device class
        # Hardware: 1 = cover active (pool covered), 0 = cover inactive (pool uncovered)
        # HA OPENING: ON = open (uncovered), OFF = closed (covered)
        if self._key == "Pool Cover":
            value = self.coordinator.data.get(self._key)
            if value is None:
                return None
            return not bool(value)

        # Check if the filtration pump is active
        key_slug = NeoPoolEntity.slugify(self._key)
        if key_slug.endswith("_measurement_active") or key_slug.endswith(
            "_module_active"
        ):
            filtration_state = self.coordinator.data.get("Filtration Pump")
            if filtration_state is not None and filtration_state is False:
                return False

        if "_STATUS_" in self._key:  # pragma: no cover
            base, flag = self._key.split("_STATUS_", 1)
            status = self.coordinator.data.get(f"{base}_STATUS", {})
            if isinstance(status, dict):
                return status.get(flag.lower())
            return None
        value = self.coordinator.data.get(self._key)
        return None if value is None else bool(value)

    @property
    def native_value(self) -> bool | None:
        """Return the actual sensor value."""
        # Return the actual sensor value from coordinator data
        return self.coordinator.data.get(self._key)  # pragma: no cover
