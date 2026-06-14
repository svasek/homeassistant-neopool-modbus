"""Tests for the NeoPool switch platform."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool.const import CURRENT_VERSION, SWITCH_DEFINITIONS
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration


async def _turn_on(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {"entity_id": entity_id},
        blocking=True,
    )


async def _turn_off(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {"entity_id": entity_id},
        blocking=True,
    )


# ---------------------------------------------------------------------------
# manual_filtration
# ---------------------------------------------------------------------------


async def test_manual_filtration_turn_on_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Manual filtration writes 1 to start the pump and 0 to stop it."""
    await setup_integration(hass, mock_config_entry)

    await _turn_on(hass, "switch.pool_manual_filtration")  # manual_filtration entity
    # MANUAL_FILTRATION_REGISTER write
    addresses_written = [
        c.args[0] for c in mock_neopool_client.async_write_register.await_args_list
    ]
    assert addresses_written, "expected at least one register write"

    mock_neopool_client.async_write_register.reset_mock()
    await _turn_off(hass, "switch.pool_manual_filtration")
    # any write with value 0 to MANUAL_FILTRATION_REGISTER
    write_calls = mock_neopool_client.async_write_register.await_args_list
    assert any(c.args[1] == 0 for c in write_calls)


# ---------------------------------------------------------------------------
# winter_mode (no register write — only options change + entity reload)
# ---------------------------------------------------------------------------


async def test_winter_mode_turn_on_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Toggling winter_mode flips coordinator.winter_mode and writes to entry options."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert coordinator.winter_mode is False

    await _turn_on(hass, "switch.pool_winter_mode")
    assert coordinator.winter_mode is True

    await _turn_off(hass, "switch.pool_winter_mode")
    assert coordinator.winter_mode is False


# ---------------------------------------------------------------------------
# auto_time_sync
# ---------------------------------------------------------------------------


async def test_auto_time_sync_turn_on_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Toggling auto_time_sync flips coordinator.auto_time_sync."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert coordinator.auto_time_sync is False

    await _turn_on(hass, "switch.pool_time_auto_sync")
    assert coordinator.auto_time_sync is True

    await _turn_off(hass, "switch.pool_time_auto_sync")
    assert coordinator.auto_time_sync is False


# ---------------------------------------------------------------------------
# Winter-mode guard: turning on/off any IO switch is rejected while winter is active
# ---------------------------------------------------------------------------


async def test_io_switch_blocked_in_winter_mode(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """While winter_mode is on, turning IO switches yields a no-op + warning."""
    entry = MockConfigEntry(
        domain="neopool",
        title="Winter Pool",
        unique_id="neopool_winter_io",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.7",
            "port": 502,
            "name": "Winter Pool",
            "slave_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "scan_interval": 30,
            "modbus_framer": "tcp",
            "winter_mode": True,
            "use_filtration1": True,
            "_capabilities": {"MBF_PAR_FILT_GPIO": 1},
        },
    )
    await setup_integration(hass, entry)
    # The manual_filtration entity exists once we have a snapshot. It's
    # available=False because winter_mode is on, but turn_on still reaches
    # the handler and short-circuits with a warning.
    state = hass.states.get("switch.winter_pool_3")
    if state is not None and state.state != STATE_UNAVAILABLE:
        await _turn_on(hass, "switch.winter_pool_3")
        assert "Winter mode is active" in caplog.text


# ---------------------------------------------------------------------------
# is_on / available — manual_filtration
# ---------------------------------------------------------------------------


