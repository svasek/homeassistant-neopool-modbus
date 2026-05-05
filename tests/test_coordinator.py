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
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.vistapool.const import FOLLOW_UP_REFRESH_DELAY
from custom_components.vistapool.coordinator import VistaPoolCoordinator


@pytest.fixture
def mock_entry():
    entry = MagicMock()
    entry.options = {}
    entry.data = {"name": "Test Pool"}
    entry.entry_id = "entry_id_123"
    entry.unique_id = "test_slug"
    return entry


@pytest.mark.asyncio
async def test_async_update_data_success(mock_entry):
    client = AsyncMock()
    # Simulate async_read_all returns base dict
    client.async_read_all = AsyncMock(return_value={"MBF_POWER_MODULE_VERSION": 0x1234})
    client.read_all_timers = AsyncMock(return_value={})
    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    data = await coordinator._async_update_data()
    assert "MBF_POWER_MODULE_VERSION" in data
    assert coordinator.firmware == "18.52"  # 0x1234 == 18.52
    assert coordinator.model == "VistaPool"


@pytest.mark.asyncio
async def test_async_update_data_raises_UpdateFailed_on_subsequent_error(mock_entry):
    """When cached data exists, a Modbus error raises UpdateFailed (not a silent cache return)."""
    client = AsyncMock()
    client.async_read_all = AsyncMock(side_effect=Exception("Modbus fail"))
    client.read_all_timers = AsyncMock()
    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    coordinator.data = {"cached": "value"}
    with patch("custom_components.vistapool.coordinator._LOGGER"):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_async_update_data_raises_ConfigEntryNotReady_on_first_error(mock_entry):
    client = AsyncMock()
    client.async_read_all = AsyncMock(side_effect=Exception("fail"))
    client.read_all_timers = AsyncMock()
    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    # data is None (never received) → ConfigEntryNotReady
    with pytest.raises(ConfigEntryNotReady):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_async_update_data_raises_UpdateFailed_when_data_is_empty_dict(
    mock_entry,
):
    """An empty dict ({}) is treated as 'data was received' — subsequent errors raise UpdateFailed."""
    client = AsyncMock()
    client.async_read_all = AsyncMock(side_effect=Exception("fail"))
    client.read_all_timers = AsyncMock()
    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    # Simulate a previous successful read that yielded an empty payload
    coordinator.data = {}
    with patch("custom_components.vistapool.coordinator._LOGGER"):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_async_update_data_time_sync(mock_entry):
    # auto_time_sync must be enabled, device time must be out of sync
    entry = MagicMock()
    entry.options = {"auto_time_sync": True}
    entry.data = {"name": "Test Pool"}
    entry.entry_id = "entry_id_321"
    entry.unique_id = "test_slug"
    client = AsyncMock()
    client.async_read_all = AsyncMock(return_value={"MBF_POWER_MODULE_VERSION": 0x2345})
    client.read_all_timers = AsyncMock(return_value={})
    client.async_write_register = AsyncMock()
    hass = MagicMock()
    with (
        patch(
            "custom_components.vistapool.coordinator.is_device_time_out_of_sync",
            return_value=True,
        ),
        patch(
            "custom_components.vistapool.coordinator.prepare_device_time",
            return_value=1234,
        ),
    ):
        coordinator = VistaPoolCoordinator(hass, client, entry, entry.entry_id)
        await coordinator._async_update_data()
    assert client.async_write_register.await_count == 2


@pytest.mark.asyncio
async def test_set_auto_time_sync(mock_entry):
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    coordinator = VistaPoolCoordinator(
        hass, MagicMock(), mock_entry, mock_entry.entry_id
    )
    await coordinator.set_auto_time_sync(True)
    assert coordinator.auto_time_sync is True
    hass.config_entries.async_update_entry.assert_called_once()


def test_firmware_and_model_property(mock_entry):
    coordinator = VistaPoolCoordinator(
        MagicMock(), MagicMock(), mock_entry, mock_entry.entry_id
    )
    coordinator._firmware = "1.2"
    coordinator._model = "X"
    assert coordinator.firmware == "1.2"
    assert coordinator.model == "X"
    coordinator.device_name = "Pool"
    assert coordinator.device_name == "Pool"


