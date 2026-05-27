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
from homeassistant.exceptions import ServiceValidationError

from custom_components.vistapool import (
    _cleanup_removed_entities,
    _register_services,
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.vistapool.const import DEFAULT_PORT


@pytest.mark.asyncio
async def test_async_handle_set_timer_happy(monkeypatch):
    """Test async_handle_set_timer sets timer correctly with all parameters."""

    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    coordinator = MagicMock()
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
    coordinator.client.write_timer = AsyncMock(return_value=True)
    coordinator.async_request_refresh = AsyncMock()
    coordinator.request_refresh_with_followup = MagicMock()

    # Prepare call mock
    call = MagicMock()
    call.data = {
        "timer": "filtration1",
        "start": "08:30",
        "stop": "10:15",
        "enable": 1,
        "entry_id": "entry1",
        "period": 1234,
    }

    # Register service and extract handler
    hass.services.has_service = MagicMock(return_value=False)
    _register_services(hass)
    service_func = next(
        c.args[2]
        for c in hass.services.async_register.call_args_list
        if c.args[1] == "set_timer"
    )

    await service_func(call)

    # Check correct timer data sent to write_timer
    coordinator.client.write_timer.assert_awaited_once_with(
        "filtration1",
        {"on": 30600, "interval": 6300, "period": 1234, "enable": 1},
    )
    coordinator.async_request_refresh.assert_not_awaited()
    coordinator.request_refresh_with_followup.assert_called_once()


@pytest.mark.asyncio
async def test_async_handle_set_timer_entry_id_fallback(monkeypatch):
    """Test async_handle_set_timer uses fallback entry_id if not provided."""

    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "fallback"
    coordinator = MagicMock()
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
    coordinator.client.write_timer = AsyncMock(return_value=True)
    coordinator.async_request_refresh = AsyncMock()
    coordinator.request_refresh_with_followup = MagicMock()

    call = MagicMock()
    call.data = {
        "timer": "relay_aux1",
        "start": "00:00",
        "stop": "01:00",
        "enable": 0,
        # "entry_id" intentionally missing!
    }

    hass.services.has_service = MagicMock(return_value=False)
    _register_services(hass)
    service_func = next(
        c.args[2]
        for c in hass.services.async_register.call_args_list
        if c.args[1] == "set_timer"
    )
    await service_func(call)

    coordinator.client.write_timer.assert_awaited_once_with(
        "relay_aux1",
        {"on": 0, "interval": 3600, "enable": 0},
    )


@pytest.mark.asyncio
async def test_async_handle_set_timer_missing_entry(monkeypatch):
    """Test async_handle_set_timer raises ServiceValidationError if no entry_id found."""

    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    call = MagicMock()
    call.data = {
        "timer": "relay_aux2",
        "start": "12:00",
        "stop": "13:00",
        # no entry_id, and no fallback available
    }

    hass.services.has_service = MagicMock(return_value=False)
    _register_services(hass)
    service_func = next(
        c.args[2]
        for c in hass.services.async_register.call_args_list
        if c.args[1] == "set_timer"
    )
    with pytest.raises(ServiceValidationError):
        await service_func(call)


@pytest.mark.asyncio
async def test_async_handle_set_timer_write_timer_exception(monkeypatch):
    """Test async_handle_set_timer raises ServiceValidationError on write_timer exception."""

    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entryX"
    coordinator = MagicMock()
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])
    coordinator.client.write_timer = AsyncMock(side_effect=Exception("fail!"))
    coordinator.async_request_refresh = AsyncMock()
    coordinator.request_refresh_with_followup = MagicMock()

    call = MagicMock()
    call.data = {
        "timer": "relay_aux2",
        "start": "14:00",
        "stop": "14:30",
        "entry_id": "entryX",
    }

    hass.services.has_service = MagicMock(return_value=False)
    _register_services(hass)
    service_func = next(
        c.args[2]
        for c in hass.services.async_register.call_args_list
        if c.args[1] == "set_timer"
    )
    with pytest.raises(ServiceValidationError):
        await service_func(call)


@pytest.mark.asyncio
async def test_async_handle_set_timer_invalid_timer_name(monkeypatch):
    """Test async_handle_set_timer rejects invalid timer names."""

    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    call = MagicMock()
    call.data = {
        "timer": "nonexistent_timer",
        "start": "08:00",
        "stop": "09:00",
        "entry_id": "entry1",
    }

    hass.services.has_service = MagicMock(return_value=False)
    _register_services(hass)
    service_func = next(
        c.args[2]
        for c in hass.services.async_register.call_args_list
        if c.args[1] == "set_timer"
    )
    with pytest.raises(ServiceValidationError, match="Invalid timer name"):
        await service_func(call)


