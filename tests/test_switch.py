"""Tests for the NeoPool switch platform."""

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from neopool_modbus import InvalidStateReason, NeoPoolInvalidStateError
from neopool_modbus.exceptions import NeoPoolConnectionError
from neopool_modbus.registers import (
    BinaryConfigFlag,
    BitmaskConfigFlag,
    RelayKind,
    TimerRelayMode,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.neopool.const import (
    CONF_CAPABILITIES,
    CONF_MODBUS_FRAMER,
    CONF_UNIT_ID,
    CONF_USE_FILTRATION1,
    CONF_WINTER_MODE,
    CURRENT_VERSION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration
from .conftest import MOCK_POOL_DATA


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
    """Manual filtration dispatches to async_set_manual_filtration(state)."""
    mock_neopool_client.async_set_manual_filtration.side_effect = lambda state: {
        "Filtration Pump": state,
        "MBF_PAR_FILT_MANUAL_STATE": int(state),
    }
    await setup_integration(hass, mock_config_entry)

    await _turn_on(hass, "switch.neopool_filtration")
    mock_neopool_client.async_set_manual_filtration.assert_called_with(True)

    mock_neopool_client.async_set_manual_filtration.reset_mock()
    await _turn_off(hass, "switch.neopool_filtration")
    mock_neopool_client.async_set_manual_filtration.assert_called_with(False)


async def test_manual_filtration_turn_on_raises_when_not_manual_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
) -> None:
    """turn_on raises ServiceValidationError when filtration mode is not manual."""
    await setup_integration(hass, mock_config_entry)

    # Push controller into auto mode (FILT_MODE=1).
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILT_MODE": 1,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    mock_neopool_client.async_write_register.reset_mock()
    mock_neopool_client.async_set_manual_filtration.reset_mock()
    with pytest.raises(ServiceValidationError):
        await _turn_on(hass, "switch.neopool_filtration")
    # No write should have happened.
    assert mock_neopool_client.async_write_register.await_count == 0
    assert mock_neopool_client.async_set_manual_filtration.await_count == 0

    with pytest.raises(ServiceValidationError):
        await _turn_off(hass, "switch.neopool_filtration")
    assert mock_neopool_client.async_write_register.await_count == 0
    assert mock_neopool_client.async_set_manual_filtration.await_count == 0


# ---------------------------------------------------------------------------
# winter_mode (no register write, only options change + entity reload)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("mock_neopool_client")
async def test_winter_mode_turn_on_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Toggling winter_mode flips coordinator.winter_mode and writes to entry options."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert coordinator.winter_mode is False

    await _turn_on(hass, "switch.neopool_winter_mode")
    assert coordinator.winter_mode is True

    await _turn_off(hass, "switch.neopool_winter_mode")
    assert coordinator.winter_mode is False


# ---------------------------------------------------------------------------
# auto_time_sync
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("mock_neopool_client")
async def test_auto_time_sync_turn_on_off(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Toggling auto_time_sync flips coordinator.auto_time_sync."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert coordinator.auto_time_sync is False

    await _turn_on(hass, "switch.neopool_time_auto_sync")
    assert coordinator.auto_time_sync is True

    await _turn_off(hass, "switch.neopool_time_auto_sync")
    assert coordinator.auto_time_sync is False


# ---------------------------------------------------------------------------
# Winter-mode guard: turning on/off any IO switch is rejected while winter is active
# ---------------------------------------------------------------------------


async def test_io_switch_unavailable_in_winter_mode(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """IO switches become unavailable while winter mode is active.

    HA's service layer refuses to dispatch to unavailable entities, so the
    availability gate on NeoPoolEntity is what actually blocks IO writes.
    Assert that gate directly on the entity instance.
    """
    entry = MockConfigEntry(
        domain="neopool",
        title="Winter Pool",
        unique_id="neopool_winter_io",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.7",
            "port": 502,
            "name": "Winter Pool",
            CONF_UNIT_ID: 1,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_MODBUS_FRAMER: "tcp",
            CONF_WINTER_MODE: True,
            CONF_USE_FILTRATION1: True,
            CONF_CAPABILITIES: {"MBF_PAR_FILT_GPIO": 1},
        },
    )
    await setup_integration(hass, entry)
    platform = next(
        p for p in ep.async_get_platforms(hass, "neopool") if p.domain == "switch"
    )
    io_entity = next(
        e
        for e in platform.entities.values()
        if getattr(e, "key", None) == "MBF_PAR_FILT_MANUAL_STATE"
    )
    winter_entity = next(
        e
        for e in platform.entities.values()
        if getattr(e, "key", None) == "WINTER_MODE"
    )
    # IO switch inherits the winter-mode availability gate.
    assert io_entity.available is False
    # The winter_mode switch itself must stay available so users can toggle it.
    assert winter_entity.available is True


# ---------------------------------------------------------------------------
# is_on / available, manual_filtration
# ---------------------------------------------------------------------------


async def test_manual_filtration_is_on_reflects_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
) -> None:
    """is_on tracks the "Filtration Pump" relay state, regardless of mode."""
    await setup_integration(hass, mock_config_entry)

    # Pump running: entity is ON.
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILT_MODE": 0,
        "Filtration Pump": True,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get("switch.neopool_filtration")
    assert state is not None
    assert state.state == STATE_ON

    # Pump stopped: entity is OFF (but still available in auto mode).
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILT_MODE": 1,
        "Filtration Pump": False,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get("switch.neopool_filtration")
    assert state is not None
    assert state.state == STATE_OFF


async def test_manual_filtration_is_on_true_when_pump_running_in_auto(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
) -> None:
    """is_on returns True when the pump is running under an automatic schedule."""

    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILT_MODE": 1,  # auto
        "Filtration Pump": True,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("switch.")
                and getattr(ent, "key", None) == "MBF_PAR_FILT_MANUAL_STATE"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None
    assert entity_obj.is_on is True


# ---------------------------------------------------------------------------
# climate_mode / smart_anti_freeze / uv_mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("register_key", "flag"),
    [
        ("MBF_PAR_CLIMA_ONOFF", BinaryConfigFlag.CLIMA_ONOFF),
        ("MBF_PAR_SMART_ANTI_FREEZE", BinaryConfigFlag.SMART_ANTI_FREEZE),
        ("MBF_PAR_UV_MODE", BinaryConfigFlag.UV_MODE),
    ],
    ids=lambda v: v.name if isinstance(v, BinaryConfigFlag) else v,
)
async def test_climate_smart_uv_writes_to_function_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    register_key: str,
    flag: BinaryConfigFlag,
) -> None:
    """The grouped switches dispatch to async_set_binary_flag with their flag."""

    mock_neopool_client.async_set_binary_flag.side_effect = lambda flag, state: {
        register_key: int(state)
    }
    await setup_integration(hass, mock_config_entry)

    # Unique IDs are lower-case slugified by NeoPoolEntity.
    suffix = f"_{register_key.lower()}"
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == SWITCH_DOMAIN and e.unique_id.endswith(suffix)
    ]
    assert entries, (
        f"no switch entity with unique_id ending in {suffix}, found: "
        + ", ".join(
            e.unique_id
            for e in er.async_entries_for_config_entry(
                registry, mock_config_entry.entry_id
            )
            if e.domain == SWITCH_DOMAIN
        )
    )
    entity_id = entries[0].entity_id

    mock_neopool_client.async_set_binary_flag.reset_mock()
    await _turn_on(hass, entity_id)
    mock_neopool_client.async_set_binary_flag.assert_called_with(flag, True)

    mock_neopool_client.async_set_binary_flag.reset_mock()
    await _turn_off(hass, entity_id)
    mock_neopool_client.async_set_binary_flag.assert_called_with(flag, False)


