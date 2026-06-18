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
from typing import Any

from neopool_modbus.decoders import is_hydrolysis_in_percent
from neopool_modbus.registers import (
    CHLORINE_SETPOINT_REGISTER,
    HEATING_SETPOINT_REGISTER,
    HIDRO_COVER_REGISTER,
    HIDRO_SETPOINT_REGISTER,
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
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NeoPoolConfigEntry
from .coordinator import NeoPoolCoordinator
from .entity import NeoPoolEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

type SupportedFn = Callable[[dict[str, Any], Mapping[str, Any]], bool]


@dataclass(frozen=True, kw_only=True)
class NeoPoolNumberEntityDescription(NumberEntityDescription):
    """Describes a NeoPool number entity."""

    register: int = 0
    scale: float = 1.0
    mask: int | None = None
    shift: int = 0
    data_key: str | None = None
    supported_fn: SupportedFn | None = None


def _support_heating_temp(data: dict[str, Any], opts: Mapping[str, Any]) -> bool:
    if "MBF_PAR_HEATING_GPIO" in data and not is_valid_relay_gpio(
        data["MBF_PAR_HEATING_GPIO"] or 0
    ):
        return False
    return bool(data.get("MBF_PAR_TEMPERATURE_ACTIVE"))


NUMBER_DESCRIPTIONS: dict[str, NeoPoolNumberEntityDescription] = {
    "MBF_PAR_HIDRO": NeoPoolNumberEntityDescription(
        key="MBF_PAR_HIDRO",
        native_unit_of_measurement="%",
        native_min_value=0.0,
        native_max_value=100.0,
        native_step=1.0,
        register=HIDRO_SETPOINT_REGISTER,
        scale=10.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: bool(data.get("Hydrolysis module detected")),
    ),
    "MBF_PAR_PH1": NeoPoolNumberEntityDescription(
        key="MBF_PAR_PH1",
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
        native_unit_of_measurement="mV",
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
        native_unit_of_measurement="ppm",
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
        native_unit_of_measurement="°C",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=0.0,
        native_max_value=40.0,
        native_step=1.0,
        register=HEATING_SETPOINT_REGISTER,
        scale=1.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=_support_heating_temp,
    ),
    "MBF_PAR_SMART_TEMP_HIGH": NeoPoolNumberEntityDescription(
        key="MBF_PAR_SMART_TEMP_HIGH",
        native_unit_of_measurement="°C",
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
        native_unit_of_measurement="°C",
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
        native_unit_of_measurement="%",
        native_min_value=0.0,
        native_max_value=100.0,
        native_step=1.0,
        register=HIDRO_COVER_REGISTER,
        data_key="MBF_PAR_HIDRO_COVER_REDUCTION",
        mask=0x00FF,
        shift=0,
        scale=1.0,
        entity_category=EntityCategory.CONFIG,
        supported_fn=lambda data, opts: bool(opts.get("use_cover_sensor")),
    ),
    "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE": NeoPoolNumberEntityDescription(
        key="MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE",
        native_unit_of_measurement="°C",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=1.0,
        native_max_value=40.0,
        native_step=1.0,
        register=HIDRO_COVER_REGISTER,
        data_key="MBF_PAR_HIDRO_COVER_REDUCTION",
        mask=0xFF00,
        shift=8,
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

        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{key.lower()}"
        self._attr_translation_key = NeoPoolEntity.slugify(key)
        self._attr_mode = NumberMode.BOX

        self._pending_write_task: asyncio.Task[None] | None = None
        self._pending_value: float | None = None
        self._debounce_delay = 2.0

    async def async_added_to_hass(self) -> None:
        """Run when the entity is added to hass."""
        _LOGGER.debug(
            "ADDED: entity_id=%s, translation_key=%s, has_entity_name=%s",
            self.entity_id,
            self.translation_key,
            getattr(self, "has_entity_name", None),
        )
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

    async def async_set_native_value(self, value: float) -> None:
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
                    "Winter mode is active — debounced write cancelled for %s",
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
        if self._key == "MBF_PAR_HIDRO":
            # 0 decimals in percent mode, 1 decimal in g/h mode
            return 0 if is_hydrolysis_in_percent(self.coordinator.data) else 1
        if self._key == "MBF_PAR_HEATING_TEMP":
            return 0
        return None

    @property
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
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement for the number value."""
        if self._key == "MBF_PAR_HIDRO":
            return "%" if is_hydrolysis_in_percent(self.coordinator.data) else "g/h"
        return self.entity_description.native_unit_of_measurement

    @property
    def native_max_value(self) -> float:
        """Return the maximum value for the number entity."""
        if self._key == "MBF_PAR_HIDRO":
            hidro_nom = self.coordinator.data.get("MBF_PAR_HIDRO_NOM")
            if hidro_nom is not None:
                return float(hidro_nom)
        return self.entity_description.native_max_value or super().native_max_value

    @property
    def native_step(self) -> float | None:
        """Return the step value for the number entity."""
        if self._key == "MBF_PAR_HIDRO":
            return 1.0 if is_hydrolysis_in_percent(self.coordinator.data) else 0.1
        return self.entity_description.native_step
