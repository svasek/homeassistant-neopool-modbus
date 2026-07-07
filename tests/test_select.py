"""Tests for the NeoPool select platform."""

from unittest.mock import MagicMock, patch

from neopool_modbus.registers import MANUAL_FILTRATION_REGISTER
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_OPTION, SERVICE_SELECT_OPTION, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration
from .conftest import MOCK_POOL_DATA


def _select_entity_id(
    hass: HomeAssistant, entry: MockConfigEntry, key_lower_suffix: str
) -> str:
    """Resolve a select entity by its trailing unique_id segment."""
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "select" and e.unique_id.endswith(f"_{key_lower_suffix}")
    ]
    assert entries, (
        f"no select entity ending in _{key_lower_suffix}, found: "
        + ", ".join(
            e.unique_id
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.domain == "select"
        )
    )
    return entries[0].entity_id


async def _select_option(hass: HomeAssistant, entity_id: str, option: str) -> None:
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {"entity_id": entity_id, ATTR_OPTION: option},
        blocking=True,
    )


# ---------------------------------------------------------------------------
# default_register dispatch (MBF_PAR_FILT_MODE)
# ---------------------------------------------------------------------------


async def test_filt_mode_select_writes_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Selecting a filtration mode delegates to the lib's async_set_filtration_mode."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _select_entity_id(hass, mock_config_entry, "mbf_par_filt_mode")

    mock_neopool_client.async_set_filtration_mode.reset_mock()
    await _select_option(hass, entity_id, "auto")
    mock_neopool_client.async_set_filtration_mode.assert_awaited_once_with("auto")


async def test_filt_mode_leaving_manual_stops_pump_first(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Switching from manual to a non-backwash mode preemptively stops the pump.

    Custom-pre-condition: filtration_mode == "manual". Switching to "auto"
    must first write 0 to MANUAL_FILTRATION_REGISTER before the lib write.
    """

    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILT_MODE": 0,
        "filtration_mode": "manual",
        "MBF_PAR_FILT_MANUAL_STATE": 1,
    }
    await setup_integration(hass, mock_config_entry)

    entity_id = _select_entity_id(hass, mock_config_entry, "mbf_par_filt_mode")
    mock_neopool_client.async_write_register.reset_mock()
    mock_neopool_client.async_set_filtration_mode.reset_mock()
    await _select_option(hass, entity_id, "auto")

    addresses = [
        c.args[0] for c in mock_neopool_client.async_write_register.await_args_list
    ]
    assert MANUAL_FILTRATION_REGISTER in addresses
    mock_neopool_client.async_set_filtration_mode.assert_awaited_once_with("auto")


async def test_filt_mode_backwash_with_auto_valve_keeps_pump_running(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Switching to backwash on a controller WITH auto valve does not stop the pump.

    The Besgo valve needs the pump running to open correctly.
    """

    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILT_MODE": 0,
        "filtration_mode": "manual",
    }
    await setup_integration(hass, mock_config_entry)

    entity_id = _select_entity_id(hass, mock_config_entry, "mbf_par_filt_mode")
    mock_neopool_client.async_write_register.reset_mock()
    mock_neopool_client.async_set_filtration_mode.reset_mock()
    await _select_option(hass, entity_id, "backwash")

    addresses = [
        c.args[0] for c in mock_neopool_client.async_write_register.await_args_list
    ]
    # No write to MANUAL_FILTRATION_REGISTER (pump kept running for valve)
    assert MANUAL_FILTRATION_REGISTER not in addresses
    mock_neopool_client.async_set_filtration_mode.assert_awaited_once_with("backwash")


# CUSTOM-ONLY START, HACS-only manual backwash override coverage.
async def test_filt_mode_options_include_backwash_via_hacs_override(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """`enable_backwash_option` in entry options exposes backwash on setups without auto valve."""
    from custom_components.neopool.const import CURRENT_VERSION

    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILTVALVE_GPIO": 0,  # no auto valve
        "MBF_PAR_FILTVALVE_ENABLE": 0,
        "MBF_PAR_FILT_MODE": 1,  # auto (not currently backwash)
    }

    entry = MockConfigEntry(
        domain="neopool",
        title="Backwash Override Pool",
        unique_id="neopool_backwash_override",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.42",
            "port": 502,
            "name": "Backwash Override Pool",
            "unit_id": 1,
            "modbus_framer": "tcp",
        },
        options={
            "modbus_framer": "tcp",
            "enable_backwash_option": True,
            "_capabilities": {"MBF_PAR_FILT_GPIO": 1},
        },
    )
    await setup_integration(hass, entry)
    entity_id = _select_entity_id(hass, entry, "mbf_par_filt_mode")
    state = hass.states.get(entity_id)
    assert state is not None
    assert "backwash" in state.attributes["options"], state.attributes["options"]


# CUSTOM-ONLY END


# ---------------------------------------------------------------------------
# mapped_register dispatch
# ---------------------------------------------------------------------------


