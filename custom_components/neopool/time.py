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

"""Time platform for the NeoPool integration."""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import time as dt_time
import logging
from typing import Any, Literal

from neopool_modbus.decoders import seconds_to_hhmm

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NeoPoolConfigEntry
from .const import DOMAIN
from .coordinator import NeoPoolCoordinator
from .entity import NeoPoolEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

type SupportedFn = Callable[[dict[str, Any], Mapping[str, Any]], bool]


@dataclass(frozen=True, kw_only=True)
class NeoPoolTimeEntityDescription(TimeEntityDescription):
    """NeoPool time entity description."""

    timer_block: str
    timer_field: Literal["start", "stop"]
    supported_fn: SupportedFn | None = None


_DEBOUNCE_DELAY = 10.0

_TIMER_BLOCKS: tuple[tuple[str, str, bool], ...] = (
    ("filtration1", "use_filtration1", True),
    ("filtration2", "use_filtration2", True),
    ("filtration3", "use_filtration3", True),
    ("relay_aux1", "use_aux1", True),
    ("relay_aux1b", "use_aux1", False),
    ("relay_aux2", "use_aux2", True),
    ("relay_aux2b", "use_aux2", False),
    ("relay_aux3", "use_aux3", True),
    ("relay_aux3b", "use_aux3", False),
    ("relay_aux4", "use_aux4", True),
    ("relay_aux4b", "use_aux4", False),
    ("relay_light", "use_light", True),
)


def _build_descriptions() -> dict[str, NeoPoolTimeEntityDescription]:
    """Build the timer start/stop descriptions."""
    out: dict[str, NeoPoolTimeEntityDescription] = {}
    for block, opt_flag, enabled_default in _TIMER_BLOCKS:
        for field in ("start", "stop"):
            key = f"{block}_{field}"
            out[key] = NeoPoolTimeEntityDescription(
                key=key,
                entity_category=EntityCategory.CONFIG,
                entity_registry_enabled_default=enabled_default,
                timer_block=block,
                timer_field=field,
                supported_fn=lambda data, opts, _flag=opt_flag: bool(opts.get(_flag)),
            )
    return out


TIME_DESCRIPTIONS: dict[str, NeoPoolTimeEntityDescription] = _build_descriptions()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NeoPoolConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NeoPool time entities from a config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        NeoPoolTime(coordinator, entry.entry_id, key, desc)
        for key, desc in TIME_DESCRIPTIONS.items()
        if desc.supported_fn is None
        or desc.supported_fn(coordinator.data, entry.options)
    )


class NeoPoolTime(NeoPoolEntity, TimeEntity):
    """NeoPool timer start/stop time entity."""

    entity_description: NeoPoolTimeEntityDescription

    def __init__(
        self,
        coordinator: NeoPoolCoordinator,
        entry_id: str,
        key: str,
        description: NeoPoolTimeEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, entry_id)
        self.entity_description = description
        self._key = key
        device_id = self.coordinator.entry.unique_id or self._entry_id
        self._attr_unique_id = f"{device_id}_{key.lower()}"
        self._attr_translation_key = NeoPoolEntity.slugify(key)

        self._pending_write_task: asyncio.Task[None] | None = None
        self._debounce_delay = _DEBOUNCE_DELAY

    @property
    def native_value(self) -> dt_time | None:
        """Decode seconds-since-midnight into HH:MM:SS."""
        seconds = self.coordinator.data.get(self._key)
        if seconds is None:
            return None
        try:
            seconds = int(seconds) % 86400
        except (TypeError, ValueError):  # pragma: no cover
            return None
        return dt_time(
            hour=seconds // 3600,
            minute=(seconds % 3600) // 60,
            second=seconds % 60,
        )

    async def async_set_value(self, value: dt_time) -> None:
        """Apply optimistically, then debounce-write to the device."""
        if self.coordinator.winter_mode:
            _LOGGER.warning(
                "Winter mode is active - ignoring set_value for %s", self._key
            )
            return
        seconds = value.hour * 3600 + value.minute * 60 + value.second
        self.coordinator.data[self._key] = seconds
        self.coordinator.async_set_updated_data(self.coordinator.data)

        if self._pending_write_task is not None and not self._pending_write_task.done():
            self._pending_write_task.cancel()
        self._pending_write_task = asyncio.create_task(self._debounced_write())

    async def _debounced_write(self) -> None:
        """Push the value to the device after a quiet period."""
        try:
            await asyncio.sleep(self._debounce_delay)
        except asyncio.CancelledError:  # pragma: no cover
            return
        if self.coordinator.winter_mode:  # pragma: no cover
            _LOGGER.warning(
                "Winter mode is active - debounced write cancelled for %s",
                self._key,
            )
            return
        desc = self.entity_description
        block = desc.timer_block
        data = self.coordinator.data
        start = seconds_to_hhmm(int(data.get(f"{block}_start", 0)))
        stop = seconds_to_hhmm(int(data.get(f"{block}_stop", 0)))
        await self.hass.services.async_call(
            DOMAIN,
            "set_timer",
            {
                "entry_id": self._entry_id,
                "timer": block,
                "start": start,
                "stop": stop,
            },
        )