@pytest.mark.asyncio
async def test_async_update_data_timer_processing(mock_entry):
    # Prepare a fake timer block with different value combinations
    client = AsyncMock()
    client.async_read_all = AsyncMock(
        return_value={
            "MBF_POWER_MODULE_VERSION": 0x1234,
            "Filtration Pump": True,
        }
    )
    # Simulate two timers: one with both 'on' and 'interval', another with 'on' missing
    client.read_all_timers = AsyncMock(
        return_value={
            "filtration1": {
                "enable": True,
                "on": 1000,  # e.g. 1000 seconds since midnight
                "interval": 3600,  # 1 hour
                "period": 2,
                "countdown": 1200,
            },
            "filtration2": {
                "enable": False,
                "on": None,
                "interval": 1800,  # 30 minutes
                "period": 1,
                "countdown": 0,
            },
        }
    )
    # Set options so at least one timer will be enabled
    entry = MagicMock()
    entry.options = {"use_filtration1": True, "use_filtration2": True}
    entry.data = {"name": "Test Pool"}
    entry.entry_id = "test_entry_id"
    entry.unique_id = "test_slug"

    coordinator = VistaPoolCoordinator(MagicMock(), client, entry, entry.entry_id)
    data = await coordinator._async_update_data()

    # Filtration timer blocks are always read regardless of use_filtration* options
    call_args = client.read_all_timers.call_args
    timers_requested = (
        call_args.kwargs.get("enabled_timers")
        if "enabled_timers" in call_args.kwargs
        else call_args.args[0]
        if call_args.args
        else None
    )
    for ft in ("filtration1", "filtration2", "filtration3"):
        assert ft in timers_requested, (
            f"{ft} must always be read for countdown aggregation"
        )

    # force_read must include filtration timers when filtration is active
    force_read = call_args[1].get("force_read")
    assert force_read is not None, "force_read must be set when filtration is running"
    for ft in ("filtration1", "filtration2", "filtration3"):
        assert ft in force_read, f"{ft} must bypass timer cache while filtration runs"

    # Check that timer data keys are present and correctly computed
    assert data["filtration1_enable"] is True
    assert data["filtration1_start"] == 1000
    assert data["filtration1_interval"] == 3600
    assert data["filtration1_period"] == 2
    assert data["filtration1_countdown"] == 1200
    # stop = (1000 + 3600) % 86400 = 4600
    assert data["filtration1_stop"] == 4600

    assert data["filtration2_enable"] is False
    assert data["filtration2_start"] is None
    assert data["filtration2_interval"] == 1800
    assert data["filtration2_period"] == 1
    assert data["filtration2_countdown"] == 0
    assert data["filtration2_stop"] is None

    # Aggregated filtration remaining: max of non-zero countdowns (1200)
    assert data["FILTRATION_REMAINING"] == 1200


@pytest.mark.asyncio
async def test_setpoint_sync_on_mismatch(mock_entry):
    client = AsyncMock()
    # Return differing setpoints to trigger sync
    client.async_read_all = AsyncMock(
        return_value={
            "MBF_POWER_MODULE_VERSION": 0x1234,
            "MBF_PAR_HEATING_TEMP": 28,
            "MBF_PAR_INTELLIGENT_TEMP": 26,
        }
    )
    client.read_all_timers = AsyncMock(return_value={})
    client.async_write_register = AsyncMock()
    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    # Seed previous snapshot so only HEATING changed this cycle
    coordinator.data = {
        "MBF_PAR_HEATING_TEMP": 27,
        "MBF_PAR_INTELLIGENT_TEMP": 26,
    }
    data = await coordinator._async_update_data()
    # Coordinator should sync only the unaffected register (INTELLIGENT) to the new HEATING value
    assert client.async_write_register.await_count == 1
    call_args = client.async_write_register.await_args_list[0]
    # Address and value
    assert call_args[0][0] == 0x041C  # INTELLIGENT_SETPOINT_REGISTER
    assert call_args[0][1] == 28
    # apply should be True for the syncing write
    assert call_args[1].get("apply", False) is True
    # Returned data should reflect synced values
    assert data["MBF_PAR_HEATING_TEMP"] == 28
    assert data["MBF_PAR_INTELLIGENT_TEMP"] == 28


