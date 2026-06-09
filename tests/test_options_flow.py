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

from custom_components.neopool.options_flow import NeoPoolOptionsFlowHandler


def make_flow(mock_config_entry):
    """Create a NeoPoolOptionsFlowHandler with a properly mocked config_entry."""
    # Provide sensible string defaults so slugify() (used for password derivation)
    # never receives a MagicMock. Tests can override data/title before calling.
    if not isinstance(mock_config_entry.data, dict):
        mock_config_entry.data = {"name": "Pool"}
    if not isinstance(mock_config_entry.title, str):
        mock_config_entry.title = "Pool"
    flow = NeoPoolOptionsFlowHandler()
    flow.hass = MagicMock()
    flow.hass.async_create_task = MagicMock()
    flow.hass.config_entries.async_get_known_entry.return_value = mock_config_entry
    flow.hass.config_entries.async_reload = MagicMock()
    flow.handler = "test_entry_id"
    return flow


@pytest.mark.asyncio
async def test_options_show_form():
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    flow = make_flow(mock_config_entry)
    result = await flow.async_step_init(user_input=None)
    assert result.get("type") == "form"
    schema = result.get("data_schema")
    assert "scan_interval" in str(schema)


@pytest.mark.asyncio
async def test_options_save_options():
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    flow = make_flow(mock_config_entry)
    user_input = {"enable_backwash_option": True, "measure_when_filtration_off": False}
    result = await flow.async_step_init(user_input=user_input)
    assert result.get("type") == "create_entry"
    assert result.get("data", {}) == user_input


@pytest.mark.asyncio
async def test_options_unlock_advanced_correct(monkeypatch):
    """Test entering correct unlock_advanced advances to advanced step."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    mock_config_entry.unique_id = "neopool_ABC123"
    mock_config_entry.data = {"name": "Pool"}
    flow = make_flow(mock_config_entry)

    with patch("custom_components.neopool.options_flow.dt_util") as mock_dt_util:
        mock_now = MagicMock()
        mock_now.year = 2025
        mock_dt_util.now.return_value = mock_now
        # Password is derived from slugified name, NOT from unique_id
        user_input = {"unlock_advanced": "pool2025"}
        flow.async_step_advanced = AsyncMock(return_value="advanced_step_called")
        result = await flow.async_step_init(user_input=user_input)
        assert result == "advanced_step_called"
        flow.async_step_advanced.assert_awaited_once()


@pytest.mark.asyncio
async def test_options_unlock_advanced_wrong(monkeypatch, caplog):
    """Test entering incorrect unlock_advanced shows error and logs warning."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    mock_config_entry.unique_id = "neopool_ABC123"
    mock_config_entry.data = {"name": "Pool"}
    flow = make_flow(mock_config_entry)

    with patch("custom_components.neopool.options_flow.dt_util") as mock_dt_util:
        mock_dt_util.now.return_value.year = 2025
        user_input = {"unlock_advanced": "wrongpassword"}
        result = await flow.async_step_init(user_input=user_input)
        # Should show error in form
        assert result.get("type") == "form"
        assert "unlock_advanced" in (result.get("errors") or {})
        # Should log warning
        assert "Wrong password for the advanced settings!" in caplog.text


@pytest.mark.asyncio
async def test_options_unlock_advanced_correct_slug_fallback(monkeypatch):
    """Test unlock_advanced uses slugified name for password regardless of unique_id."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    mock_config_entry.unique_id = None
    mock_config_entry.data = {"name": "My Pool"}
    flow = make_flow(mock_config_entry)

    with patch("custom_components.neopool.options_flow.dt_util") as mock_dt_util:
        mock_now = MagicMock()
        mock_now.year = 2025
        mock_dt_util.now.return_value = mock_now
        # slugify("My Pool") == "my_pool", so expected password is "my_pool2025"
        user_input = {"unlock_advanced": "my_pool2025"}
        flow.async_step_advanced = AsyncMock(return_value="advanced_step_called")
        result = await flow.async_step_init(user_input=user_input)
        assert result == "advanced_step_called"
        flow.async_step_advanced.assert_awaited_once()


@pytest.mark.asyncio
async def test_options_unlock_advanced_wrong_slug_fallback(monkeypatch, caplog):
    """Test unlock_advanced shows error when password doesn't match slugified name."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    mock_config_entry.unique_id = None
    mock_config_entry.data = {"name": "My Pool"}
    flow = make_flow(mock_config_entry)

    with patch("custom_components.neopool.options_flow.dt_util") as mock_dt_util:
        mock_dt_util.now.return_value.year = 2025
        user_input = {"unlock_advanced": "wrongpassword"}
        result = await flow.async_step_init(user_input=user_input)
        assert result.get("type") == "form"
        assert "unlock_advanced" in (result.get("errors") or {})
        assert "Wrong password for the advanced settings!" in caplog.text