@pytest.mark.asyncio
async def test_async_handle_set_timer_missing_timer_key(monkeypatch):
    """Test async_handle_set_timer raises ServiceValidationError when 'timer' key is missing."""

    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    call = MagicMock()
    call.data = {"start": "08:00", "stop": "09:00", "entry_id": "entry1"}

    hass.services.has_service = MagicMock(return_value=False)
    _register_services(hass)
    service_func = next(
        c.args[2]
        for c in hass.services.async_register.call_args_list
        if c.args[1] == "set_timer"
    )
    with pytest.raises(ServiceValidationError, match="Missing required parameter"):
        await service_func(call)


@pytest.mark.asyncio
async def test_async_setup_entry_success():
    """Test async_setup_entry completes successfully."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    config_entry = MagicMock()
    with patch("custom_components.vistapool.VistaPoolModbusClient"):
        with patch(
            "custom_components.vistapool.VistaPoolCoordinator"
        ) as mock_coordinator:
            mock_coord_instance = mock_coordinator.return_value
            mock_coord_instance.async_config_entry_first_refresh = AsyncMock(
                return_value=None
            )
            with patch("custom_components.vistapool.er.async_get") as mock_er_get:
                mock_registry = MagicMock()
                mock_er_get.return_value = mock_registry
                with patch(
                    "custom_components.vistapool.er.async_entries_for_config_entry",
                    return_value=[],
                ):
                    result = await async_setup_entry(hass, config_entry)
                    assert result is True


@pytest.mark.asyncio
async def test_async_unload_entry_success():
    """Test async_unload_entry completes successfully."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    coordinator = MagicMock()
    coordinator.client = AsyncMock()
    config_entry.runtime_data = coordinator
    # Simulate another entry still loaded — services should NOT be removed
    other_entry = MagicMock()
    other_entry.entry_id = "entry2"
    hass.config_entries.async_entries = MagicMock(
        return_value=[config_entry, other_entry]
    )
    hass.services.has_service = MagicMock(return_value=True)
    hass.services.async_remove = MagicMock()
    result = await async_unload_entry(hass, config_entry)
    assert result is True
    # Check that follow-up refresh was cancelled and client closed
    coordinator.cancel_follow_up_refresh.assert_called_once()
    assert coordinator.client.close.await_count == 1
    # Services should NOT be removed (other entry still loaded)
    hass.services.async_remove.assert_not_called()


@pytest.mark.asyncio
async def test_async_unload_entry_last_entry():
    """Test async_unload_entry removes services when last entry is unloaded."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    coordinator = MagicMock()
    coordinator.client = AsyncMock()
    config_entry.runtime_data = coordinator
    # Only this entry — after unload, no remaining entries
    hass.config_entries.async_entries = MagicMock(return_value=[config_entry])
    hass.services.has_service = MagicMock(return_value=True)
    hass.services.async_remove = MagicMock()
    result = await async_unload_entry(hass, config_entry)
    assert result is True
    # Services should be removed (last entry)
    assert hass.services.async_remove.call_count == 2


@pytest.mark.asyncio
async def test_async_unload_entry_no_client():
    """Test async_unload_entry when coordinator has no client."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    config_entry = MagicMock()
    config_entry.entry_id = "entry2"
    coordinator = MagicMock()
    coordinator.client = None
    config_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[config_entry])
    hass.services.has_service = MagicMock(return_value=True)
    hass.services.async_remove = MagicMock()
    result = await async_unload_entry(hass, config_entry)
    assert result is True


@pytest.mark.asyncio
async def test_register_services():
    """Test _register_services registers set_timer and write_register services."""
    hass = MagicMock()
    hass.services.async_register = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    _register_services(hass)
    assert hass.services.async_register.call_count == 2
    registered = {c.args[1] for c in hass.services.async_register.call_args_list}
    assert "set_timer" in registered
    assert "write_register" in registered


@pytest.mark.asyncio
async def test_register_services_partial():
    """Test _register_services only registers missing services."""
    hass = MagicMock()
    hass.services.async_register = MagicMock()
    # set_timer exists, write_register does not
    hass.services.has_service = MagicMock(
        side_effect=lambda domain, name: name == "set_timer"
    )
    _register_services(hass)
    assert hass.services.async_register.call_count == 1
    assert hass.services.async_register.call_args.args[1] == "write_register"