# ---------------------------------------------------------------------------
# aux relay (relay_timer) write paths
# ---------------------------------------------------------------------------


async def test_aux_relay_turn_on_writes_relay_index(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """aux1 turn_on/off dispatches to async_set_relay_state(RelayKind.AUX1, state)."""

    mock_neopool_client.async_set_relay_state.side_effect = lambda relay, state: {
        "AUX1": state
    }
    await setup_integration(hass, mock_config_entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == SWITCH_DOMAIN and e.unique_id.endswith("_aux1")
    ]
    assert entries
    entity_id = entries[0].entity_id

    mock_neopool_client.async_set_relay_state.reset_mock()
    await _turn_on(hass, entity_id)
    mock_neopool_client.async_set_relay_state.assert_called_with(RelayKind.AUX1, True)

    mock_neopool_client.async_set_relay_state.reset_mock()
    await _turn_off(hass, entity_id)
    mock_neopool_client.async_set_relay_state.assert_called_with(RelayKind.AUX1, False)


@pytest.mark.parametrize(
    ("aux_key", "enable_key"),
    [
        ("aux1", "relay_aux1_enable"),
        ("aux2", "relay_aux2_enable"),
        ("aux3", "relay_aux3_enable"),
        ("aux4", "relay_aux4_enable"),
    ],
)
@pytest.mark.parametrize(
    "enable_value",
    [
        pytest.param(TimerRelayMode.ENABLED, id="auto"),
        pytest.param(None, id="missing"),
        pytest.param(0, id="disabled"),
        pytest.param(2, id="unknown-state"),
    ],
)
async def test_aux_relay_turn_on_raises_when_not_in_manual_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
    aux_key: str,
    enable_key: str,
    enable_value: int | None,
) -> None:
    """Aux relay refuses to fire unless the relay is in a manual mode."""
    await setup_integration(hass, mock_config_entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == SWITCH_DOMAIN and e.unique_id.endswith(f"_{aux_key}")
    ]
    assert entries
    entity_id = entries[0].entity_id

    data: dict[str, Any] = {**MOCK_POOL_DATA}
    if enable_value is None:
        data.pop(enable_key, None)
    else:
        data[enable_key] = enable_value
    mock_neopool_client.async_read_all.return_value = data
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    mock_neopool_client.async_set_relay_state.reset_mock()

    with pytest.raises(ServiceValidationError):
        await _turn_on(hass, entity_id)
    with pytest.raises(ServiceValidationError):
        await _turn_off(hass, entity_id)

    # Custom pre-check refuses the write; the lib API is never called.
    mock_neopool_client.async_set_relay_state.assert_not_called()
    assert mock_neopool_client.async_write_register.await_count == 0


