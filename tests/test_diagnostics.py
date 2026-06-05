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

from unittest.mock import MagicMock

import pytest

from custom_components.neopool.diagnostics import async_get_config_entry_diagnostics

REDACTED = "**REDACTED**"


@pytest.mark.asyncio
async def test_diagnostics_redacts_sensitive_config_data():
    entry = MagicMock()
    entry.data = {
        "host": "192.168.1.100",
        "port": 8899,
        "password": "secret",
        "token": "abcdef",
        "user": "admin",
    }
    entry.options = {"option1": True}
    entry.title = "Test Pool"
    entry.entry_id = "entry1"
    entry.unique_id = "neopool_0000000100AC00CD00120034"
    entry.version = 1

    client = MagicMock()
    client.connection_stats = {
        "retries": 3,
        "host": "192.168.1.100",
        "port": 8899,
        "unit_id": 1,
        "connected": True,
    }

    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.last_update_time = "2025-07-19 10:00:00"
    coordinator.data = {"some": "data"}
    coordinator.update_interval = 60
    coordinator.last_exception = None
    coordinator.firmware = "1.0"
    coordinator.model = "Vistapool"
    coordinator.client = client

    entry.runtime_data = coordinator
    hass = MagicMock()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    # Sensitive keys are present but redacted
    config_data = diagnostics["config_entry"]["data"]
    assert config_data["host"] == REDACTED
    assert config_data["port"] == REDACTED
    assert config_data["password"] == REDACTED
    assert config_data["token"] == REDACTED
    assert config_data["user"] == "admin"

    # connection_stats sensitive keys are also redacted
    stats = diagnostics["connection_stats"]
    assert stats["host"] == REDACTED
    assert stats["port"] == REDACTED
    assert stats["retries"] == 3
    assert stats["unit_id"] == 1

    assert diagnostics["config_entry"]["title"] == "Test Pool"
    assert (
        diagnostics["config_entry"]["unique_id"] == "neopool_0000000100AC00CD00120034"
    )
    assert diagnostics["coordinator"]["firmware"] == "1.0"
    assert diagnostics["coordinator"]["model"] == "Vistapool"


@pytest.mark.asyncio
async def test_diagnostics_no_client():
    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    entry.entry_id = "entry1"
    entry.unique_id = None
    entry.version = 1
    entry.title = "Pool"
    coordinator = MagicMock(
        spec=[
            "last_update_success",
            "last_update_time",
            "data",
            "update_interval",
            "last_exception",
            "firmware",
            "model",
            "client",
        ]
    )
    coordinator.client = None
    entry.runtime_data = coordinator
    hass = MagicMock()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["config_entry"]["entry_id"] == "entry1"
    assert "connection_stats" not in diagnostics


@pytest.mark.asyncio
async def test_diagnostics_no_duplicate_data():
    """Coordinator data must not appear twice in the output."""
    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    entry.entry_id = "entry1"
    entry.unique_id = None
    entry.version = 1
    entry.title = "Pool"
    coordinator = MagicMock()
    coordinator.data = {"key": "value"}
    coordinator.client = None
    entry.runtime_data = coordinator
    hass = MagicMock()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["coordinator"]["data"] == {"key": "value"}
    assert "last_device_data" not in diagnostics


@pytest.mark.asyncio
async def test_diagnostics_without_runtime_data():
    """Diagnostics must work when runtime_data is not set (entry not loaded)."""
    entry = MagicMock(
        spec=["data", "options", "title", "entry_id", "unique_id", "version"]
    )
    entry.data = {}
    entry.options = {}
    entry.entry_id = "entry1"
    entry.unique_id = None
    entry.version = 1
    entry.title = "Pool"
    hass = MagicMock()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["config_entry"]["entry_id"] == "entry1"
    assert diagnostics["coordinator"] == {"status": "not loaded"}
    assert "connection_stats" not in diagnostics
