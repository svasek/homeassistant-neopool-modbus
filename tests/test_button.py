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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.neopool.button import NeoPoolButton, async_setup_entry
from custom_components.neopool.const import FOLLOW_UP_REFRESH_DELAY


@pytest.fixture
def mock_coordinator():
    mock = MagicMock()
    mock.data = {}
    mock.device_slug = "neopool"
    mock.winter_mode = False
    mock.client = AsyncMock()
    mock.async_request_refresh = AsyncMock()
    config_entry = MagicMock()
    config_entry.entry_id = "test_entry"
    config_entry.unique_id = "test_slug"
    mock.config_entry = config_entry
    return mock


@pytest.fixture
def button_props():
    return {}


def test_button_attrs(mock_coordinator, button_props):
    ent = NeoPoolButton(mock_coordinator, "test_entry", "SYNC_TIME", button_props)
    assert ent._key == "SYNC_TIME"


@pytest.mark.asyncio
async def test_button_press_sync_time(mock_coordinator, button_props):
    ent = NeoPoolButton(mock_coordinator, "test_entry", "SYNC_TIME", button_props)
    ent.hass = MagicMock()
    ent.hass.config = MagicMock()
    ent.hass.config.time_zone = "Europe/Prague"
    await ent.async_press()
    assert mock_coordinator.client.async_write_register.called


@pytest.mark.asyncio
async def test_button_press_escape(mock_coordinator, button_props):
    """Test async_press calls correct register writes for MBF_ESCAPE button."""
    ent = NeoPoolButton(mock_coordinator, "test_entry", "MBF_ESCAPE", button_props)
    ent.hass = MagicMock()
    await ent.async_press()
    # Should write to 0x0297, value 1
    mock_coordinator.client.async_write_register.assert_any_await(0x0297, 1)
    mock_coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_button_async_setup_entry_adds_entities(monkeypatch):
    """Test async_setup_entry adds button entities for all definitions."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"

    class DummyCoordinator:
        data = {"something": True}
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()
    # Patch BUTTON_DEFINITIONS
    from custom_components.neopool import button as btn_module

    monkeypatch.setitem(btn_module.BUTTON_DEFINITIONS, "TEST_BUTTON", {})
    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
    # Should add entity for each key in BUTTON_DEFINITIONS
    entities = async_add_entities.call_args[0][0]
    assert any(isinstance(e, NeoPoolButton) for e in entities)
    assert any(e._key == "TEST_BUTTON" for e in entities)


@pytest.mark.asyncio
async def test_button_async_setup_entry_no_data(monkeypatch, caplog):
    """Test async_setup_entry logs warning and adds no entities when no data."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"

    class DummyCoordinator:
        data = None
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    with caplog.at_level("WARNING"):
        await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]
        assert "No data from Modbus" in caplog.text
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_press_blocked_during_winter_mode(mock_coordinator, caplog):
    """async_press is ignored when winter mode is active."""
    mock_coordinator.winter_mode = True
    props = {"name": "Sync Time"}
    ent = NeoPoolButton(mock_coordinator, "test_entry", "SYNC_TIME", props)
    with caplog.at_level("WARNING"):
        await ent.async_press()
    mock_coordinator.client.async_write_register.assert_not_called()
    assert "Winter mode is active" in caplog.text


def test_available_false_during_winter_mode(mock_coordinator):
    """NeoPoolButton is unavailable when winter mode is active."""
    mock_coordinator.winter_mode = True
    props = {"name": "Sync Time"}
    ent = NeoPoolButton(mock_coordinator, "test_entry", "SYNC_TIME", props)
    assert ent.available is False


@pytest.mark.asyncio
async def test_button_press_backwash_with_valve(mock_coordinator, caplog):
    """async_press for BACKWASH writes mode 13 when filtvalve is configured."""
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_ENABLE": 1}
    mock_coordinator.device_name = "Test Pool"
    props = {"name": "Start Backwash"}
    ent = NeoPoolButton(mock_coordinator, "test_entry", "BACKWASH", props)
    ent.hass = MagicMock()
    with caplog.at_level("INFO"):
        await ent.async_press()
    mock_coordinator.client.async_write_register.assert_awaited_once_with(0x0411, 13)
    mock_coordinator.async_request_refresh.assert_awaited_once()
    mock_coordinator.request_refresh_with_followup.assert_called_once()
    assert "Backwash pre-write state:" in caplog.text


