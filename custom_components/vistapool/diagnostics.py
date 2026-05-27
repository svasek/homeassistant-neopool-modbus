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

"""VistaPool Integration for Home Assistant - Diagnostics Module"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import VistaPoolConfigEntry

TO_REDACT = {"password", "token", "host", "port"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VistaPoolConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a VistaPool config entry."""

    diagnostics: dict[str, Any] = {}

    diagnostics["config_entry"] = {
        "data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "title": entry.title,
        "entry_id": entry.entry_id,
        "unique_id": entry.unique_id,
        "version": entry.version,
    }

    # Coordinator state (contains data, errors, etc.)
    coordinator = entry.runtime_data

    diagnostics["coordinator"] = {
        "last_update_success": getattr(coordinator, "last_update_success", None),
        "last_update_time": str(getattr(coordinator, "last_update_time", None)),
        "data": getattr(coordinator, "data", {}),
        "update_interval": str(getattr(coordinator, "update_interval", None)),
        "last_exception": str(getattr(coordinator, "last_exception", "")),
        "firmware": getattr(coordinator, "firmware", None),
        "model": getattr(coordinator, "model", None),
    }

    # Additional client details
    client = getattr(coordinator, "client", None)
    if client and hasattr(client, "connection_stats"):
        diagnostics["connection_stats"] = async_redact_data(
            dict(client.connection_stats), TO_REDACT
        )

    return diagnostics