@pytest.mark.asyncio
async def test_setpoint_sync_on_mismatch_intel_changed(mock_entry):
    client = AsyncMock()
    # Return differing setpoints to trigger sync
    client.async_read_all = AsyncMock(
        return_value={
            "MBF_POWER_MODULE_VERSION": 0x1234,
            "MBF_PAR_HEATING_TEMP": 26,
            "MBF_PAR_INTELLIGENT_TEMP": 28,
        }
    )
    client.read_all_timers = AsyncMock(return_value={})
    client.async_write_register = AsyncMock()
    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    # Seed previous snapshot so only INTELLIGENT changed this cycle
    coordinator.data = {
        "MBF_PAR_HEATING_TEMP": 26,
        "MBF_PAR_INTELLIGENT_TEMP": 27,
    }
    data = await coordinator._async_update_data()
    # Coordinator should sync only the unaffected register (HEATING) to the new INTELLIGENT value
    assert client.async_write_register.await_count == 1
    call_args = client.async_write_register.await_args_list[0]
    assert call_args[0][0] == 0x0416  # HEATING_SETPOINT_REGISTER
    assert call_args[0][1] == 28
    assert call_args[1].get("apply", False) is True
    assert data["MBF_PAR_HEATING_TEMP"] == 28
    assert data["MBF_PAR_INTELLIGENT_TEMP"] == 28


@pytest.mark.asyncio
async def test_setpoint_sync_both_changed_conflict(mock_entry):
    client = AsyncMock()
    # Both changed to different values in this cycle
    client.async_read_all = AsyncMock(
        return_value={
            "MBF_POWER_MODULE_VERSION": 0x1234,
            "MBF_PAR_HEATING_TEMP": 28,
            "MBF_PAR_INTELLIGENT_TEMP": 26,
        }
    )
    client.read_all_timers = AsyncMock(return_value={})
    client.async_write_register = AsyncMock()
    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    # Previous snapshot with identical values so that both appear changed now
    coordinator.data = {
        "MBF_PAR_HEATING_TEMP": 27,
        "MBF_PAR_INTELLIGENT_TEMP": 27,
    }
    data = await coordinator._async_update_data()
    # Both changed simultaneously → revert both to previous values
    # Expect 2 writes: one for heating (apply=False), one for intelligent (apply=True)
    assert client.async_write_register.await_count == 2
    # First write: revert heating to 27 (apply=False)
    client.async_write_register.assert_any_await(0x0416, 27, apply=False)
    # Second write: revert intelligent to 27 (apply=True)
    client.async_write_register.assert_any_await(0x041C, 27, apply=True)
    # Data should be reverted to previous values
    assert data["MBF_PAR_HEATING_TEMP"] == 27
    assert data["MBF_PAR_INTELLIGENT_TEMP"] == 27


@pytest.mark.asyncio
async def test_setpoint_sync_both_equal_no_conflict(mock_entry):
    client = AsyncMock()
    # Both setpoints are equal, so no conflict even if both changed
    client.async_read_all = AsyncMock(
        return_value={
            "MBF_POWER_MODULE_VERSION": 0x1234,
            "MBF_PAR_HEATING_TEMP": 29,
            "MBF_PAR_INTELLIGENT_TEMP": 29,
        }
    )
    client.read_all_timers = AsyncMock(return_value={})
    client.async_write_register = AsyncMock()
    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    # Previous snapshot with different identical values
    coordinator.data = {
        "MBF_PAR_HEATING_TEMP": 27,
        "MBF_PAR_INTELLIGENT_TEMP": 27,
    }
    data = await coordinator._async_update_data()
    # Both are equal → no conflict, no write needed
    assert client.async_write_register.await_count == 0
    # Data should remain as read (both equal)
    assert data["MBF_PAR_HEATING_TEMP"] == 29
    assert data["MBF_PAR_INTELLIGENT_TEMP"] == 29