async def test_filtvalve_period_minutes_writes_mapped_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Mapped-register selects reverse-lookup the option label and write it."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _select_entity_id(
        hass, mock_config_entry, "mbf_par_filtvalve_period_minutes"
    )
    mock_neopool_client.async_write_register.reset_mock()
    await _select_option(hass, entity_id, "1_week")
    mock_neopool_client.async_write_register.assert_any_await(0x04ED, 10080)


async def test_filtvalve_mode_writes_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """The Backwash Valve Mode select writes the mapped int to its register."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _select_entity_id(hass, mock_config_entry, "mbf_par_filtvalve_mode")
    mock_neopool_client.async_write_register.reset_mock()
    await _select_option(hass, entity_id, "always_on")
    mock_neopool_client.async_write_register.assert_any_await(0x04E9, 3)


# ---------------------------------------------------------------------------
# cell_boost dispatch
# ---------------------------------------------------------------------------


async def test_cell_boost_active_redox_writes_composite_value(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """active_redox option writes 0x05A0 to the cell boost register."""
    mock_config_entry.add_to_hass(hass)
    # Pre-create the registry entry as ENABLED so the disabled-by-default
    # MBF_CELL_BOOST select shows up after setup.
    er.async_get(hass).async_get_or_create(
        domain="select",
        platform="neopool",
        unique_id=f"{mock_config_entry.unique_id}_mbf_cell_boost",
        config_entry=mock_config_entry,
        suggested_object_id="pool_mbf_cell_boost",
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = _select_entity_id(hass, mock_config_entry, "mbf_cell_boost")
    mock_neopool_client.async_set_cell_boost.reset_mock()
    await _select_option(hass, entity_id, "active_redox")
    mock_neopool_client.async_set_cell_boost.assert_awaited_once_with("active_redox")


@pytest.mark.usefixtures("mock_neopool_client")
async def test_cell_boost_current_option_decodes_register_bits(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """current_option for MBF_CELL_BOOST decodes the register bit pattern."""
    mock_config_entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        domain="select",
        platform="neopool",
        unique_id=f"{mock_config_entry.unique_id}_mbf_cell_boost",
        config_entry=mock_config_entry,
        suggested_object_id="pool_mbf_cell_boost",
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = mock_config_entry.runtime_data

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("select.")
                and getattr(ent, "key", None) == "MBF_CELL_BOOST"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None

    # 0 → "inactive"
    coordinator.data["MBF_CELL_BOOST"] = 0
    assert entity_obj.current_option == "inactive"
    # bit 0x8000 set → "active" (redox control disabled)
    coordinator.data["MBF_CELL_BOOST"] = 0x8000
    assert entity_obj.current_option == "active"
    # 0x0500 | 0x00A0 (both bit groups set, 0x8000 not set) → "active_redox"
    coordinator.data["MBF_CELL_BOOST"] = 0x0500 | 0x00A0
    assert entity_obj.current_option == "active_redox"
    # Fallback: arbitrary value → "inactive"
    coordinator.data["MBF_CELL_BOOST"] = 0x1234
    assert entity_obj.current_option == "inactive"


@pytest.mark.usefixtures("mock_neopool_client")
async def test_relay_mode_current_option_handles_disabled_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Verify the disabled-state branch of a relay_mode select.

    The options list adds 'disabled' when enable=0, and current_option
    returns 'disabled' for that state.
    """

    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["relay_aux1_enable"] = 0  # disabled

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("select.")
                and getattr(ent, "key", None) == "relay_aux1_mode"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None
    assert "disabled" in entity_obj.options
    assert entity_obj.current_option == "disabled"


async def test_timer_period_options_and_current_option(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """timer_period select reads options + current_option from coordinator data."""
    # Pre-set the relay_aux1_period to a known PERIOD_MAP value (1 day).
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "relay_aux1_period": 86400,
    }
    await setup_integration(hass, mock_config_entry)

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("select.")
                and getattr(ent, "key", None) == "relay_aux1_period"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None
    # current_option resolves the seconds value back to its key.
    assert entity_obj.current_option == "1_day"
    # options list is the full PERIOD_MAP.
    assert "1_day" in entity_obj.options
    assert "1_week" in entity_obj.options


