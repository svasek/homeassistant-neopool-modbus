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

from custom_components.vistapool import config_flow
from custom_components.vistapool.const import (
    DEFAULT_MODBUS_FRAMER,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SLAVE_ID,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_show_user_form_on_init():
    flow = config_flow.VistaPoolConfigFlow()
    result = await flow.async_step_user(user_input=None)
    assert result is not None
    assert result["type"] == "form"
    assert "errors" in result
    # Check if the form schema contains host, port, slave_id, name and modbus_framer
    schema = result["data_schema"]
    assert "host" in str(schema)
    assert "port" in str(schema)
    assert "slave_id" in str(schema)
    assert "name" in str(schema)
    assert "modbus_framer" in str(schema)


@pytest.mark.asyncio
async def test_create_entry_success():
    flow = config_flow.VistaPoolConfigFlow()
    user_input = {
        "host": "192.168.1.100",
        "port": DEFAULT_PORT,
        "slave_id": 1,
        "name": "Test Pool",
    }
    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=True),
    ):
        result = await flow.async_step_user(user_input)
        assert result is not None
        assert result["type"] == "create_entry"
        assert result["title"] == "Test Pool"
        assert result["data"]["host"] == "192.168.1.100"
        assert result["data"]["port"] == DEFAULT_PORT


@pytest.mark.asyncio
async def test_create_entry_with_rtu_framer():
    """Test that modbus_framer='rtu' is accepted and stored in config entry."""
    flow = config_flow.VistaPoolConfigFlow()
    user_input = {
        "host": "192.168.1.100",
        "port": DEFAULT_PORT,
        "slave_id": 1,
        "name": "Test Pool RTU",
        "modbus_framer": "rtu",
    }
    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=True),
    ):
        result = await flow.async_step_user(user_input)
        assert result is not None
        assert result["type"] == "create_entry"
        assert result["data"]["modbus_framer"] == "rtu"


@pytest.mark.asyncio
async def test_create_entry_failure():
    flow = config_flow.VistaPoolConfigFlow()
    user_input = {
        "host": "192.168.1.100",
        "port": DEFAULT_PORT,
        "slave_id": 1,
        "name": "Test Pool",
    }
    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=False),
    ):
        result = await flow.async_step_user(user_input)
        assert result is not None
        assert result["type"] == "form"
        assert "host" in result["errors"]
        assert result["errors"]["host"] == "cannot_connect"


def test_async_get_options_flow(monkeypatch):
    class DummyConfigEntry:
        pass

    class DummyOptionsFlow:
        """Mirrors the new OptionsFlow API: no config_entry injected via __init__."""

        def __init__(self):
            self.called = True

    # Patch import ve funkci
    monkeypatch.setattr(
        "custom_components.vistapool.options_flow.VistaPoolOptionsFlowHandler",
        DummyOptionsFlow,
    )
    config_entry = DummyConfigEntry()
    handler = config_flow.VistaPoolConfigFlow.async_get_options_flow(config_entry)  # type: ignore[arg-type]
    assert isinstance(handler, DummyOptionsFlow)
    assert handler.called is True


@pytest.mark.asyncio
async def test_reconfigure_shows_form_with_current_data():
    """Reconfigure form is shown with pre-filled values from the existing entry."""
    flow = config_flow.VistaPoolConfigFlow()

    existing_data = {
        "host": "10.0.0.1",
        "port": 502,
        "slave_id": 2,
        "modbus_framer": "rtu",
        "name": "MyPool",
        "scan_interval": 30,
    }
    mock_entry = MagicMock()
    mock_entry.data = existing_data

    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry.return_value = mock_entry
    flow.context = {"entry_id": "abc123"}

    result = await flow.async_step_reconfigure(user_input=None)
    assert result is not None

    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"
    assert not result.get("errors")

    # Extract defaults from the voluptuous schema and verify they match existing_data
    schema_defaults = {
        key.schema: key.default() if callable(key.default) else key.default
        for key in result["data_schema"].schema
        if hasattr(key, "default")
    }
    assert schema_defaults["host"] == existing_data["host"]
    assert schema_defaults["port"] == existing_data["port"]
    assert schema_defaults["slave_id"] == existing_data["slave_id"]
    assert schema_defaults["modbus_framer"] == existing_data["modbus_framer"]