@pytest.mark.asyncio
async def test_setpoint_sync_initial_mismatch(mock_entry):
    client = AsyncMock()
    # Setpoints differ but neither changed (initial state or manual device change)
    client.async_read_all = AsyncMock(
        return_value={
            "MBF_POWER_MODULE_VERSION": 0x1234,
            "MBF_PAR_HEATING_TEMP": 25,
            "MBF_PAR_INTELLIGENT_TEMP": 1,
        }
    )
    client.read_all_timers = AsyncMock(return_value={})
    client.async_write_register = AsyncMock()
    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    # Previous snapshot with same values (neither changed)
    coordinator.data = {
        "MBF_PAR_HEATING_TEMP": 25,
        "MBF_PAR_INTELLIGENT_TEMP": 1,
    }
    data = await coordinator._async_update_data()
    # Initial sync: intelligent should be set to match heating
    assert client.async_write_register.await_count == 1
    client.async_write_register.assert_awaited_once_with(0x041C, 25, apply=True)
    # Data should reflect the sync
    assert data["MBF_PAR_HEATING_TEMP"] == 25
    assert data["MBF_PAR_INTELLIGENT_TEMP"] == 25


@pytest.mark.asyncio
async def test_dev_overrides_applied_valid_json(mock_entry):
    # Enable overrides with valid JSON string
    entry = MagicMock()
    entry.options = {
        "dev_overrides_enabled": True,
        "dev_overrides": '{"MBF_PAR_CLIMA_ONOFF": 1, "MBF_PAR_MODEL": 1}',
    }
    entry.data = {"name": "Test Pool"}
    entry.entry_id = "entry_id_dev1"
    entry.unique_id = "test_slug"

    client = AsyncMock()
    client.async_read_all = AsyncMock(
        return_value={
            "MBF_POWER_MODULE_VERSION": 0x1234,
            "MBF_PAR_CLIMA_ONOFF": 0,
        }
    )
    client.read_all_timers = AsyncMock(return_value={})

    coordinator = VistaPoolCoordinator(MagicMock(), client, entry, entry.entry_id)
    data = await coordinator._async_update_data()

    # Overrides should be applied over the base read values
    assert data["MBF_PAR_CLIMA_ONOFF"] == 1
    assert data["MBF_PAR_MODEL"] == 1


@pytest.mark.asyncio
async def test_dev_overrides_invalid_json_ignored(mock_entry):
    entry = MagicMock()
    entry.options = {
        "dev_overrides_enabled": True,
        "dev_overrides": "this-is-not-json",
    }
    entry.data = {"name": "Test Pool"}
    entry.entry_id = "entry_id_dev2"
    entry.unique_id = "test_slug"

    client = AsyncMock()
    client.async_read_all = AsyncMock(return_value={"X": 1})
    client.read_all_timers = AsyncMock(return_value={})

    with patch("custom_components.vistapool.coordinator._LOGGER") as mock_logger:
        coordinator = VistaPoolCoordinator(MagicMock(), client, entry, entry.entry_id)
        data = await coordinator._async_update_data()
        # Should log a warning about failed overrides but not raise
        assert mock_logger.warning.called

    # Data remains as originally read (no overrides applied)
    assert data.get("X") == 1
    assert "MBF_PAR_CLIMA_ONOFF" not in data
    assert "MBF_PAR_MODEL" not in data


# ---------------------------------------------------------------------------
# Winter mode tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_winter_mode_returns_empty_dict_when_no_cached_data(mock_entry):
    """Winter mode with no data and no saved capabilities returns {} without calling Modbus."""
    mock_entry.options = {"winter_mode": True}

    client = AsyncMock()
    client.async_read_all = AsyncMock()
    client.read_all_timers = AsyncMock()

    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    coordinator.data = None

    with patch("custom_components.vistapool.coordinator._LOGGER") as mock_logger:
        data = await coordinator._async_update_data()

    client.async_read_all.assert_not_called()
    assert data == {}
    assert mock_logger.debug.called


