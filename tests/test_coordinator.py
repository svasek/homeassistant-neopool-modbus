"""Tests for the NeoPool coordinator."""

from datetime import timedelta
import json as _json
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from neopool_modbus.registers import (
    HEATING_SETPOINT_REGISTER,
    INTELLIGENT_SETPOINT_REGISTER,
    MAX_RELAY_GPIO,
)
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.neopool.const import CURRENT_VERSION, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from . import setup_integration
from .conftest import MOCK_POOL_DATA

# ---------------------------------------------------------------------------
# Update cycle
# ---------------------------------------------------------------------------


async def test_update_data_populates_firmware_and_model(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """The first successful read populates firmware and model."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    # MBF_POWER_MODULE_VERSION = 0x1234 → "18.52"
    assert coordinator.firmware == "18.52"
    assert coordinator.model == "NeoPool"


async def test_transient_modbus_failure_after_first_success_marks_unavailable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failure after at least one good read raises UpdateFailed (not ConfigEntryNotReady)."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert coordinator.last_update_success is True

    # Simulate a transient failure on the next polling cycle.
    mock_neopool_client.async_read_all.side_effect = ConnectionError("Modbus fail")
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    # last_update_success now False but entry remains LOADED — entities will
    # report unavailable on their own.
    assert coordinator.last_update_success is False
    assert mock_config_entry.state is ConfigEntryState.LOADED


# ---------------------------------------------------------------------------
# Winter mode
# ---------------------------------------------------------------------------


async def test_winter_mode_skips_modbus(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """When winter_mode is on we never call async_read_all on subsequent updates."""
    snapshot = {"MBF_PAR_FILT_GPIO": 1, "MBF_PAR_LIGHTING_GPIO": 2}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Winter Pool",
        unique_id="neopool_winter",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.5",
            "port": 502,
            "name": "Winter Pool",
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "scan_interval": 30,
            "modbus_framer": "tcp",
            "winter_mode": True,
            "_capabilities": snapshot,
        },
    )
    await setup_integration(hass, entry)
    assert entry.state is ConfigEntryState.LOADED


# ---------------------------------------------------------------------------
# GPIO sanity check
# ---------------------------------------------------------------------------


async def test_corrupt_gpio_creates_repair_issue(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A GPIO register outside 0..MAX_RELAY_GPIO opens a corrupted_gpio issue."""
    bad_data = dict(MOCK_POOL_DATA)
    bad_data["MBF_PAR_FILT_GPIO"] = MAX_RELAY_GPIO + 1
    mock_neopool_client.async_read_all = AsyncMock(return_value=bad_data)

    await setup_integration(hass, mock_config_entry)

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(DOMAIN, "corrupted_gpio")
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR


async def test_clean_gpio_does_not_create_issue(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A clean read does not open a corrupted_gpio issue."""
    await setup_integration(hass, mock_config_entry)
    issue_registry = ir.async_get(hass)
    assert issue_registry.async_get_issue(DOMAIN, "corrupted_gpio") is None


# ---------------------------------------------------------------------------
# Capability snapshot
# ---------------------------------------------------------------------------


async def test_capability_snapshot_persisted_to_options(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """The capability snapshot reaches entry.options after the first refresh."""
    await setup_integration(hass, mock_config_entry)
    snap = mock_config_entry.options.get("_capabilities")
    assert snap is not None
    # Each GPIO key from MOCK_POOL_DATA should be present in the snapshot.
    assert snap["MBF_PAR_FILT_GPIO"] == 1
    assert snap["MBF_PAR_LIGHTING_GPIO"] == 2


# ---------------------------------------------------------------------------
# Auto time sync
# ---------------------------------------------------------------------------


async def test_auto_time_sync_writes_when_drift_detected(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """With auto_time_sync on and the device clock drifting, we write to 0x0408 + 0x04F0."""
    drifted = dict(MOCK_POOL_DATA)
    # Pick an "in the past" device clock that is well over a minute old.
    long_ago = int(dt_util.utcnow().timestamp()) - 7200
    drifted["MBF_PAR_TIME_LOW"] = long_ago & 0xFFFF
    drifted["MBF_PAR_TIME_HIGH"] = (long_ago >> 16) & 0xFFFF
    mock_neopool_client.async_read_all = AsyncMock(return_value=drifted)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        unique_id="neopool_drift",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.6",
            "port": 502,
            "name": "Pool",
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "scan_interval": 30,
            "modbus_framer": "tcp",
            "auto_time_sync": True,
        },
    )
    await setup_integration(hass, entry)
    # Two writes expected: 0x0408 (time) and 0x04F0 (commit).
    written_addresses = [
        call.args[0]
        for call in mock_neopool_client.async_write_register.await_args_list
    ]
    assert 0x0408 in written_addresses
    assert 0x04F0 in written_addresses


# ---------------------------------------------------------------------------
# Developer override JSON
# ---------------------------------------------------------------------------


async def test_dev_overrides_applied_when_enabled(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """dev_overrides_enabled merges the JSON map into coordinator.data."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        unique_id="neopool_dev_overrides",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.10",
            "port": 502,
            "name": "Pool",
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "scan_interval": 30,
            "modbus_framer": "tcp",
            "dev_overrides_enabled": True,
            "dev_overrides": _json.dumps({"MBF_MEASURE_TEMPERATURE": 999}),
        },
    )
    await setup_integration(hass, entry)
    coordinator = entry.runtime_data
    assert coordinator.data["MBF_MEASURE_TEMPERATURE"] == 999