@pytest.mark.asyncio
async def test_reconfigure_success():
    """Successful reconfiguration merges new values and calls update_reload_and_abort."""
    flow = config_flow.VistaPoolConfigFlow()

    existing_data = {
        "host": "10.0.0.1",
        "port": 502,
        "slave_id": 1,
        "modbus_framer": "tcp",
        "name": "MyPool",
        "scan_interval": 30,
    }
    mock_entry = MagicMock()
    mock_entry.data = existing_data

    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry.return_value = mock_entry
    flow.context = {"entry_id": "abc123"}
    flow.async_update_reload_and_abort = MagicMock(
        return_value={"type": "abort", "reason": "reconfigure_successful"}
    )

    user_input = {
        "host": "10.0.0.99",
        "port": 503,
        "slave_id": 2,
        "modbus_framer": "rtu",
    }

    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=True),
    ):
        result = await flow.async_step_reconfigure(user_input)
        assert result is not None

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"

    call_kwargs = flow.async_update_reload_and_abort.call_args
    saved_data = call_kwargs[1]["data"]
    # New values overwrite old ones
    assert saved_data["host"] == "10.0.0.99"
    assert saved_data["port"] == 503
    assert saved_data["slave_id"] == 2
    assert saved_data["modbus_framer"] == "rtu"
    # Unchanged values from original entry are preserved
    assert saved_data["name"] == "MyPool"
    assert saved_data["scan_interval"] == 30


@pytest.mark.asyncio
async def test_reconfigure_cannot_connect():
    """Reconfigure shows cannot_connect error when host is unreachable."""
    flow = config_flow.VistaPoolConfigFlow()

    mock_entry = MagicMock()
    mock_entry.data = {
        "host": "10.0.0.1",
        "port": 502,
        "slave_id": 1,
        "modbus_framer": "tcp",
    }

    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry.return_value = mock_entry
    flow.context = {"entry_id": "abc123"}

    user_input = {
        "host": "10.0.0.99",
        "port": 502,
        "slave_id": 1,
        "modbus_framer": "tcp",
    }

    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=False),
    ):
        result = await flow.async_step_reconfigure(user_input)
        assert result is not None

    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"
    assert result["errors"].get("host") == "cannot_connect"


@pytest.mark.asyncio
async def test_reconfigure_entry_not_found_aborts():
    """When the entry cannot be found, the flow aborts gracefully."""
    flow = config_flow.VistaPoolConfigFlow()

    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry.return_value = None
    flow.context = {"entry_id": "missing"}
    flow.async_abort = MagicMock(
        return_value={"type": "abort", "reason": "entry_not_found"}
    )

    result = await flow.async_step_reconfigure(user_input=None)
    assert result is not None

    assert result["type"] == "abort"
    assert result["reason"] == "entry_not_found"


@pytest.mark.asyncio
async def test_is_host_port_open_exception():
    # Monkeypatch asyncio.open_connection to raise
    async def raise_exc(*args, **kwargs):
        raise OSError("fail")

    monkeypatch = patch("asyncio.open_connection", raise_exc)
    with monkeypatch:
        result = await config_flow.is_host_port_open("127.0.0.1", 9999)
        assert result is False


@pytest.mark.asyncio
async def test_is_host_port_open_success(monkeypatch):
    reader = MagicMock()
    writer = MagicMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    async def fake_open_connection(host, port):
        return reader, writer

    monkeypatch.setattr("asyncio.open_connection", fake_open_connection)
    result = await config_flow.is_host_port_open("127.0.0.1", DEFAULT_PORT)
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()
    assert result is True