@pytest.mark.asyncio
async def test_winter_mode_returns_frozen_cached_data(mock_entry):
    """Winter mode with existing cached data returns that data unchanged."""
    mock_entry.options = {"winter_mode": True}

    client = AsyncMock()
    client.async_read_all = AsyncMock()
    client.read_all_timers = AsyncMock()

    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    cached = {"MBF_PAR_FILT_MODE": 1, "MBF_PAR_TEMPERATURE_ACTIVE": 1}
    coordinator.data = cached

    data = await coordinator._async_update_data()

    client.async_read_all.assert_not_called()
    assert data is cached  # same object – not a copy, frozen in place


@pytest.mark.asyncio
async def test_winter_mode_disabled_resumes_modbus(mock_entry):
    """When winter_mode is False the coordinator communicates normally."""
    mock_entry.options = {"winter_mode": False}

    client = AsyncMock()
    client.async_read_all = AsyncMock(return_value={"MBF_POWER_MODULE_VERSION": 0x0100})
    client.read_all_timers = AsyncMock(return_value={})

    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )

    data = await coordinator._async_update_data()

    client.async_read_all.assert_called_once()
    assert "MBF_POWER_MODULE_VERSION" in data


@pytest.mark.asyncio
async def test_set_winter_mode(mock_entry):
    """set_winter_mode persists state, clears data on enable, skips clear on disable."""
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    coordinator = VistaPoolCoordinator(
        hass, MagicMock(), mock_entry, mock_entry.entry_id
    )
    coordinator.async_set_updated_data = MagicMock()
    assert coordinator.winter_mode is False

    # Enable: data is replaced with the capability snapshot immediately
    coordinator.data = {"MBF_PAR_FILT_MODE": 0}  # no CAPABILITY_KEYS → snapshot is {}
    await coordinator.set_winter_mode(True)
    assert coordinator.winter_mode is True
    options_saved = hass.config_entries.async_update_entry.call_args[1]["options"]
    assert options_saved["winter_mode"] is True
    assert "_capabilities" in options_saved
    assert options_saved["_capabilities"] == {}
    coordinator.async_set_updated_data.assert_called_once_with({})

    # Disable: no data clear
    coordinator.async_set_updated_data.reset_mock()
    await coordinator.set_winter_mode(False)
    assert coordinator.winter_mode is False
    options_saved = hass.config_entries.async_update_entry.call_args[1]["options"]
    assert options_saved["winter_mode"] is False
    coordinator.async_set_updated_data.assert_not_called()


@pytest.mark.asyncio
async def test_set_winter_mode_snapshots_capability_keys(mock_entry):
    """set_winter_mode(True) extracts only CAPABILITY_KEYS from data and persists them."""
    from custom_components.vistapool.const import CAPABILITY_KEYS

    hass = MagicMock()
    options_saved = {}
    hass.config_entries.async_update_entry = MagicMock(
        side_effect=lambda entry, **kw: options_saved.update(kw.get("options", {}))
    )
    coordinator = VistaPoolCoordinator(
        hass, MagicMock(), mock_entry, mock_entry.entry_id
    )
    coordinator.async_set_updated_data = MagicMock()

    # Simulate full coordinator data: capability keys + measurement registers
    coordinator.data = {
        "MBF_PAR_MODEL": 3,
        "MBF_PAR_TEMPERATURE_ACTIVE": 1,
        "MBF_PAR_HEATING_GPIO": 5,
        "MBF_MEASURE_TEMPERATURE": 27.5,  # measurement – must NOT be in snapshot
        "MBF_PAR_FILT_MODE": 2,  # runtime value – must NOT be in snapshot
    }

    await coordinator.set_winter_mode(True)

    saved_caps = options_saved["_capabilities"]
    # Capability keys present in data must appear in the snapshot
    assert saved_caps["MBF_PAR_MODEL"] == 3
    assert saved_caps["MBF_PAR_TEMPERATURE_ACTIVE"] == 1
    assert saved_caps["MBF_PAR_HEATING_GPIO"] == 5
    # All saved keys must be real CAPABILITY_KEYS
    for key in saved_caps:
        assert key in CAPABILITY_KEYS
    # Non-capability measurement values must be excluded
    assert "MBF_MEASURE_TEMPERATURE" not in saved_caps
    assert "MBF_PAR_FILT_MODE" not in saved_caps
    # async_set_updated_data must be called with the capability snapshot (not {})
    coordinator.async_set_updated_data.assert_called_once_with(saved_caps)