def _get_write_register_handler(hass):
    """Helper: register services and return the write_register handler."""
    hass.services.has_service = MagicMock(return_value=False)
    _register_services(hass)
    return next(
        c.args[2]
        for c in hass.services.async_register.call_args_list
        if c.args[1] == "write_register"
    )


@pytest.mark.asyncio
async def test_write_register_decimal():
    """Test write_register with decimal address and value."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.client.async_write_register = AsyncMock(
        return_value={"value": 5, "confirmed": 5}
    )
    coordinator.request_refresh_with_followup = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "1539", "value": "5", "entry_id": "entry1"}
    await handler(call)
    coordinator.client.async_write_register.assert_awaited_once_with(
        1539, 5, apply=True
    )


@pytest.mark.asyncio
async def test_write_register_hex():
    """Test write_register with hex address and value."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.client.async_write_register = AsyncMock(
        return_value={"value": 0, "confirmed": 0}
    )
    coordinator.request_refresh_with_followup = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "0x0604", "value": "0x0000", "entry_id": "entry1"}
    await handler(call)
    coordinator.client.async_write_register.assert_awaited_once_with(
        0x0604, 0, apply=True
    )


@pytest.mark.asyncio
async def test_write_register_int_passthrough():
    """Test write_register when YAML passes native int values."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.client.async_write_register = AsyncMock(
        return_value={"value": 2, "confirmed": 2}
    )
    coordinator.request_refresh_with_followup = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": 1074, "value": 2, "entry_id": "entry1"}
    await handler(call)
    coordinator.client.async_write_register.assert_awaited_once_with(
        1074, 2, apply=True
    )


@pytest.mark.asyncio
async def test_write_register_invalid_hex():
    """Test write_register raises on invalid hex string."""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "0xZZZZ", "value": "5", "entry_id": "entry1"}
    with pytest.raises(ServiceValidationError, match="Invalid address"):
        await handler(call)


@pytest.mark.asyncio
async def test_write_register_out_of_range():
    """Test write_register raises when value > 65535."""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "0x0001", "value": "70000", "entry_id": "entry1"}
    with pytest.raises(ServiceValidationError, match="out of range"):
        await handler(call)


@pytest.mark.asyncio
async def test_write_register_apply_false():
    """Test write_register passes apply=False when specified."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.client.async_write_register = AsyncMock(
        return_value={"value": 5, "confirmed": 5}
    )
    coordinator.request_refresh_with_followup = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {
        "address": "0x0603",
        "value": "5",
        "apply": False,
        "entry_id": "entry1",
    }
    await handler(call)
    coordinator.client.async_write_register.assert_awaited_once_with(
        0x0603, 5, apply=False
    )


@pytest.mark.asyncio
async def test_write_register_apply_invalid_type():
    """Test write_register raises when apply is not a boolean."""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {
        "address": "0x0001",
        "value": "1",
        "apply": "false",
        "entry_id": "entry1",
    }
    with pytest.raises(ServiceValidationError, match="Invalid apply"):
        await handler(call)


@pytest.mark.asyncio
async def test_write_register_rejects_bool():
    """Test write_register raises when address or value is a boolean."""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": True, "value": "5", "entry_id": "entry1"}
    with pytest.raises(ServiceValidationError, match="Invalid address"):
        await handler(call)


@pytest.mark.asyncio
async def test_write_register_rejects_float():
    """Test write_register raises when address or value is a float."""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": 1.5, "value": "5", "entry_id": "entry1"}
    with pytest.raises(ServiceValidationError, match="not a float"):
        await handler(call)


@pytest.mark.asyncio
async def test_write_register_missing_param():
    """Test write_register raises when required parameter is missing."""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "0x0001", "entry_id": "entry1"}
    with pytest.raises(ServiceValidationError, match="Missing required parameter"):
        await handler(call)


@pytest.mark.asyncio
async def test_write_register_returns_none():
    """Test write_register raises when async_write_register returns None."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.client.async_write_register = AsyncMock(return_value=None)
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "0x0001", "value": "1", "entry_id": "entry1"}
    with pytest.raises(ServiceValidationError, match="failed"):
        await handler(call)


@pytest.mark.asyncio
async def test_write_register_verification_mismatch():
    """Test write_register raises when read-back value differs from written value."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.client.async_write_register = AsyncMock(
        return_value={"value": 1, "confirmed": 99}
    )
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "0x0001", "value": "1", "entry_id": "entry1"}
    with pytest.raises(ServiceValidationError, match="Write verification failed"):
        await handler(call)