@pytest.mark.asyncio
async def test_create_entry_scan_interval_coerced_to_int():
    """scan_interval submitted as string (from SelectSelector) must be saved as int."""
    flow = config_flow.VistaPoolConfigFlow()
    user_input = {
        "host": "192.168.1.100",
        "port": DEFAULT_PORT,
        "slave_id": 1,
        "name": "Test Pool",
        "scan_interval": "30",  # SelectSelector returns strings
    }
    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=True),
    ):
        result = await flow.async_step_user(user_input)
        assert result is not None
    assert result["type"] == "create_entry"
    assert result["data"]["scan_interval"] == 30
    assert isinstance(result["data"]["scan_interval"], int)


@pytest.mark.asyncio
async def test_user_form_contains_use_cover_sensor():
    """Config flow form schema must include use_cover_sensor toggle."""
    flow = config_flow.VistaPoolConfigFlow()
    result = await flow.async_step_user(user_input=None)
    assert result is not None
    assert result["type"] == "form"
    assert "use_cover_sensor" in str(result["data_schema"])


# ---------------------------------------------------------------------------
# _async_get_default_name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_default_name_returns_translated_name():
    """When translation contains name_default the translated name is returned."""
    flow = config_flow.VistaPoolConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.language = "cs"
    key = f"component.{DOMAIN}.config.step.user.data.name_default"
    with patch(
        "custom_components.vistapool.config_flow.ha_translation.async_get_translations",
        new=AsyncMock(return_value={key: "Bazén"}),
    ):
        name = await flow._async_get_default_name()
    assert name == "Bazén"


@pytest.mark.asyncio
async def test_get_default_name_falls_back_when_key_missing():
    """When translation dict does not contain name_default, DEFAULT_NAME is returned."""
    flow = config_flow.VistaPoolConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.language = "en"
    with patch(
        "custom_components.vistapool.config_flow.ha_translation.async_get_translations",
        new=AsyncMock(return_value={}),
    ):
        name = await flow._async_get_default_name()
    assert name == DEFAULT_NAME


@pytest.mark.asyncio
async def test_get_default_name_falls_back_without_hass():
    """When hass is not set (AttributeError), DEFAULT_NAME is returned."""
    flow = config_flow.VistaPoolConfigFlow()
    name = await flow._async_get_default_name()
    assert name == DEFAULT_NAME


@pytest.mark.asyncio
async def test_get_default_name_falls_back_on_translation_error():
    """When async_get_translations raises, DEFAULT_NAME is returned."""
    flow = config_flow.VistaPoolConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.language = "en"
    with patch(
        "custom_components.vistapool.config_flow.ha_translation.async_get_translations",
        new=AsyncMock(side_effect=RuntimeError("fail")),
    ):
        name = await flow._async_get_default_name()
    assert name == DEFAULT_NAME


# ---------------------------------------------------------------------------
# async_step_user – name fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_entry_empty_name_uses_default():
    """Empty string for name falls back to the default name."""
    flow = config_flow.VistaPoolConfigFlow()
    user_input = {
        "host": "192.168.1.100",
        "port": DEFAULT_PORT,
        "slave_id": 1,
        "name": "",  # empty → should fall back
    }
    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=True),
    ):
        result = await flow.async_step_user(user_input)
        assert result is not None

    assert result["type"] == "create_entry"
    assert result["title"] == DEFAULT_NAME
    assert result["data"]["name"] == DEFAULT_NAME


@pytest.mark.asyncio
async def test_create_entry_no_name_key_uses_default():
    """Missing name key in user_input falls back to the default name."""
    flow = config_flow.VistaPoolConfigFlow()
    user_input = {
        "host": "192.168.1.100",
        "port": DEFAULT_PORT,
        "slave_id": 1,
        # no "name" key
    }
    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=True),
    ):
        result = await flow.async_step_user(user_input)
        assert result is not None

    assert result["type"] == "create_entry"
    assert result["title"] == DEFAULT_NAME
    assert result["data"]["name"] == DEFAULT_NAME