@pytest.mark.asyncio
async def test_winter_mode_restores_capabilities_from_options_on_restart(mock_entry):
    """After a restart in winter mode, _capability_snapshot is loaded from entry.options."""
    saved_caps = {"MBF_PAR_MODEL": 3, "MBF_PAR_TEMPERATURE_ACTIVE": 1}
    mock_entry.options = {"winter_mode": True, "_capabilities": saved_caps}

    client = AsyncMock()
    client.async_read_all = AsyncMock()

    coordinator = VistaPoolCoordinator(
        MagicMock(), client, mock_entry, mock_entry.entry_id
    )
    # Simulate the very first _async_update_data call after restart (data is None)
    coordinator.data = None

    data = await coordinator._async_update_data()

    client.async_read_all.assert_not_called()
    assert data == saved_caps
    assert data["MBF_PAR_MODEL"] == 3


@pytest.mark.asyncio
async def test_async_update_data_updates_capability_snapshot(mock_entry):
    """A successful Modbus read updates _capability_snapshot with the capability keys
    and persists it to entry.options so it survives HA restarts while Modbus is down."""
    mock_entry.options = {"winter_mode": False}

    client = AsyncMock()
    client.async_read_all = AsyncMock(
        return_value={
            "MBF_POWER_MODULE_VERSION": 0x0100,
            "MBF_PAR_MODEL": 2,
            "MBF_PAR_TEMPERATURE_ACTIVE": 1,
            "MBF_MEASURE_TEMPERATURE": 26.0,
        }
    )
    client.read_all_timers = AsyncMock(return_value={})

    hass = MagicMock()
    coordinator = VistaPoolCoordinator(hass, client, mock_entry, mock_entry.entry_id)
    assert coordinator._capability_snapshot == {}

    await coordinator._async_update_data()

    assert coordinator._capability_snapshot["MBF_PAR_MODEL"] == 2
    assert coordinator._capability_snapshot["MBF_PAR_TEMPERATURE_ACTIVE"] == 1
    # Measurement registers must not be included
    assert "MBF_MEASURE_TEMPERATURE" not in coordinator._capability_snapshot
    assert "MBF_POWER_MODULE_VERSION" not in coordinator._capability_snapshot
    # Must also be persisted to entry.options via async_update_entry
    hass.config_entries.async_update_entry.assert_called_once()
    saved_options = hass.config_entries.async_update_entry.call_args[1]["options"]
    assert saved_options["_capabilities"]["MBF_PAR_MODEL"] == 2
    assert saved_options["_capabilities"]["MBF_PAR_TEMPERATURE_ACTIVE"] == 1


@pytest.mark.asyncio
async def test_request_refresh_with_followup(mock_entry, monkeypatch):
    """request_refresh_with_followup schedules a follow-up without immediate refresh."""
    client = AsyncMock()
    hass = MagicMock()
    coordinator = VistaPoolCoordinator(hass, client, mock_entry, mock_entry.entry_id)
    coordinator.async_request_refresh = AsyncMock()

    calls = []

    def fake_call_later(hass, delay, action):
        calls.append((delay, action))
        return lambda: None

    monkeypatch.setattr(
        "custom_components.vistapool.coordinator.async_call_later", fake_call_later
    )

    coordinator.request_refresh_with_followup()
    coordinator.async_request_refresh.assert_not_awaited()
    assert len(calls) == 1
    assert calls[0][0] == FOLLOW_UP_REFRESH_DELAY


@pytest.mark.asyncio
async def test_request_refresh_with_followup_custom_delay(mock_entry, monkeypatch):
    """Follow-up delay can be customized."""
    client = AsyncMock()
    hass = MagicMock()
    coordinator = VistaPoolCoordinator(hass, client, mock_entry, mock_entry.entry_id)
    coordinator.async_request_refresh = AsyncMock()

    calls = []

    def fake_call_later(hass, delay, action):
        calls.append((delay, action))
        return lambda: None

    monkeypatch.setattr(
        "custom_components.vistapool.coordinator.async_call_later", fake_call_later
    )

    coordinator.request_refresh_with_followup(delay=5.0)
    assert calls[0][0] == 5.0


