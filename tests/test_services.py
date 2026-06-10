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

"""Tests for the dedicated services module.

These exercise `_async_set_timer`, `_async_write_register`, the
`_get_coordinator` resolver, and the `async_setup_services` registration
helper directly — without going through the full `async_setup_entry`
service-registration path (which is covered separately in test_init.py).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from neopool_modbus.exceptions import NeoPoolError

from custom_components.neopool.services import (
    SERVICE_SET_TIMER,
    SERVICE_WRITE_REGISTER,
    _async_set_timer,
    _async_write_register,
    _get_coordinator,
    async_setup_services,
)


def _make_call(data: dict, hass: MagicMock | None = None) -> MagicMock:
    """Build a ServiceCall mock with a `.hass` and `.data` attribute."""
    call = MagicMock()
    call.hass = hass or MagicMock()
    call.data = data
    return call


def _make_loaded_entry(entry_id: str = "entry1") -> MagicMock:
    """Build a config-entry mock whose state is LOADED with a coordinator."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.state = ConfigEntryState.LOADED
    coordinator = MagicMock()
    coordinator.client.write_timer = AsyncMock(return_value=True)
    coordinator.client.async_write_register = AsyncMock()
    coordinator.request_refresh_with_followup = MagicMock()
    entry.runtime_data = coordinator
    return entry


# ---------------------------------------------------------------------------
# _get_coordinator
# ---------------------------------------------------------------------------


def test_get_coordinator_explicit_entry_id():
    """Explicit entry_id resolves to the matching loaded entry's coordinator."""
    entry = _make_loaded_entry("e1")
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"entry_id": "e1"}, hass)
    coord = _get_coordinator(hass, call)
    assert coord is entry.runtime_data


def test_get_coordinator_fallback_first_loaded():
    """Without entry_id, the first LOADED entry's coordinator is returned."""
    not_loaded = MagicMock()
    not_loaded.state = ConfigEntryState.NOT_LOADED
    loaded = _make_loaded_entry("e2")
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[not_loaded, loaded])
    call = _make_call({}, hass)
    assert _get_coordinator(hass, call) is loaded.runtime_data


def test_get_coordinator_unknown_entry_id():
    """Unknown entry_id surfaces an entry_not_found ServiceValidationError."""
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    with pytest.raises(ServiceValidationError) as exc:
        _get_coordinator(hass, _make_call({"entry_id": "missing"}, hass))
    assert exc.value.translation_key == "entry_not_found"


def test_get_coordinator_explicit_entry_id_not_loaded():
    """Explicit entry_id pointing at a NOT_LOADED entry is rejected.

    Routing a service call to an entry whose runtime_data is stale or
    missing would surface confusing AttributeError downstream — the
    resolver must require the matching entry to be LOADED.
    """
    not_loaded = MagicMock()
    not_loaded.entry_id = "e1"
    not_loaded.state = ConfigEntryState.NOT_LOADED
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[not_loaded])
    with pytest.raises(ServiceValidationError) as exc:
        _get_coordinator(hass, _make_call({"entry_id": "e1"}, hass))
    assert exc.value.translation_key == "entry_not_found"


def test_get_coordinator_no_loaded_entries():
    """No loaded entries surfaces a no_loaded_entry ServiceValidationError."""
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    with pytest.raises(ServiceValidationError) as exc:
        _get_coordinator(hass, _make_call({}, hass))
    assert exc.value.translation_key == "no_loaded_entry"


def test_get_coordinator_runtime_data_none():
    """Loaded entry without a coordinator surfaces no_coordinator error."""
    entry = MagicMock()
    entry.state = ConfigEntryState.LOADED
    entry.entry_id = "e3"
    entry.runtime_data = None
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    with pytest.raises(ServiceValidationError) as exc:
        _get_coordinator(hass, _make_call({}, hass))
    assert exc.value.translation_key == "no_coordinator"


# ---------------------------------------------------------------------------
# _async_set_timer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_timer_happy_path():
    """All timer parameters are converted and forwarded to write_timer."""
    entry = _make_loaded_entry("e1")
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call(
        {
            "entry_id": "e1",
            "timer": "filtration1",
            "start": "08:30",
            "stop": "10:15",
            "period": 1234,
            "enable": 1,
        },
        hass,
    )
    await _async_set_timer(call)
    entry.runtime_data.client.write_timer.assert_awaited_once_with(
        "filtration1",
        {"on": 30600, "interval": 6300, "period": 1234, "enable": 1},
    )
    entry.runtime_data.request_refresh_with_followup.assert_called_once()


@pytest.mark.asyncio
async def test_set_timer_invalid_timer_name():
    """Unknown timer name raises a translatable invalid_timer error."""
    entry = _make_loaded_entry()
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"timer": "not_a_timer"}, hass)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_set_timer(call)
    assert exc.value.translation_key == "invalid_timer"