@pytest.mark.asyncio
async def test_write_register_generic_exception():
    """Test write_register wraps unexpected exceptions in ServiceValidationError."""
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.client.async_write_register = AsyncMock(
        side_effect=RuntimeError("connection lost")
    )
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = coordinator
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "0x0001", "value": "1", "entry_id": "entry1"}
    with pytest.raises(ServiceValidationError, match="Register write failed"):
        await handler(call)


@pytest.mark.asyncio
async def test_get_coordinator_not_found():
    """Test _get_coordinator raises when entry_id has no coordinator."""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "0x0001", "value": "1", "entry_id": "nonexistent"}
    with pytest.raises(ServiceValidationError, match="No entry_id found"):
        await handler(call)


@pytest.mark.asyncio
async def test_get_coordinator_runtime_data_none():
    """Test _get_coordinator raises when runtime_data is None."""
    hass = MagicMock()
    mock_entry = MagicMock()
    mock_entry.entry_id = "entry1"
    mock_entry.runtime_data = None
    hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    handler = _get_write_register_handler(hass)
    call = MagicMock()
    call.data = {"address": "0x0001", "value": "1", "entry_id": "entry1"}
    with pytest.raises(ServiceValidationError, match="No VistaPool coordinator"):
        await handler(call)


@pytest.mark.asyncio
async def test_async_setup_entry_registers_services():
    """Test async_setup_entry calls _register_services when no services exist."""
    hass = MagicMock()

    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {
        "host": "1.2.3.4",
        "port": 502,
        "name": "Pool",
        "slave_id": 1,
    }
    entry.options = {}

    with (
        patch("custom_components.vistapool.VistaPoolModbusClient"),
        patch("custom_components.vistapool.VistaPoolCoordinator") as mock_coord_cls,
        patch("custom_components.vistapool._cleanup_removed_entities"),
    ):
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock()
        mock_coord_cls.return_value = mock_coord

        result = await async_setup_entry(hass, entry)

    assert result is True
    # Verify services were registered (has_service returned False)
    assert hass.services.async_register.call_count == 2


def test_cleanup_removes_orphaned_entities():
    """Test _cleanup_removed_entities removes entities matching REMOVED_ENTITY_KEYS."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    orphan = MagicMock()
    orphan.unique_id = "test_entry_hidro on target"
    orphan.entity_id = "binary_sensor.hydrolysis_on_target"

    valid = MagicMock()
    valid.unique_id = "test_entry_hidro low flow"
    valid.entity_id = "binary_sensor.hydrolysis_low_flow"

    mock_registry = MagicMock()

    with patch("custom_components.vistapool.er.async_get", return_value=mock_registry):
        with patch(
            "custom_components.vistapool.er.async_entries_for_config_entry",
            return_value=[orphan, valid],
        ):
            _cleanup_removed_entities(hass, entry)

    mock_registry.async_remove.assert_called_once_with(
        "binary_sensor.hydrolysis_on_target"
    )


def test_cleanup_removes_ph_pump_entities():
    """Test _cleanup_removed_entities matches lowercase pH pump unique_ids."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    # unique_ids are built with key.lower() — REMOVED_ENTITY_KEYS must be lowercase
    ph_acid = MagicMock()
    ph_acid.unique_id = "test_entry_ph acid pump active"
    ph_acid.entity_id = "binary_sensor.vistapool_ph_acid_pump_active"

    ph_base = MagicMock()
    ph_base.unique_id = "test_entry_ph pump active"
    ph_base.entity_id = "binary_sensor.vistapool_ph_pump_active"

    unrelated = MagicMock()
    unrelated.unique_id = "test_entry_ph control module"
    unrelated.entity_id = "binary_sensor.vistapool_ph_control_module"

    mock_registry = MagicMock()

    with patch("custom_components.vistapool.er.async_get", return_value=mock_registry):
        with patch(
            "custom_components.vistapool.er.async_entries_for_config_entry",
            return_value=[ph_acid, ph_base, unrelated],
        ):
            _cleanup_removed_entities(hass, entry)

    assert mock_registry.async_remove.call_count == 2
    removed_ids = [c.args[0] for c in mock_registry.async_remove.call_args_list]
    assert "binary_sensor.vistapool_ph_acid_pump_active" in removed_ids
    assert "binary_sensor.vistapool_ph_pump_active" in removed_ids