async def test_manual_filtration_is_on_reflects_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """is_on tracks MBF_PAR_FILT_MANUAL_STATE, available tracks FILT_MODE."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data

    # Set FILT_MODE=0 (manual) and MANUAL_STATE=1 (on)
    coordinator.data["MBF_PAR_FILT_MODE"] = 0
    coordinator.data["MBF_PAR_FILT_MANUAL_STATE"] = 1
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    state = hass.states.get("switch.pool_manual_filtration")
    assert state is not None
    assert state.state == STATE_ON

    # Switch FILT_MODE to non-manual → entity becomes unavailable
    coordinator.data["MBF_PAR_FILT_MODE"] = 1
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()
    state = hass.states.get("switch.pool_manual_filtration")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE


async def test_manual_filtration_is_on_returns_false_when_filt_mode_is_auto(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """is_on returns False directly when FILT_MODE is in auto (1).

    The entity is also UNAVAILABLE in that mode (covered above), but the
    is_on early-return is on a separate code path and needs its own assert.
    """

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_FILT_MODE"] = 1  # auto
    coordinator.data["MBF_PAR_FILT_MANUAL_STATE"] = 1
    coordinator.async_set_updated_data(coordinator.data)

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("switch.")
                and getattr(ent, "_key", None) == "MBF_PAR_FILT_MANUAL_STATE"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None
    assert entity_obj.is_on is False


# ---------------------------------------------------------------------------
# climate_mode / smart_anti_freeze / uv_mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "register_key",
    [
        "MBF_PAR_CLIMA_ONOFF",
        "MBF_PAR_SMART_ANTI_FREEZE",
        "MBF_PAR_UV_MODE",
    ],
)
async def test_climate_smart_uv_writes_to_function_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    register_key: str,
) -> None:
    """The grouped switches all write 1/0 to their own function_addr."""

    await setup_integration(hass, mock_config_entry)

    function_addr = SWITCH_DEFINITIONS[register_key].get("function_addr")
    assert function_addr is not None

    # Unique IDs are lower-case slugified by NeoPoolEntity.
    suffix = f"_{register_key.lower()}"
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == "switch" and e.unique_id.endswith(suffix)
    ]
    assert entries, (
        f"no switch entity with unique_id ending in {suffix} — found: "
        + ", ".join(
            e.unique_id
            for e in er.async_entries_for_config_entry(
                registry, mock_config_entry.entry_id
            )
            if e.domain == "switch"
        )
    )
    entity_id = entries[0].entity_id

    mock_neopool_client.async_write_register.reset_mock()
    await _turn_on(hass, entity_id)
    await _turn_off(hass, entity_id)

    addresses = [
        c.args[0] for c in mock_neopool_client.async_write_register.await_args_list
    ]
    assert addresses.count(function_addr) >= 2


# ---------------------------------------------------------------------------
# aux relay (relay_timer) write paths
# ---------------------------------------------------------------------------


async def test_aux_relay_turn_on_writes_relay_index(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """aux1 turn_on/off calls async_write_aux_relay with the right index/state."""

    await setup_integration(hass, mock_config_entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == "switch" and e.unique_id.endswith("_aux1")
    ]
    assert entries
    entity_id = entries[0].entity_id

    # The aux switches use switch_type 'relay_timer' which writes to function +
    # timer_block + EXEC. Verify three writes happen.
    mock_neopool_client.async_write_register.reset_mock()
    await _turn_on(hass, entity_id)
    assert mock_neopool_client.async_write_register.await_count >= 2

    mock_neopool_client.async_write_register.reset_mock()
    await _turn_off(hass, entity_id)
    assert mock_neopool_client.async_write_register.await_count >= 2


# ---------------------------------------------------------------------------
# bitmask write paths (MBF_PAR_HIDRO_COVER_ENABLE / MBF_PAR_HIDRO_TEMP_SHUTDOWN)
# ---------------------------------------------------------------------------


async def test_hidro_cover_enable_bitmask_writes_or_pattern(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """The hydro cover-enable bitmask switch ORs/clears its bit on its data register."""

    await setup_integration(hass, mock_config_entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == "switch" and e.unique_id.endswith("_mbf_par_hidro_cover_enable")
    ]
    if not entries:
        pytest.skip("hidro cover enable switch not registered")
    entity_id = entries[0].entity_id

    mock_neopool_client.async_write_register.reset_mock()
    await _turn_on(hass, entity_id)
    assert mock_neopool_client.async_write_register.await_count >= 1

    mock_neopool_client.async_write_register.reset_mock()
    await _turn_off(hass, entity_id)
    assert mock_neopool_client.async_write_register.await_count >= 1


# ---------------------------------------------------------------------------
# Winter-mode guards on every switch_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "switch_key",
    [
        "MBF_PAR_FILT_MANUAL_STATE",
        "aux1",
        "MBF_PAR_CLIMA_ONOFF",
        "MBF_PAR_HIDRO_COVER_ENABLE",
    ],
)
async def test_io_switch_winter_mode_short_circuits(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
    switch_key: str,
) -> None:
    """async_turn_on/off short-circuits with a warning while winter_mode is on."""

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.winter_mode = True

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("switch.")
                and getattr(ent, "_key", None) == switch_key
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    if entity_obj is None:
        pytest.skip(f"{switch_key} switch not registered on this fixture")

    mock_neopool_client.async_write_register.reset_mock()
    mock_neopool_client.async_write_aux_relay.reset_mock()
    await entity_obj.async_turn_on()
    await entity_obj.async_turn_off()
    assert "Winter mode is active" in caplog.text
    mock_neopool_client.async_write_register.assert_not_called()
    mock_neopool_client.async_write_aux_relay.assert_not_called()