# ---------------------------------------------------------------------------
# async_step_user – form schema defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_form_schema_boolean_defaults():
    """Schema defaults: use_filtration1=True, others False."""
    flow = config_flow.VistaPoolConfigFlow()
    result = await flow.async_step_user(user_input=None)
    assert result is not None
    schema = result["data_schema"]

    bool_defaults = {
        key.schema: key.default() if callable(key.default) else key.default
        for key in schema.schema
        if hasattr(key, "default")
        and key.schema
        in (
            "use_filtration1",
            "use_filtration2",
            "use_filtration3",
            "use_light",
            "use_cover_sensor",
        )
    }

    assert bool_defaults["use_filtration1"] is True
    assert bool_defaults["use_filtration2"] is False
    assert bool_defaults["use_filtration3"] is False
    assert bool_defaults["use_light"] is False
    assert bool_defaults["use_cover_sensor"] is False


@pytest.mark.asyncio
async def test_user_form_schema_connection_defaults():
    """Schema defaults for port, slave_id and modbus_framer match constants."""
    flow = config_flow.VistaPoolConfigFlow()
    result = await flow.async_step_user(user_input=None)
    assert result is not None
    schema = result["data_schema"]

    defaults = {
        key.schema: key.default() if callable(key.default) else key.default
        for key in schema.schema
        if hasattr(key, "default")
        and key.schema in ("port", "slave_id", "modbus_framer")
    }

    assert defaults["port"] == DEFAULT_PORT
    assert defaults["slave_id"] == DEFAULT_SLAVE_ID
    assert defaults["modbus_framer"] == DEFAULT_MODBUS_FRAMER


# ---------------------------------------------------------------------------
# async_step_user – optional flags stored correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_entry_stores_use_light_flag():
    """use_light=True is persisted in the config entry data."""
    flow = config_flow.VistaPoolConfigFlow()
    user_input = {
        "host": "192.168.1.100",
        "port": DEFAULT_PORT,
        "slave_id": 1,
        "name": "Test Pool",
        "use_light": True,
    }
    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=True),
    ):
        result = await flow.async_step_user(user_input)
        assert result is not None

    assert result["type"] == "create_entry"
    assert result["data"]["use_light"] is True


@pytest.mark.asyncio
async def test_create_entry_stores_filtration_flags():
    """Non-default filtration flags are persisted correctly."""
    flow = config_flow.VistaPoolConfigFlow()
    user_input = {
        "host": "192.168.1.100",
        "port": DEFAULT_PORT,
        "slave_id": 1,
        "name": "Test Pool",
        "use_filtration1": False,
        "use_filtration2": True,
        "use_filtration3": True,
    }
    with patch(
        "custom_components.vistapool.config_flow.is_host_port_open",
        new=AsyncMock(return_value=True),
    ):
        result = await flow.async_step_user(user_input)
        assert result is not None

    assert result["type"] == "create_entry"
    assert result["data"]["use_filtration1"] is False
    assert result["data"]["use_filtration2"] is True
    assert result["data"]["use_filtration3"] is True


# ---------------------------------------------------------------------------
# async_step_reconfigure – missing optional keys fall back to constants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconfigure_schema_defaults_to_constants_when_keys_absent():
    """When entry data lacks optional keys the schema defaults to module constants."""
    flow = config_flow.VistaPoolConfigFlow()

    # Entry with only the host stored (no port / slave_id / modbus_framer)
    mock_entry = MagicMock()
    mock_entry.data = {"host": "10.0.0.1", "name": "MyPool"}

    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry.return_value = mock_entry
    flow.context = {"entry_id": "abc123"}

    result = await flow.async_step_reconfigure(user_input=None)
    assert result is not None
    assert result["type"] == "form"

    schema_defaults = {
        key.schema: key.default() if callable(key.default) else key.default
        for key in result["data_schema"].schema
        if hasattr(key, "default")
    }

    assert schema_defaults["port"] == DEFAULT_PORT
    assert schema_defaults["slave_id"] == DEFAULT_SLAVE_ID
    assert schema_defaults["modbus_framer"] == DEFAULT_MODBUS_FRAMER