@pytest.mark.asyncio
async def test_button_press_backwash_post_write_log(mock_coordinator, caplog):
    """async_press for BACKWASH schedules a delayed diagnostic log."""
    mock_coordinator.data = {
        "MBF_PAR_FILTVALVE_ENABLE": 1,
        "MBF_PAR_FILT_MODE": 0,
        "MBF_PAR_FILTVALVE_REMAINING": 0,
    }
    mock_coordinator.device_name = "Test Pool"
    props = {"name": "Start Backwash", "icon": "mdi:waves-arrow-left"}
    ent = NeoPoolButton(mock_coordinator, "test_entry", "BACKWASH", props)
    ent.hass = MagicMock()
    with patch("custom_components.neopool.button.async_call_later") as mock_call_later:
        with caplog.at_level("INFO"):
            await ent.async_press()
            # Verify async_call_later was called with FOLLOW_UP_REFRESH_DELAY + 3
            mock_call_later.assert_called_once()
            args = mock_call_later.call_args
            assert args[0][1] == FOLLOW_UP_REFRESH_DELAY + 3.0
            # Invoke the callback to test the post-write log
            delayed_callback = args[0][2]
            mock_coordinator.data["MBF_PAR_FILT_MODE"] = 13
            mock_coordinator.data["MBF_PAR_FILTVALVE_REMAINING"] = 30
            delayed_callback(None)
    assert "Backwash post-write state" in caplog.text
    assert "MBF_PAR_FILT_MODE=13" in caplog.text


@pytest.mark.asyncio
async def test_button_press_backwash_no_valve(mock_coordinator, caplog):
    """async_press for BACKWASH logs warning and does nothing when valve not configured."""
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 0}
    mock_coordinator.device_name = "Test Pool"
    props = {"name": "Start Backwash"}
    ent = NeoPoolButton(mock_coordinator, "test_entry", "BACKWASH", props)
    ent.hass = MagicMock()
    with caplog.at_level("WARNING"):
        await ent.async_press()
    mock_coordinator.client.async_write_register.assert_not_called()
    assert "MBF_PAR_FILTVALVE_ENABLE=0" in caplog.text
    assert "MBF_PAR_FILTVALVE_GPIO=0" in caplog.text


@pytest.mark.asyncio
async def test_button_press_backwash_gpio_only(mock_coordinator, caplog):
    """async_press for BACKWASH works when only GPIO is set (ENABLE=0, GPIO!=0)."""
    mock_coordinator.data = {"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 5}
    mock_coordinator.device_name = "Test Pool"
    props = {"name": "Start Backwash"}
    ent = NeoPoolButton(mock_coordinator, "test_entry", "BACKWASH", props)
    ent.hass = MagicMock()
    with caplog.at_level("INFO"):
        await ent.async_press()
    mock_coordinator.client.async_write_register.assert_awaited_once_with(0x0411, 13)
    mock_coordinator.async_request_refresh.assert_awaited_once()
    mock_coordinator.request_refresh_with_followup.assert_called_once()
    assert "Backwash pre-write state:" in caplog.text


@pytest.mark.asyncio
async def test_button_setup_entry_creates_backwash_with_gpio_only():
    """async_setup_entry creates BACKWASH button when only GPIO is set (ENABLE=0)."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"

    class DummyCoordinator:
        data = {"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 5}
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "BACKWASH" in keys


@pytest.mark.asyncio
async def test_button_setup_entry_skips_backwash_without_valve():
    """async_setup_entry skips BACKWASH button when neither ENABLE nor GPIO is set."""

    class DummyEntry:
        unique_id = None
        entry_id = "test_entry"

    class DummyCoordinator:
        data = {"MBF_PAR_FILTVALVE_ENABLE": 0, "MBF_PAR_FILTVALVE_GPIO": 0}
        config_entry = DummyEntry()
        entry = config_entry
        device_slug = "neopool"

    hass = MagicMock()
    entry = DummyEntry()
    entry.runtime_data = DummyCoordinator()
    async_add_entities = MagicMock()

    await async_setup_entry(hass, entry, async_add_entities)  # type: ignore[arg-type]

    keys = [e._key for e in async_add_entities.call_args[0][0]]
    assert "BACKWASH" not in keys