@pytest.mark.asyncio
async def test_follow_up_cancels_previous(mock_entry, monkeypatch):
    """A new follow-up refresh cancels any previously scheduled one."""
    client = AsyncMock()
    hass = MagicMock()
    coordinator = VistaPoolCoordinator(hass, client, mock_entry, mock_entry.entry_id)
    coordinator.async_request_refresh = AsyncMock()

    unsub = MagicMock()

    def fake_call_later(hass, delay, action):
        return unsub

    monkeypatch.setattr(
        "custom_components.vistapool.coordinator.async_call_later", fake_call_later
    )

    coordinator.request_refresh_with_followup()
    assert unsub.call_count == 0  # first schedule, nothing to cancel

    coordinator.request_refresh_with_followup()
    assert unsub.call_count == 1  # previous follow-up was cancelled


@pytest.mark.asyncio
async def test_follow_up_callback_triggers_refresh(mock_entry, monkeypatch):
    """The scheduled follow-up callback clears unsub and creates a refresh task."""
    client = AsyncMock()
    hass = MagicMock()
    coordinator = VistaPoolCoordinator(hass, client, mock_entry, mock_entry.entry_id)
    coordinator.async_request_refresh = AsyncMock()

    captured_callback = None

    def fake_call_later(hass, delay, action):
        nonlocal captured_callback
        captured_callback = action
        return MagicMock()

    monkeypatch.setattr(
        "custom_components.vistapool.coordinator.async_call_later", fake_call_later
    )

    coordinator.request_refresh_with_followup()
    assert captured_callback is not None
    assert coordinator._follow_up_unsub is not None

    # Simulate the timer firing
    captured_callback(None)
    assert coordinator._follow_up_unsub is None
    hass.async_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_follow_up_refresh(mock_entry, monkeypatch):
    """cancel_follow_up_refresh cancels a pending follow-up and clears the handle."""
    client = AsyncMock()
    hass = MagicMock()
    coordinator = VistaPoolCoordinator(hass, client, mock_entry, mock_entry.entry_id)
    coordinator.async_request_refresh = AsyncMock()

    unsub = MagicMock()

    def fake_call_later(hass, delay, action):
        return unsub

    monkeypatch.setattr(
        "custom_components.vistapool.coordinator.async_call_later", fake_call_later
    )

    coordinator.request_refresh_with_followup()
    assert coordinator._follow_up_unsub is not None

    coordinator.cancel_follow_up_refresh()
    unsub.assert_called_once()
    assert coordinator._follow_up_unsub is None


@pytest.mark.asyncio
async def test_cancel_follow_up_refresh_noop_when_none(mock_entry):
    """cancel_follow_up_refresh is safe to call when no follow-up is pending."""
    client = AsyncMock()
    hass = MagicMock()
    coordinator = VistaPoolCoordinator(hass, client, mock_entry, mock_entry.entry_id)
    assert coordinator._follow_up_unsub is None
    coordinator.cancel_follow_up_refresh()  # should not raise
    assert coordinator._follow_up_unsub is None


