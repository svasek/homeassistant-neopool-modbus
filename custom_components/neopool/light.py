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

from collections.abc import Callable, Mapping
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


@dataclass(frozen=True, kw_only=True)
class NeoPoolLightEntityDescription(LightEntityDescription):
    """Describes a NeoPool light entity."""

    switch_type: str = ""
    function_addr: int | None = None
    function_code: int | None = None
    timer_block_addr: int | None = None
    supported_fn: Callable[[dict[str, Any], Mapping[str, Any]], bool] | None = None


LIGHT_DESCRIPTIONS: dict[str, NeoPoolLightEntityDescription] = {
    "light": NeoPoolLightEntityDescription(
        key="light",
        translation_key="light",
        switch_type="relay_timer",
        timer_block_addr=LIGHT_TIMER_BLOCK_REGISTER,
        function_addr=LIGHT_FUNCTION_REGISTER,
        function_code=2,  # LIGHTING
        supported_fn=lambda data, opts: (
            bool(opts.get("use_light"))
            and (
                "MBF_PAR_LIGHTING_GPIO" not in data
                or is_valid_relay_gpio(data["MBF_PAR_LIGHTING_GPIO"] or 0)
            )
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

    async_add_entities(
        NeoPoolLight(coordinator, entry.entry_id, key, desc)
        for key, desc in LIGHT_DESCRIPTIONS.items()
        if desc.supported_fn is None
        or desc.supported_fn(coordinator.data, entry.options)
    )


class NeoPoolLight(NeoPoolEntity, LightEntity):
    """Representation of a NeoPool light entity."""

    entity_description: NeoPoolLightEntityDescription

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
        """Dispatch turn_on / turn_off to the per-type writer."""
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
        desc = self.entity_description
        if desc.switch_type == "relay_timer":
            await self._write_relay_timer(client, state)

        # Optimistic update + schedule follow-up
        self._optimistic_update(state)
        self.coordinator.async_set_updated_data(self.coordinator.data)
        self.coordinator.request_refresh_with_followup()

    async def _write_relay_timer(self, client: Any, state: bool) -> None:
        """Drive the relay light via its timer block."""
        desc = self.entity_description
        if desc.timer_block_addr is None:  # pragma: no cover
            _LOGGER.error("Missing timer_block_addr for %s", self._key)
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
            if (
                desc.function_addr is None or desc.function_code is None
            ):  # pragma: no cover
                _LOGGER.error("Missing relay_timer function config for %s", self._key)
                return
            _LOGGER.debug(
                "Turning ON %s: function_addr=0x%04X, timer_block_addr=0x%04X",
                self._key,
                desc.function_addr,
                desc.timer_block_addr,
            )
            await client.async_write_register(desc.function_addr, desc.function_code)
            await client.async_write_register(
                desc.timer_block_addr, TimerRelayMode.ALWAYS_ON
            )
        else:
            _LOGGER.debug(
                "Turning OFF %s: timer_block_addr=0x%04X",
                self._key,
                desc.timer_block_addr,
            )
            await client.async_write_register(
                desc.timer_block_addr, TimerRelayMode.ALWAYS_OFF
            )
        await client.async_write_register(EXEC_REGISTER, 1)  # Commit

    def _optimistic_update(self, state: bool) -> None:
        """Apply an optimistic state update to coordinator data."""
        desc = self.entity_description
        data = self.coordinator.data
        if desc.switch_type == "relay_timer":
            data["relay_light_enable"] = (
                TimerRelayMode.ALWAYS_ON if state else TimerRelayMode.ALWAYS_OFF
            )
            data["Pool Light"] = state

    @property
    @override
    def is_on(self) -> bool:
        """Return True if the light is ON."""
        return bool(self.coordinator.data.get("Pool Light"))

    @property
    @override
    def supported_color_modes(self) -> set[ColorMode]:
        """Return the color modes supported by this light."""
        return {ColorMode.ONOFF}

    @property
    @override
    def color_mode(self) -> ColorMode:
        """Return the current color mode of the light."""
        return ColorMode.ONOFF