def test_cleanup_no_orphans():
    """Test _cleanup_removed_entities does nothing when no orphans exist."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    valid = MagicMock()
    valid.unique_id = "test_entry_hidro low flow"
    valid.entity_id = "binary_sensor.hydrolysis_low_flow"

    mock_registry = MagicMock()

    with patch("custom_components.vistapool.er.async_get", return_value=mock_registry):
        with patch(
            "custom_components.vistapool.er.async_entries_for_config_entry",
            return_value=[valid],
        ):
            _cleanup_removed_entities(hass, entry)

    mock_registry.async_remove.assert_not_called()


def test_cleanup_removes_orphans_with_serial_unique_id():
    """Test _cleanup_removed_entities matches new unique_id-prefixed entities (v2+)."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "old_entry_id"
    entry.unique_id = "neopool_0000000100AC00CD00120034"

    # Orphan with new unique_id prefix (post-migration)
    orphan_new = MagicMock()
    orphan_new.unique_id = "neopool_0000000100AC00CD00120034_hidro on target"
    orphan_new.entity_id = "binary_sensor.hydrolysis_on_target"

    # Orphan with old entry_id prefix (pre-migration leftover)
    orphan_old = MagicMock()
    orphan_old.unique_id = "old_entry_id_hidro on target"
    orphan_old.entity_id = "binary_sensor.hydrolysis_on_target_old"

    valid = MagicMock()
    valid.unique_id = "neopool_0000000100AC00CD00120034_hidro low flow"
    valid.entity_id = "binary_sensor.hydrolysis_low_flow"

    mock_registry = MagicMock()

    with patch("custom_components.vistapool.er.async_get", return_value=mock_registry):
        with patch(
            "custom_components.vistapool.er.async_entries_for_config_entry",
            return_value=[orphan_new, orphan_old, valid],
        ):
            _cleanup_removed_entities(hass, entry)

    assert mock_registry.async_remove.call_count == 2
    removed_ids = [c.args[0] for c in mock_registry.async_remove.call_args_list]
    assert "binary_sensor.hydrolysis_on_target" in removed_ids
    assert "binary_sensor.hydrolysis_on_target_old" in removed_ids


# --- Migration tests ---

