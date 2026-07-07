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

"""Light platform for the NeoPool integration."""

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any, override

from neopool_modbus.registers import (
    EXEC_REGISTER,
    LIGHT_FUNCTION_REGISTER,
    LIGHT_TIMER_BLOCK_REGISTER,
    TimerRelayMode,
    is_valid_relay_gpio,
)

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import NeoPoolConfigEntry, NeoPoolCoordinator
from .entity import NeoPoolEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# Values written to well-known registers when driving the light relay.
# See neopool_modbus.registers for the register spec.
_LIGHTING_FUNCTION_CODE = 2
_EXEC_COMMIT = 1


@dataclass(frozen=True, kw_only=True)
class NeoPoolLightEntityDescription(LightEntityDescription):
    """Describes a NeoPool light entity."""

    supported_fn: Callable[[dict[str, Any]], bool] | None = None


LIGHT_DESCRIPTIONS: dict[str, NeoPoolLightEntityDescription] = {
    "light": NeoPoolLightEntityDescription(
        key="light",
        translation_key="light",
        supported_fn=lambda data: (
            "MBF_PAR_LIGHTING_GPIO" not in data
            or is_valid_relay_gpio(data["MBF_PAR_LIGHTING_GPIO"] or 0)
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool lights from a config entry."""
    coordinator = entry.runtime_data

    if not entry.options.get("use_light"):
        return

    async_add_entities(
        NeoPoolLight(coordinator, entry.entry_id, key, desc)
        for key, desc in LIGHT_DESCRIPTIONS.items()
        if desc.supported_fn is None or desc.supported_fn(coordinator.data)
    )


class NeoPoolLight(NeoPoolEntity, LightEntity):
    """Representation of a NeoPool light entity."""

    entity_description: NeoPoolLightEntityDescription
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        description: NeoPoolLightEntityDescription,
    ) -> None:
        """Initialize the NeoPool light entity."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._key = key
        self._attr_unique_id = f"{self.coordinator.entry.unique_id}_{key.lower()}"

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light ON."""
        await self._async_set_state(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light OFF."""
        await self._async_set_state(False)

    async def _async_set_state(self, state: bool) -> None:
        """Drive the light relay via its timer block."""
        action = "turn_on" if state else "turn_off"
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active, ignoring %s for %s", action, self._key
            )
            return
        client = getattr(self.coordinator, "client", None)
        if client is None:  # pragma: no cover
            _LOGGER.error("Modbus client not available for writing registers")
            return

        current_mode = self.coordinator.data.get("relay_light_enable")
        if current_mode not in (
            TimerRelayMode.ALWAYS_ON,
            TimerRelayMode.ALWAYS_OFF,
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="relay_in_auto_mode",
            )

        if state:
            _LOGGER.debug(
                "Turning ON %s: function_addr=0x%04X, timer_block_addr=0x%04X",
                self._key,
                LIGHT_FUNCTION_REGISTER,
                LIGHT_TIMER_BLOCK_REGISTER,
            )
            await client.async_write_register(
                LIGHT_FUNCTION_REGISTER, _LIGHTING_FUNCTION_CODE
            )
            await client.async_write_register(
                LIGHT_TIMER_BLOCK_REGISTER, TimerRelayMode.ALWAYS_ON
            )
        else:
            _LOGGER.debug(
                "Turning OFF %s: timer_block_addr=0x%04X",
                self._key,
                LIGHT_TIMER_BLOCK_REGISTER,
            )
            await client.async_write_register(
                LIGHT_TIMER_BLOCK_REGISTER, TimerRelayMode.ALWAYS_OFF
            )
        await client.async_write_register(EXEC_REGISTER, _EXEC_COMMIT)

        # Optimistic update + schedule follow-up.
        data = self.coordinator.data
        data["relay_light_enable"] = (
            TimerRelayMode.ALWAYS_ON if state else TimerRelayMode.ALWAYS_OFF
        )
        data["Pool Light"] = state
        self.coordinator.async_set_updated_data(data)
        self.coordinator.request_refresh_with_followup()

    @property
    @override
    def is_on(self) -> bool:
        """Return True if the light is ON."""
        return bool(self.coordinator.data.get("Pool Light"))