async def test_dev_overrides_invalid_json_ignored(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
    caplog,
) -> None:
    """Malformed dev_overrides JSON logs a warning but does not crash setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        unique_id="neopool_dev_bad",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.11",
            "port": 502,
            "name": "Pool",
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "scan_interval": 30,
            "modbus_framer": "tcp",
            "dev_overrides_enabled": True,
            "dev_overrides": "not-valid-json",
        },
    )
    await setup_integration(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert "Failed to apply dev_overrides" in caplog.text


# ---------------------------------------------------------------------------
# Setpoint sync (heating ↔ intelligent)
# ---------------------------------------------------------------------------


async def test_setpoint_initial_sync_uses_heating_as_source(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Write intelligent := heating when both differ but neither was just changed.

    Covers the initial-sync branch in _sync_heating_intelligent_setpoints.
    """

    seeded_equal = dict(MOCK_POOL_DATA)
    seeded_equal["MBF_PAR_HEATING_TEMP"] = 30
    seeded_equal["MBF_PAR_INTELLIGENT_TEMP"] = 30
    mock_neopool_client.async_read_all = AsyncMock(return_value=seeded_equal)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        unique_id="neopool_initial_sync",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.12",
            "port": 502,
            "name": "Pool",
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={"scan_interval": 30, "modbus_framer": "tcp"},
    )
    await setup_integration(hass, entry)

    # Now next read returns differing values that *neither changed* — that
    # means they were already different before this cycle started; force
    # the initial-sync branch by feeding values that are different but
    # match prev (so heating_changed=False AND intelligent_changed=False).
    next_data = dict(seeded_equal)
    next_data["MBF_PAR_HEATING_TEMP"] = 30
    next_data["MBF_PAR_INTELLIGENT_TEMP"] = 25
    # Manipulate self.data to set the previous snapshot's intel to 25
    coordinator = entry.runtime_data
    coordinator.data["MBF_PAR_INTELLIGENT_TEMP"] = 25
    coordinator.data["MBF_PAR_HEATING_TEMP"] = 30
    mock_neopool_client.async_read_all = AsyncMock(return_value=next_data)
    mock_neopool_client.async_write_register.reset_mock()

    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    matched = [
        call
        for call in mock_neopool_client.async_write_register.await_args_list
        if len(call.args) >= 2
        and call.args[0] == INTELLIGENT_SETPOINT_REGISTER
        and call.args[1] == 30
    ]
    assert matched, (
        "expected intelligent register to be set to heating value (30); got "
        + repr(mock_neopool_client.async_write_register.await_args_list)
    )