async def test_aux_relay_maps_lib_invalid_state_to_service_validation_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Race window: custom guard passes but the lib refuses on write.

    ``coordinator.data`` may lag briefly behind the lib's cache (e.g. a poll
    landed after the pre-check). Remap ``NeoPoolInvalidStateError`` to a
    translated ``ServiceValidationError`` instead of leaking the raw error.
    """
    await setup_integration(hass, mock_config_entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == SWITCH_DOMAIN and e.unique_id.endswith("_aux1")
    ]
    assert entries
    entity_id = entries[0].entity_id

    mock_neopool_client.async_set_relay_state.side_effect = NeoPoolInvalidStateError(
        "relay in auto mode",
        reason=InvalidStateReason.RELAY_IN_AUTO_MODE,
    )

    with pytest.raises(ServiceValidationError) as exc:
        await _turn_on(hass, entity_id)
    assert exc.value.translation_key == "relay_in_auto_mode"


@pytest.mark.parametrize(
    "write_error",
    [
        pytest.param(NeoPoolConnectionError("boom"), id="lib-connection-error"),
        pytest.param(TimeoutError("boom"), id="timeout"),
        pytest.param(OSError("boom"), id="os-error"),
    ],
)
async def test_aux_relay_maps_communication_error_to_home_assistant_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    write_error: Exception,
) -> None:
    """Communication errors on switch write are surfaced as translated HomeAssistantError."""
    await setup_integration(hass, mock_config_entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == SWITCH_DOMAIN and e.unique_id.endswith("_aux1")
    ]
    assert entries
    entity_id = entries[0].entity_id

    mock_neopool_client.async_set_relay_state.side_effect = write_error
    with pytest.raises(HomeAssistantError):
        await _turn_on(hass, entity_id)


async def test_filtration_switch_maps_filtration_reason_to_dedicated_key(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """A FILTRATION_NOT_IN_MANUAL_MODE reason routes to the filtration-specific key."""
    await setup_integration(hass, mock_config_entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == SWITCH_DOMAIN
        and e.unique_id.endswith("_mbf_par_filt_manual_state")
    ]
    assert entries
    entity_id = entries[0].entity_id

    # Bypass the custom pre-check by pretending we are already in manual mode.
    coordinator = mock_config_entry.runtime_data
    coordinator.data["MBF_PAR_FILT_MODE"] = 0
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    mock_neopool_client.async_set_manual_filtration.side_effect = (
        NeoPoolInvalidStateError(
            "not in manual filtration mode",
            reason=InvalidStateReason.FILTRATION_NOT_IN_MANUAL_MODE,
        )
    )

    with pytest.raises(ServiceValidationError) as exc:
        await _turn_on(hass, entity_id)
    assert exc.value.translation_key == "filtration_not_manual_mode"


# ---------------------------------------------------------------------------
# bitmask write paths (MBF_PAR_HIDRO_COVER_ENABLE / MBF_PAR_HIDRO_TEMP_SHUTDOWN)
# ---------------------------------------------------------------------------


async def test_hidro_cover_enable_bitmask_writes_or_pattern(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """The hydro cover-enable bitmask switch dispatches to async_set_bitmask_flag."""

    mock_neopool_client.async_set_bitmask_flag.side_effect = lambda flag, state: {
        "MBF_PAR_HIDRO_COVER_ENABLE": 1 if state else 0
    }
    await setup_integration(hass, mock_config_entry)
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == SWITCH_DOMAIN
        and e.unique_id.endswith("_mbf_par_hidro_cover_enable")
    ]
    if not entries:
        pytest.skip("hidro cover enable switch not registered")
    entity_id = entries[0].entity_id

    mock_neopool_client.async_set_bitmask_flag.reset_mock()
    await _turn_on(hass, entity_id)
    mock_neopool_client.async_set_bitmask_flag.assert_called_with(
        BitmaskConfigFlag.HIDRO_COVER_ENABLE, True
    )

    mock_neopool_client.async_set_bitmask_flag.reset_mock()
    await _turn_off(hass, entity_id)
    mock_neopool_client.async_set_bitmask_flag.assert_called_with(
        BitmaskConfigFlag.HIDRO_COVER_ENABLE, False
    )


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
    """Snapshot every entity registered by the switch platform.

    Snapshot the registry entries directly rather than via
    `snapshot_platform`, which assumes every entity is enabled and has
    state. NeoPool ships several `entity_registry_enabled_default=False`
    entities; including them via state lookup would either fail or pull
    entire state machines into the snapshot. The registry entry alone
    (unique_id, name, disabled_by, ...) is the stable shape we care about.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.SWITCH]):
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
    """Snapshot the switch entities registered when no modules are present.

    Drives setup with the lean `mock_neopool_client_minimal` fixture (no
    modules detected, no relay GPIOs assigned). Each platform's gating
    branches fire and entities depending on the missing hardware are
    skipped; the resulting registry shape is captured as a snapshot.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.SWITCH]):
        await setup_integration(hass, mock_config_entry)
    entries = sorted(
        er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id),
        key=lambda e: e.entity_id,
    )
    assert entries == snapshot