@pytest.mark.asyncio
async def test_set_timer_write_failure_translates_to_validation_error():
    """A NeoPoolError from write_timer becomes a translatable timer_failed error."""
    entry = _make_loaded_entry()
    entry.runtime_data.client.write_timer = AsyncMock(side_effect=NeoPoolError("boom"))
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"timer": "filtration1"}, hass)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_set_timer(call)
    assert exc.value.translation_key == "timer_failed"


# ---------------------------------------------------------------------------
# _async_write_register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_register_decimal_and_hex_parsing():
    """Decimal and hex string addresses both parse via parse_register_int."""
    entry = _make_loaded_entry()
    entry.runtime_data.client.async_write_register = AsyncMock(
        return_value={"value": 42, "confirmed": 42}
    )
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    # Decimal address
    await _async_write_register(
        _make_call({"address": "1539", "value": "42", "apply": True}, hass)
    )
    entry.runtime_data.client.async_write_register.assert_awaited_with(
        1539, 42, apply=True
    )
    # Hex address
    await _async_write_register(
        _make_call({"address": "0x0603", "value": "42", "apply": True}, hass)
    )
    entry.runtime_data.client.async_write_register.assert_awaited_with(
        0x0603, 42, apply=True
    )


@pytest.mark.asyncio
async def test_write_register_apply_false_passes_through():
    """The apply=False flag is forwarded to async_write_register."""
    entry = _make_loaded_entry()
    entry.runtime_data.client.async_write_register = AsyncMock(
        return_value={"value": 1, "confirmed": 1}
    )
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    await _async_write_register(
        _make_call({"address": "0x0001", "value": "1", "apply": False}, hass)
    )
    entry.runtime_data.client.async_write_register.assert_awaited_with(
        1, 1, apply=False
    )


@pytest.mark.asyncio
async def test_write_register_returns_none_raises_write_failed():
    """A None response from async_write_register surfaces write_failed."""
    entry = _make_loaded_entry()
    entry.runtime_data.client.async_write_register = AsyncMock(return_value=None)
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"address": "1", "value": "1", "apply": True}, hass)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_write_register(call)
    assert exc.value.translation_key == "write_failed"


@pytest.mark.asyncio
async def test_write_register_verification_mismatch():
    """Confirmed != value surfaces a write_verification_failed error."""
    entry = _make_loaded_entry()
    entry.runtime_data.client.async_write_register = AsyncMock(
        return_value={"value": 0, "confirmed": 0}
    )
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"address": "1", "value": "1", "apply": True}, hass)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_write_register(call)
    assert exc.value.translation_key == "write_verification_failed"


@pytest.mark.asyncio
async def test_write_register_modbus_failure_translates_to_validation_error():
    """A NeoPoolError from the client becomes a register_write_failed error."""
    entry = _make_loaded_entry()
    entry.runtime_data.client.async_write_register = AsyncMock(
        side_effect=NeoPoolError("offline")
    )
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"address": "1", "value": "1", "apply": True}, hass)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_write_register(call)
    assert exc.value.translation_key == "register_write_failed"


# ---------------------------------------------------------------------------
# parse_register_int paths exercised through write_register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_register_rejects_bool_address():
    """Bool addresses (True/False) are rejected with invalid_register_type."""
    entry = _make_loaded_entry()
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"address": True, "value": "1", "apply": True}, hass)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_write_register(call)
    assert exc.value.translation_key == "invalid_register_type"


@pytest.mark.asyncio
async def test_write_register_rejects_float_address():
    """Float addresses are rejected with invalid_register_float."""
    entry = _make_loaded_entry()
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"address": 1.5, "value": "1", "apply": True}, hass)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_write_register(call)
    assert exc.value.translation_key == "invalid_register_float"


@pytest.mark.asyncio
async def test_write_register_invalid_hex_string():
    """Unparsable strings raise invalid_register_type with chained cause."""
    entry = _make_loaded_entry()
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"address": "0xZZZZ", "value": "1", "apply": True}, hass)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_write_register(call)
    assert exc.value.translation_key == "invalid_register_type"


@pytest.mark.asyncio
async def test_write_register_out_of_range():
    """Values above 65535 are rejected with invalid_register_range."""
    entry = _make_loaded_entry()
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    call = _make_call({"address": "70000", "value": "1", "apply": True}, hass)
    with pytest.raises(ServiceValidationError) as exc:
        await _async_write_register(call)
    assert exc.value.translation_key == "register_out_of_range"


# ---------------------------------------------------------------------------
# async_setup_services
# ---------------------------------------------------------------------------


def test_setup_services_registers_both_services():
    """Both set_timer and write_register are registered when neither exists."""
    hass = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()
    async_setup_services(hass)
    registered = [c.args[1] for c in hass.services.async_register.call_args_list]
    assert SERVICE_SET_TIMER in registered
    assert SERVICE_WRITE_REGISTER in registered


def test_setup_services_is_idempotent():
    """Already-registered services are not re-registered (idempotent guard)."""
    hass = MagicMock()
    hass.services.has_service = MagicMock(return_value=True)
    hass.services.async_register = MagicMock()
    async_setup_services(hass)
    hass.services.async_register.assert_not_called()