DEFAULT_SERIAL_REGS = [0x0000, 0x0001, 0x00AC, 0x00CD, 0x0012, 0x0034]
DEFAULT_SERIAL_STRING = "".join(f"{r:04X}" for r in DEFAULT_SERIAL_REGS)


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_to_v2_success():
    """Test migration from v1 (no unique_id) to v2 (serial-based unique_id)."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_123"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    hass.config_entries.async_entries.return_value = []

    mock_entity1 = MagicMock()
    mock_entity1.unique_id = "old_entry_id_123_mbf_ph_measure"
    mock_entity1.entity_id = "sensor.pool_ph"

    mock_entity2 = MagicMock()
    mock_entity2.unique_id = "old_entry_id_123_mbf_temperature"
    mock_entity2.entity_id = "sensor.pool_temperature"

    mock_entity_registry = MagicMock()
    mock_entity_registry.async_update_entity = MagicMock()

    mock_old_device = MagicMock()
    mock_old_device.id = "old_device_id"
    mock_device_registry = MagicMock()
    mock_device_registry.async_get_device.return_value = mock_old_device

    expected_unique_id = f"neopool_{DEFAULT_SERIAL_STRING}"

    with (
        patch(
            "custom_components.vistapool.migration.async_get_device_serial",
            new=AsyncMock(return_value=DEFAULT_SERIAL_STRING),
        ),
        patch(
            "custom_components.vistapool.migration.er.async_get",
            return_value=mock_entity_registry,
        ),
        patch(
            "custom_components.vistapool.migration.er.async_entries_for_config_entry",
            return_value=[mock_entity1, mock_entity2],
        ),
        patch(
            "custom_components.vistapool.migration.dr.async_get",
            return_value=mock_device_registry,
        ),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_called_once_with(
        config_entry, unique_id=expected_unique_id, version=2
    )
    assert mock_entity_registry.async_update_entity.call_count == 2
    mock_entity_registry.async_update_entity.assert_any_call(
        "sensor.pool_ph",
        new_unique_id=f"{expected_unique_id}_mbf_ph_measure",
    )
    mock_entity_registry.async_update_entity.assert_any_call(
        "sensor.pool_temperature",
        new_unique_id=f"{expected_unique_id}_mbf_temperature",
    )
    # Old device with entry_id identifier should be updated to serial-based
    mock_device_registry.async_get_device.assert_called_once_with(
        identifiers={("vistapool", "old_entry_id_123")}
    )
    mock_device_registry.async_update_device.assert_called_once_with(
        "old_device_id",
        new_identifiers={("vistapool", expected_unique_id)},
    )


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_to_v2_serial_unavailable():
    """Test migration defers when serial cannot be read (retries on next restart)."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_456"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    with patch(
        "custom_components.vistapool.migration.async_get_device_serial",
        new=AsyncMock(return_value=None),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    # Version must NOT be bumped — migration will retry on next HA restart
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_to_v2_duplicate_detected():
    """Test migration fails when another entry already has the same serial."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "entry_aaa"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    existing_entry = MagicMock()
    existing_entry.entry_id = "entry_bbb"
    existing_entry.unique_id = f"neopool_{DEFAULT_SERIAL_STRING}"
    hass.config_entries.async_entries.return_value = [existing_entry]

    with patch(
        "custom_components.vistapool.migration.async_get_device_serial",
        new=AsyncMock(return_value=DEFAULT_SERIAL_STRING),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is False
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_async_migrate_entry_entity_update_error():
    """Test migration rolls back and defers when entity update fails."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_789"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    hass.config_entries.async_entries.return_value = []

    # First entity will succeed, second will fail → first must be rolled back
    mock_entity1 = MagicMock()
    mock_entity1.unique_id = "old_entry_id_789_mbf_ph_measure"
    mock_entity1.entity_id = "sensor.pool_ph"

    mock_entity2 = MagicMock()
    mock_entity2.unique_id = "old_entry_id_789_mbf_temperature"
    mock_entity2.entity_id = "sensor.pool_temperature"

    call_count = 0

    def update_side_effect(entity_id, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call (entity1 migration) succeeds
        # Second call (entity2 migration) fails
        # Third call (entity1 rollback) succeeds
        if call_count == 2:
            raise ValueError("registry conflict")

    mock_registry = MagicMock()
    mock_registry.async_update_entity.side_effect = update_side_effect

    with (
        patch(
            "custom_components.vistapool.migration.async_get_device_serial",
            new=AsyncMock(return_value=DEFAULT_SERIAL_STRING),
        ),
        patch(
            "custom_components.vistapool.migration.er.async_get",
            return_value=mock_registry,
        ),
        patch(
            "custom_components.vistapool.migration.er.async_entries_for_config_entry",
            return_value=[mock_entity1, mock_entity2],
        ),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    # 3 calls: migrate entity1 (ok), migrate entity2 (fail), rollback entity1
    assert mock_registry.async_update_entity.call_count == 3
    # Verify rollback call restored entity1's original unique_id
    mock_registry.async_update_entity.assert_any_call(
        "sensor.pool_ph",
        new_unique_id="old_entry_id_789_mbf_ph_measure",
    )
    # Version must NOT be bumped — migration will retry on next HA restart
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_async_migrate_entry_rollback_also_fails():
    """Test migration returns False when rollback fails to prevent duplicates."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_789"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    hass.config_entries.async_entries.return_value = []

    mock_entity1 = MagicMock()
    mock_entity1.unique_id = "old_entry_id_789_mbf_ph_measure"
    mock_entity1.entity_id = "sensor.pool_ph"

    mock_entity2 = MagicMock()
    mock_entity2.unique_id = "old_entry_id_789_mbf_temperature"
    mock_entity2.entity_id = "sensor.pool_temperature"

    call_count = 0

    def update_side_effect(entity_id, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            # entity2 migration fails, then entity1 rollback also fails
            raise ValueError("registry conflict")

    mock_registry = MagicMock()
    mock_registry.async_update_entity.side_effect = update_side_effect

    with (
        patch(
            "custom_components.vistapool.migration.async_get_device_serial",
            new=AsyncMock(return_value=DEFAULT_SERIAL_STRING),
        ),
        patch(
            "custom_components.vistapool.migration.er.async_get",
            return_value=mock_registry,
        ),
        patch(
            "custom_components.vistapool.migration.er.async_entries_for_config_entry",
            return_value=[mock_entity1, mock_entity2],
        ),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is False
    # 3 calls: migrate entity1 (ok), migrate entity2 (fail), rollback entity1 (fail)
    assert mock_registry.async_update_entity.call_count == 3
    hass.config_entries.async_update_entry.assert_not_called()
