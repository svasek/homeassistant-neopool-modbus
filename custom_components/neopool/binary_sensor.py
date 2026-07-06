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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from neopool_modbus.capabilities import is_ionization_present
from neopool_modbus.registers import is_valid_relay_gpio

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NeoPoolConfigEntry, NeoPoolCoordinator
from .entity import NeoPoolEntity
from .helpers import is_device_time_out_of_sync

PARALLEL_UPDATES = 0

type _SupportedFn = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True, kw_only=True)
class NeoPoolBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a NeoPool binary sensor entity."""

    supported_fn: _SupportedFn | None = None
    value_fn: Callable[[dict[str, Any], HomeAssistant], bool | None] | None = None


def _gpio_ok(gpio_key: str) -> _SupportedFn:
    """Return a supported_fn that checks a relay GPIO key is valid."""
    return lambda data: gpio_key not in data or is_valid_relay_gpio(data[gpio_key] or 0)


def _module_detected(module_key: str) -> _SupportedFn:
    """Return a supported_fn that requires a measurement module to be detected."""
    return lambda data: bool(data.get(module_key))


def _device_time_drift(data: dict[str, Any], hass: HomeAssistant) -> bool | None:
    """Compute whether the device clock is out of sync with HA."""
    if data.get("MBF_PAR_TIME") is None:
        return None
    return is_device_time_out_of_sync(data, hass)


def _pool_cover_open(data: dict[str, Any], hass: HomeAssistant) -> bool | None:
    """Invert the raw cover state to match BinarySensorDeviceClass.OPENING semantics."""
    value = data.get("Pool Cover")
    if value is None:
        return None
    return not bool(value)


BINARY_SENSOR_DESCRIPTIONS: dict[str, NeoPoolBinarySensorEntityDescription] = {
    "Device Time Out Of Sync": NeoPoolBinarySensorEntityDescription(
        key="Device Time Out Of Sync",
        translation_key="device_time_out_of_sync",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_device_time_drift,
    ),
    # Relay states
    "pH Acid Pump": NeoPoolBinarySensorEntityDescription(
        key="pH Acid Pump",
        translation_key="ph_acid_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=_gpio_ok("MBF_PAR_PH_ACID_RELAY_GPIO"),
    ),
    "Filtration Pump": NeoPoolBinarySensorEntityDescription(
        key="Filtration Pump",
        translation_key="filtration_pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        supported_fn=_gpio_ok("MBF_PAR_FILT_GPIO"),
    ),
    "Pool Light": NeoPoolBinarySensorEntityDescription(
        key="Pool Light",
        translation_key="pool_light",
        device_class=BinarySensorDeviceClass.LIGHT,
        supported_fn=_gpio_ok("MBF_PAR_LIGHTING_GPIO"),
    ),
    "AUX1": NeoPoolBinarySensorEntityDescription(
        key="AUX1",
        translation_key="aux1",
        device_class=BinarySensorDeviceClass.POWER,
    ),
    "AUX2": NeoPoolBinarySensorEntityDescription(
        key="AUX2",
        translation_key="aux2",
        device_class=BinarySensorDeviceClass.POWER,
    ),
    "AUX3": NeoPoolBinarySensorEntityDescription(
        key="AUX3",
        translation_key="aux3",
        device_class=BinarySensorDeviceClass.POWER,
    ),
    "AUX4": NeoPoolBinarySensorEntityDescription(
        key="AUX4",
        translation_key="aux4",
        device_class=BinarySensorDeviceClass.POWER,
    ),
    "pH module control status": NeoPoolBinarySensorEntityDescription(
        key="pH module control status",
        translation_key="ph_module_control_status",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("pH measurement module detected"),
    ),
    "pH control module": NeoPoolBinarySensorEntityDescription(
        key="pH control module",
        translation_key="ph_control_module",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("pH measurement module detected"),
    ),
    "pH measurement active": NeoPoolBinarySensorEntityDescription(
        key="pH measurement active",
        translation_key="ph_measurement_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("pH measurement module detected"),
    ),
    "Redox pump active": NeoPoolBinarySensorEntityDescription(
        key="Redox pump active",
        translation_key="redox_pump_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=lambda data: (
            bool(data.get("Redox measurement module detected"))
            and (
                "MBF_PAR_RX_RELAY_GPIO" not in data
                or is_valid_relay_gpio(data["MBF_PAR_RX_RELAY_GPIO"] or 0)
            )
        ),
    ),
    "Redox control module": NeoPoolBinarySensorEntityDescription(
        key="Redox control module",
        translation_key="redox_control_module",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("Redox measurement module detected"),
    ),
    "Redox measurement active": NeoPoolBinarySensorEntityDescription(
        key="Redox measurement active",
        translation_key="redox_measurement_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("Redox measurement module detected"),
    ),
    "Chlorine flow sensor problem": NeoPoolBinarySensorEntityDescription(
        key="Chlorine flow sensor problem",
        translation_key="chlorine_flow_sensor_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=_module_detected("Chlorine measurement module detected"),
    ),
    "Chlorine pump active": NeoPoolBinarySensorEntityDescription(
        key="Chlorine pump active",
        translation_key="chlorine_pump_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=lambda data: (
            bool(data.get("Chlorine measurement module detected"))
            and (
                "MBF_PAR_CL_RELAY_GPIO" not in data
                or is_valid_relay_gpio(data["MBF_PAR_CL_RELAY_GPIO"] or 0)
            )
        ),
    ),
    "Chlorine control module": NeoPoolBinarySensorEntityDescription(
        key="Chlorine control module",
        translation_key="chlorine_control_module",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("Chlorine measurement module detected"),
    ),
    "Chlorine measurement active": NeoPoolBinarySensorEntityDescription(
        key="Chlorine measurement active",
        translation_key="chlorine_measurement_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("Chlorine measurement module detected"),
    ),
    "Conductivity pump active": NeoPoolBinarySensorEntityDescription(
        key="Conductivity pump active",
        translation_key="conductivity_pump_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=lambda data: (
            bool(data.get("Conductivity measurement module detected"))
            and (
                "MBF_PAR_CD_RELAY_GPIO" not in data
                or is_valid_relay_gpio(data["MBF_PAR_CD_RELAY_GPIO"] or 0)
            )
        ),
    ),
    "Conductivity control module": NeoPoolBinarySensorEntityDescription(
        key="Conductivity control module",
        translation_key="conductivity_control_module",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("Conductivity measurement module detected"),
    ),
    "Conductivity measurement active": NeoPoolBinarySensorEntityDescription(
        key="Conductivity measurement active",
        translation_key="conductivity_measurement_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("Conductivity measurement module detected"),
    ),
    "ION On Target": NeoPoolBinarySensorEntityDescription(
        key="ION On Target",
        translation_key="ion_on_target",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=lambda data: is_ionization_present(data),  # pragma: no cover
    ),
    "ION Low Flow": NeoPoolBinarySensorEntityDescription(
        key="ION Low Flow",
        translation_key="ion_low_flow",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=lambda data: is_ionization_present(data),  # pragma: no cover
    ),
    "ION Program time exceeded": NeoPoolBinarySensorEntityDescription(
        key="ION Program time exceeded",
        translation_key="ion_program_time_exceeded",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=lambda data: is_ionization_present(data),  # pragma: no cover
    ),
    "HIDRO Low Flow": NeoPoolBinarySensorEntityDescription(
        key="HIDRO Low Flow",
        translation_key="hidro_low_flow",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=_module_detected("Hydrolysis module detected"),
    ),
    "Pool Cover": NeoPoolBinarySensorEntityDescription(
        key="Pool Cover",
        translation_key="pool_cover",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=_pool_cover_open,
    ),
    "HIDRO Module active": NeoPoolBinarySensorEntityDescription(
        key="HIDRO Module active",
        translation_key="hidro_module_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=_module_detected("Hydrolysis module detected"),
    ),
    "HIDRO Module regulated": NeoPoolBinarySensorEntityDescription(
        key="HIDRO Module regulated",
        translation_key="hidro_module_regulated",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        supported_fn=_module_detected("Hydrolysis module detected"),
    ),
    "HIDRO Activated by the RX module": NeoPoolBinarySensorEntityDescription(
        key="HIDRO Activated by the RX module",
        translation_key="hidro_activated_by_the_rx_module",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=lambda data: (
            bool(data.get("Hydrolysis module detected"))
            and bool(data.get("Redox measurement module detected"))
        ),  # pragma: no cover
    ),
    "HIDRO Chlorine shock mode": NeoPoolBinarySensorEntityDescription(
        key="HIDRO Chlorine shock mode",
        translation_key="hidro_chlorine_shock_mode",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=_module_detected("Hydrolysis module detected"),
    ),
    "HIDRO Activated by the CL module": NeoPoolBinarySensorEntityDescription(
        key="HIDRO Activated by the CL module",
        translation_key="hidro_activated_by_the_cl_module",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=lambda data: (
            bool(data.get("Hydrolysis module detected"))
            and bool(data.get("Chlorine measurement module detected"))
        ),
    ),
    "Heating": NeoPoolBinarySensorEntityDescription(
        key="Heating",
        translation_key="heating",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=_gpio_ok("MBF_PAR_HEATING_GPIO"),
    ),
    "UV Lamp": NeoPoolBinarySensorEntityDescription(
        key="UV Lamp",
        translation_key="uv_lamp",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        supported_fn=lambda data: (
            "MBF_PAR_UV_RELAY_GPIO" not in data
            or is_valid_relay_gpio(data["MBF_PAR_UV_RELAY_GPIO"] or 0)
        ),
    ),
}


_MEASUREMENT_SUFFIXES = ("_measurement_active", "_module_active")


# Entities gated on a config-entry option (in addition to their supported_fn).
_ENTITY_OPTION_KEY: dict[str, str] = {
    "Pool Light": "use_light",
    "AUX1": "use_aux1",
    "AUX2": "use_aux2",
    "AUX3": "use_aux3",
    "AUX4": "use_aux4",
    "Pool Cover": "use_cover_sensor",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool binary sensors from a config entry."""
    coordinator = entry.runtime_data
    options = entry.options

    async_add_entities(
        NeoPoolBinarySensor(coordinator, entry.entry_id, key, desc)
        for key, desc in BINARY_SENSOR_DESCRIPTIONS.items()
        if (
            (option_key := _ENTITY_OPTION_KEY.get(key)) is None
            or bool(options.get(option_key))
        )
        and (desc.supported_fn is None or desc.supported_fn(coordinator.data))
    )


class NeoPoolBinarySensor(NeoPoolEntity, BinarySensorEntity):
    """Representation of a NeoPool binary sensor."""

    _winter_mode_active = False
    entity_description: NeoPoolBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        description: NeoPoolBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._key = key
        self._attr_unique_id = f"{self.coordinator.entry.unique_id}_{key.lower()}"

    @property
    @override
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on."""
        if (value_fn := self.entity_description.value_fn) is not None:
            value: bool | None = value_fn(self.coordinator.data, self.hass)
            return value
        if self._is_measurement_active_suppressed():
            return False
        value = self.coordinator.data.get(self._key)
        return None if value is None else bool(value)

    def _is_measurement_active_suppressed(self) -> bool:
        """Return True if a "*_measurement_active" / "*_module_active" flag should be forced off."""
        translation_key = self.entity_description.translation_key or ""
        if not translation_key.endswith(_MEASUREMENT_SUFFIXES):
            return False
        return self.coordinator.data.get("Filtration Pump") is False