@pytest.mark.usefixtures("mock_neopool_client")
async def test_cell_boost_options_drop_active_redox_when_no_redox_module(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Without the Redox module flag, the cell-boost options drop 'active_redox'."""
    mock_config_entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        domain="select",
        platform="neopool",
        unique_id=f"{mock_config_entry.unique_id}_mbf_cell_boost",
        config_entry=mock_config_entry,
        suggested_object_id="pool_mbf_cell_boost",
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = mock_config_entry.runtime_data
    coordinator.data["Redox measurement module detected"] = False

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("select.")
                and getattr(ent, "key", None) == "MBF_CELL_BOOST"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None
    assert "active_redox" not in entity_obj.options


# ---------------------------------------------------------------------------
# filtration_speed dispatch
# ---------------------------------------------------------------------------


async def test_filtration_speed_packs_into_filtration_conf(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Selecting a speed delegates to the lib's async_set_filtration_speed."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_FILTRATION_CONF"] = 0
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    entity_id = _select_entity_id(hass, mock_config_entry, "mbf_par_filtration_speed")
    mock_neopool_client.async_set_filtration_speed.reset_mock()
    await _select_option(hass, entity_id, "high")
    mock_neopool_client.async_set_filtration_speed.assert_awaited_once_with("high")


async def test_filtration_speed_raises_when_not_manual_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Changing filtration speed raises ServiceValidationError outside manual mode."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_FILT_MODE"] = 1  # auto
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    entity_id = _select_entity_id(hass, mock_config_entry, "mbf_par_filtration_speed")
    mock_neopool_client.async_set_filtration_speed.reset_mock()
    with pytest.raises(ServiceValidationError):
        await _select_option(hass, entity_id, "high")
    mock_neopool_client.async_set_filtration_speed.assert_not_awaited()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0x0000, "low"),
        (0x0010, "mid"),
        (0x0020, "high"),
    ],
)
@pytest.mark.usefixtures("mock_neopool_client")
async def test_filtration_speed_current_option_decodes_filtration_conf(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    raw: int,
    expected: str,
) -> None:
    """Current option decodes bits 4-6 of MBF_PAR_FILTRATION_CONF to a speed label."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_FILTRATION_CONF"] = raw
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    entity_id = _select_entity_id(hass, mock_config_entry, "mbf_par_filtration_speed")
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected


# ---------------------------------------------------------------------------
# timer_time + timer_period + relay_mode dispatch via set_timer service
# ---------------------------------------------------------------------------


async def test_timer_period_select_calls_set_timer_service(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A timer_period select forwards a period in seconds to set_timer."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _select_entity_id(hass, mock_config_entry, "relay_aux1_period")
    mock_neopool_client.write_timer.reset_mock()
    await _select_option(hass, entity_id, "1_week")
    timer_name, payload = mock_neopool_client.write_timer.await_args.args
    assert timer_name == "relay_aux1"
    assert payload["period"] == 604800


async def test_relay_mode_select_calls_set_timer_service(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A relay_mode select writes the enable value through the lib."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _select_entity_id(hass, mock_config_entry, "relay_aux1_mode")
    mock_neopool_client.write_timer.reset_mock()
    await _select_option(hass, entity_id, "auto")
    assert mock_neopool_client.write_timer.await_count == 1
    mock_neopool_client.write_timer.assert_awaited_with("relay_aux1", {"enable": 1})


async def test_relay_mode_manual_to_manual_is_noop(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Selecting 'manual' when the relay already is in a manual state does not write."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.data["relay_aux1_enable"] = 3  # ALWAYS_ON = manual on
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    entity_id = _select_entity_id(hass, mock_config_entry, "relay_aux1_mode")
    mock_neopool_client.write_timer.reset_mock()
    await _select_option(hass, entity_id, "manual")
    assert mock_neopool_client.write_timer.await_count == 0


# ---------------------------------------------------------------------------
# Winter mode guard
# ---------------------------------------------------------------------------


async def test_select_blocked_in_winter_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """async_select_option short-circuits when winter_mode is on."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.winter_mode = True

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("select.")
                and getattr(ent, "key", None) == "MBF_PAR_FILT_MODE"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None

    mock_neopool_client.async_write_register.reset_mock()
    await entity_obj.async_select_option("auto")
    assert "Winter mode is active" in caplog.text
    mock_neopool_client.async_write_register.assert_not_called()


# ---------------------------------------------------------------------------
# Platform-wide snapshots
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("mock_neopool_client")
async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Snapshot every entity registered by the select platform.

    Snapshot the registry entries directly rather than via
    `snapshot_platform`, which assumes every entity is enabled and has
    state. NeoPool ships several `entity_registry_enabled_default=False`
    entities; including them via state lookup would either fail or pull
    entire state machines into the snapshot. The registry entry alone
    (unique_id, name, disabled_by, ...) is the stable shape we care about.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.SELECT]):
        await setup_integration(hass, mock_config_entry)
    entries = sorted(
        er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id),
        key=lambda e: e.entity_id,
    )
    assert entries == snapshot


async def test_setup_when_modules_absent(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client_minimal: MagicMock,
) -> None:
    """Snapshot the select entities registered when no modules are present.

    Drives setup with the lean `mock_neopool_client_minimal` fixture (no
    modules detected, no relay GPIOs assigned). Each platform's gating
    branches fire and entities depending on the missing hardware are
    skipped; the resulting registry shape is captured as a snapshot.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.SELECT]):
        await setup_integration(hass, mock_config_entry)
    entries = sorted(
        er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id),
        key=lambda e: e.entity_id,
    )
    assert entries == snapshot