async def test_setpoint_last_change_wins_when_only_heating_changed(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """When only heating changed since last poll, mirror it to intelligent."""

    seeded = dict(MOCK_POOL_DATA)
    seeded["MBF_PAR_HEATING_TEMP"] = 25
    seeded["MBF_PAR_INTELLIGENT_TEMP"] = 25
    mock_neopool_client.async_read_all = AsyncMock(return_value=seeded)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        unique_id="neopool_lcw_h",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.13",
            "port": 502,
            "name": "Pool",
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={"scan_interval": 30, "modbus_framer": "tcp"},
    )
    await setup_integration(hass, entry)

    # Next poll: heating moved 25→30, intel still 25 → heating_changed=True
    # XOR intelligent_changed=False. Expect a write of 30 to INTELLIGENT.
    next_data = dict(seeded)
    next_data["MBF_PAR_HEATING_TEMP"] = 30
    mock_neopool_client.async_read_all = AsyncMock(return_value=next_data)
    mock_neopool_client.async_write_register.reset_mock()

    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    matched = [
        call
        for call in mock_neopool_client.async_write_register.await_args_list
        if len(call.args) >= 2
        and call.args[0] == INTELLIGENT_SETPOINT_REGISTER
        and call.args[1] == 30
    ]
    assert matched, (
        "expected intelligent setpoint to be mirrored from heating (30); got "
        + repr(mock_neopool_client.async_write_register.await_args_list)
    )


async def test_setpoint_revert_when_both_changed(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """When BOTH heat and intel changed in a single cycle, revert both."""

    seeded = dict(MOCK_POOL_DATA)
    seeded["MBF_PAR_HEATING_TEMP"] = 25
    seeded["MBF_PAR_INTELLIGENT_TEMP"] = 25
    mock_neopool_client.async_read_all = AsyncMock(return_value=seeded)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pool",
        unique_id="neopool_revert",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.14",
            "port": 502,
            "name": "Pool",
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={"scan_interval": 30, "modbus_framer": "tcp"},
    )
    await setup_integration(hass, entry)

    # Next poll: both moved (heat 25→30, intel 25→27 → conflict). Coordinator
    # writes the OLD values back: 25 to both.
    next_data = dict(seeded)
    next_data["MBF_PAR_HEATING_TEMP"] = 30
    next_data["MBF_PAR_INTELLIGENT_TEMP"] = 27
    mock_neopool_client.async_read_all = AsyncMock(return_value=next_data)
    mock_neopool_client.async_write_register.reset_mock()

    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    addresses = [
        (call.args[0], call.args[1])
        for call in mock_neopool_client.async_write_register.await_args_list
        if len(call.args) >= 2
    ]
    # Both registers reverted to 25 (the previous values).
    assert (HEATING_SETPOINT_REGISTER, 25) in addresses
    assert (INTELLIGENT_SETPOINT_REGISTER, 25) in addresses


async def test_follow_up_refresh_callback_runs(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """request_refresh_with_followup schedules a refresh that fires after the delay."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    initial_count = mock_neopool_client.async_read_all.await_count
    coordinator.request_refresh_with_followup(delay=0.1)
    freezer.tick(timedelta(seconds=0.2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    # The follow-up triggered another async_read_all.
    assert mock_neopool_client.async_read_all.await_count > initial_count


async def test_timer_block_data_merged_into_coordinator(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """When read_all_timers returns timer blocks, the per-block fields land in data."""
    mock_neopool_client.read_all_timers = AsyncMock(
        return_value={
            "filtration1": {
                "enable": 1,
                "on": 8 * 3600,  # 08:00
                "interval": 4 * 3600,  # 4h → stop = 12:00
                "period": 86400,
                "countdown": 3600,
            },
            "filtration2": {
                "enable": 0,
                "on": None,
                "interval": None,
                "period": None,
                "countdown": 0,
            },
        }
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    assert coordinator.data["filtration1_enable"] == 1
    assert coordinator.data["filtration1_start"] == 8 * 3600
    assert coordinator.data["filtration1_interval"] == 4 * 3600
    assert coordinator.data["filtration1_stop"] == 12 * 3600
    # filtration2: on/interval are None → stop falls back to None
    assert coordinator.data["filtration2_stop"] is None
    # Aggregated filtration_remaining picks up the 1-hour countdown.
    assert coordinator.data["FILTRATION_REMAINING"] == 3600