@pytest.mark.asyncio
async def test_options_unlock_advanced_title_fallback(monkeypatch):
    """Test unlock_advanced falls back to config_entry.title when CONF_NAME is missing."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    mock_config_entry.unique_id = None
    mock_config_entry.data = {}  # no CONF_NAME key
    mock_config_entry.title = "My Pool"
    flow = make_flow(mock_config_entry)

    with patch("custom_components.neopool.options_flow.dt_util") as mock_dt_util:
        mock_now = MagicMock()
        mock_now.year = 2025
        mock_dt_util.now.return_value = mock_now
        # Falls back to slugify("My Pool") == "my_pool"
        user_input = {"unlock_advanced": "my_pool2025"}
        flow.async_step_advanced = AsyncMock(return_value="advanced_step_called")
        result = await flow.async_step_init(user_input=user_input)
        assert result == "advanced_step_called"
        flow.async_step_advanced.assert_awaited_once()


@pytest.mark.asyncio
async def test_options_already_enabled():
    """When backwash is already enabled, saving without password saves and triggers reload if changed."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {"enable_backwash_option": True}
    flow = make_flow(mock_config_entry)
    # Disable backwash — no password → save directly with reload
    user_input = {"enable_backwash_option": False}
    result = await flow.async_step_init(user_input=user_input)
    assert result.get("type") == "create_entry"
    assert result.get("data", {}).get("enable_backwash_option") is False
    flow.hass.async_create_task.assert_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_async_step_advanced(monkeypatch):
    """Test async_step_advanced creates entry and triggers reload if changed."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {
        "use_light": False,
        "use_aux1": False,
        "use_aux2": False,
        "use_aux3": False,
        "use_aux4": False,
    }
    flow = make_flow(mock_config_entry)
    flow._base_options = {"use_light": False}
    user_input = {"enable_backwash_option": True, "use_light": True}  # changed value
    result = await flow.async_step_advanced(user_input=user_input)
    assert result.get("type") == "create_entry"
    assert result.get("data", {})["enable_backwash_option"] is True
    # Should call reload due to use_light change
    flow.hass.async_create_task.assert_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_async_step_advanced_show_form():
    """Test async_step_advanced returns a form if user_input is None."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    flow = make_flow(mock_config_entry)
    result = await flow.async_step_advanced(user_input=None)
    assert result.get("type") == "form"
    assert result.get("step_id") == "advanced"
    assert "data_schema" in result


@pytest.mark.asyncio
async def test_options_reload_trigger(monkeypatch):
    """Test async_step_init triggers reload when any option changes."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {"use_light": False, "use_aux1": False}
    flow = make_flow(mock_config_entry)
    user_input = {"use_light": True, "use_aux1": False}
    result = await flow.async_step_init(user_input=user_input)
    assert result.get("type") == "create_entry"
    flow.hass.async_create_task.assert_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_options_reload_trigger_any_key():
    """Changing a non-use_* option like measure_when_filtration_off also triggers reload."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {"measure_when_filtration_off": False}
    flow = make_flow(mock_config_entry)
    user_input = {"measure_when_filtration_off": True}
    result = await flow.async_step_init(user_input=user_input)
    assert result.get("type") == "create_entry"
    flow.hass.async_create_task.assert_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_async_step_advanced_reload_on_backwash_toggle():
    """Toggling enable_backwash_option alone must trigger reload."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {"enable_backwash_option": False}
    flow = make_flow(mock_config_entry)
    flow._base_options = {}
    user_input = {"enable_backwash_option": True}
    result = await flow.async_step_advanced(user_input=user_input)
    assert result.get("type") == "create_entry"
    assert result.get("data", {})["enable_backwash_option"] is True
    flow.hass.async_create_task.assert_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_async_step_advanced_no_reload_when_unchanged():
    """No reload when advanced options are saved without any changes."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {"enable_backwash_option": True}
    flow = make_flow(mock_config_entry)
    flow._base_options = {}
    user_input = {"enable_backwash_option": True}
    result = await flow.async_step_advanced(user_input=user_input)
    assert result.get("type") == "create_entry"
    flow.hass.async_create_task.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_async_step_init_show_form():
    """Test async_step_init returns form if user_input is None."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    flow = make_flow(mock_config_entry)
    result = await flow.async_step_init(user_input=None)
    assert result.get("type") == "form"
    assert result.get("step_id") == "init"
    assert "data_schema" in result


@pytest.mark.asyncio
async def test_options_selector_values_coerced_to_int():
    """scan_interval and timer_resolution submitted as strings must be saved as int."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    flow = make_flow(mock_config_entry)
    user_input = {
        "scan_interval": "60",  # SelectSelector returns strings
        "timer_resolution": "15",
        "measure_when_filtration_off": False,
    }
    result = await flow.async_step_init(user_input=user_input)
    assert result.get("type") == "create_entry"
    assert result.get("data", {})["scan_interval"] == 60
    assert isinstance(result.get("data", {})["scan_interval"], int)
    assert result.get("data", {})["timer_resolution"] == 15
    assert isinstance(result.get("data", {})["timer_resolution"], int)


@pytest.mark.asyncio
async def test_options_form_contains_use_cover_sensor():
    """Options flow form schema must include use_cover_sensor toggle."""
    mock_config_entry = MagicMock()
    mock_config_entry.options = {}
    flow = make_flow(mock_config_entry)
    result = await flow.async_step_init(user_input=None)
    assert result.get("type") == "form"
    assert "use_cover_sensor" in str(result.get("data_schema"))