class TestGpioSanityCheck:
    """Tests for _check_gpio_registers."""

    PATCH_TARGET = (
        "custom_components.vistapool.coordinator.persistent_notification.async_create"
    )
    PATCH_DISMISS = (
        "custom_components.vistapool.coordinator.persistent_notification.async_dismiss"
    )

    def _make_coordinator(self, mock_entry):
        hass = MagicMock()
        client = AsyncMock()
        coordinator = VistaPoolCoordinator(
            hass, client, mock_entry, mock_entry.entry_id
        )
        return coordinator, hass

    def test_valid_gpio_values_no_notification(self, mock_entry):
        """No notification when all GPIO registers are within valid range."""
        coordinator, hass = self._make_coordinator(mock_entry)
        data = {
            "MBF_PAR_FILT_GPIO": 2,
            "MBF_PAR_LIGHTING_GPIO": 3,
            "MBF_PAR_HEATING_GPIO": 7,
            "MBF_PAR_PH_ACID_RELAY_GPIO": 1,
            "MBF_PAR_UV_RELAY_GPIO": 0,
        }
        with (
            patch(self.PATCH_TARGET) as mock_notify,
            patch(self.PATCH_DISMISS) as mock_dismiss,
        ):
            coordinator._check_gpio_registers(data)
            mock_notify.assert_not_called()
            mock_dismiss.assert_called_once_with(hass, "vistapool_corrupted_gpio")

    def test_corrupted_gpio_triggers_notification(self, mock_entry):
        """Notification is created when a GPIO register has an invalid value."""
        coordinator, hass = self._make_coordinator(mock_entry)
        data = {
            "MBF_PAR_FILT_GPIO": 22846,  # corrupted
            "MBF_PAR_LIGHTING_GPIO": 3,
        }
        with patch(self.PATCH_TARGET) as mock_notify:
            coordinator._check_gpio_registers(data)
            mock_notify.assert_called_once()
            # hass must be passed as first positional arg, not as keyword
            assert mock_notify.call_args.args[0] is hass
            assert "hass" not in mock_notify.call_args.kwargs
            call_kwargs = mock_notify.call_args.kwargs
            assert "Corrupted GPIO" in call_kwargs["title"]
            assert "22846" in call_kwargs["message"]
            assert "MBF_PAR_FILT_GPIO" in call_kwargs["message"]
            assert call_kwargs["notification_id"] == "vistapool_corrupted_gpio"

    def test_multiple_corrupted_gpio_in_single_notification(self, mock_entry):
        """Multiple corrupted GPIO registers appear in a single notification."""
        coordinator, _ = self._make_coordinator(mock_entry)
        data = {
            "MBF_PAR_FILT_GPIO": 22846,
            "MBF_PAR_HEATING_GPIO": 65535,
        }
        with patch(self.PATCH_TARGET) as mock_notify:
            coordinator._check_gpio_registers(data)
            mock_notify.assert_called_once()
            msg = mock_notify.call_args.kwargs["message"]
            assert "MBF_PAR_FILT_GPIO" in msg
            assert "MBF_PAR_HEATING_GPIO" in msg

    def test_missing_gpio_keys_no_notification(self, mock_entry):
        """No notification when GPIO keys are absent from data."""
        coordinator, _ = self._make_coordinator(mock_entry)
        with patch(self.PATCH_TARGET) as mock_notify:
            coordinator._check_gpio_registers({})
            mock_notify.assert_not_called()

    def test_zero_gpio_is_valid(self, mock_entry):
        """GPIO value 0 (unassigned) is within valid range and should not trigger notification."""
        coordinator, _ = self._make_coordinator(mock_entry)
        data = {"MBF_PAR_FILT_GPIO": 0}
        with patch(self.PATCH_TARGET) as mock_notify:
            coordinator._check_gpio_registers(data)
            mock_notify.assert_not_called()

    def test_negative_gpio_triggers_notification(self, mock_entry):
        """Negative GPIO value is out of range and triggers notification."""
        coordinator, _ = self._make_coordinator(mock_entry)
        data = {"MBF_PAR_FILT_GPIO": -1}
        with patch(self.PATCH_TARGET) as mock_notify:
            coordinator._check_gpio_registers(data)
            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_gpio_check_runs_only_once(self, mock_entry):
        """_check_gpio_registers is called only on the first successful read."""
        coordinator, _ = self._make_coordinator(mock_entry)
        coordinator.client.async_read_all = AsyncMock(
            return_value={
                "MBF_POWER_MODULE_VERSION": 0x1234,
                "MBF_PAR_FILT_GPIO": 22846,
            }
        )
        coordinator.client.read_all_timers = AsyncMock(return_value={})

        with patch(self.PATCH_TARGET) as mock_notify:
            await coordinator._async_update_data()
            assert coordinator._gpio_checked is True
            assert mock_notify.call_count == 1

            # Second call should NOT trigger check again
            mock_notify.reset_mock()
            await coordinator._async_update_data()
            mock_notify.assert_not_called()
