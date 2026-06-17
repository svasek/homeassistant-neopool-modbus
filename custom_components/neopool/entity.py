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

"""Base entity class for the NeoPool integration.

This module defines the base entity class for the NeoPool integration.
It provides common functionality for all entities, including device information,
"""

from neopool_modbus.decoders import (
    decode_par_model_modules,
    get_machine_name,
    modbus_regs_to_hex_string,
    parse_version,
)

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify as ha_slugify

from .const import DOMAIN, NAME
from .coordinator import NeoPoolCoordinator

_MODULE_LABELS: dict[str, str] = {
    "ionization": "Ionization",
    "hydrolysis": "Hydro/Electrolysis",
    "uv_lamp": "UV Lamp",
    "salinity": "Salinity",
}


class NeoPoolEntity(CoordinatorEntity[NeoPoolCoordinator]):
    """Base class for NeoPool entities."""

    _attr_has_entity_name = True
    _winter_mode_active: bool = True

    def __init__(self, coordinator: NeoPoolCoordinator, entry_id: str) -> None:
        """Initialise the NeoPool base entity."""
        super().__init__(coordinator)
        self._entry_id = entry_id

    @property
    def available(self) -> bool:
        """Return False for control entities while winter mode is active."""
        if self._winter_mode_active and getattr(self.coordinator, "winter_mode", False):
            return False
        return super().available

    @property
    def translation_key(self) -> str | None:
        """Return the translation key for the entity."""
        return getattr(self, "_attr_translation_key", None)  # pragma: no cover

    @property
    def device_info(self) -> DeviceInfo:  # pragma: no cover
        """Return device information for the entity."""
        data = self.coordinator.data or {}
        serial_number = modbus_regs_to_hex_string(data.get("MBF_POWER_MODULE_NODEID"))

        # Use entry.unique_id (serial-based in v2+) as device identifier,
        # otherwise fall back to entry_id. Never use serial_number as identifier
        # to avoid mid-run device identity flips when migration was deferred.
        hw_identifier = self.coordinator.entry.unique_id or self._entry_id

        machine_type = (get_machine_name(data) or "").strip()
        model_prefix = "NeoPool Compatible: " if machine_type else "NeoPool Compatible"

        return DeviceInfo(
            identifiers={(DOMAIN, hw_identifier)},
            name=getattr(self.coordinator, "device_name", NAME),
            model=f"{model_prefix}{machine_type}".strip(),
            manufacturer="Hayward (Sugar Valley)",
            hw_version=f"Detected Modules: [{self._format_modules(data)}]",
            sw_version=f"v{self.coordinator.firmware} (v{parse_version(data.get('MBF_PAR_VERSION'))})",
            serial_number=serial_number,
        )

    # Generate a unique object ID for the entity to use in Home Assistant
    # This remove the prefix "mbf_" and "par_" from the key and replaces spaces, dashes, and dots with underscores
    @staticmethod
    def slugify(name: str) -> str:
        """Convert a name to a slug suitable for use as an object ID."""
        if not name:
            return ""
        return ha_slugify(name.lower().replace("mbf_", "", 1).replace("par_", "", 1))

    @staticmethod
    def _format_modules(data: dict) -> str:
        """Render installed_modules as the hw_version label."""
        modules = data.get("installed_modules")
        if modules is None:
            # First paint: coordinator data not yet populated.
            modules = decode_par_model_modules(data.get("MBF_PAR_MODEL"))
        if not modules:
            return "None" if data.get("MBF_PAR_MODEL") is not None else "Unknown"
        return ", ".join(_MODULE_LABELS.get(m, m) for m in modules)
