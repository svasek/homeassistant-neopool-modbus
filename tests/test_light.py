"""Tests for the NeoPool light platform."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from neopool_modbus.registers import LIGHT_FUNCTION_REGISTER, LIGHT_TIMER_BLOCK_REGISTER
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration
from .conftest import MOCK_POOL_DATA


def _light_entity_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "light"
    ]
    assert entries, "expected exactly one neopool light entity"
    return entries[0].entity_id


async def _turn_on(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {"entity_id": entity_id},
        blocking=True,
    )


async def _turn_off(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {"entity_id": entity_id},
        blocking=True,
    )


async def test_light_turn_on_off_writes_to_relay_timer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Light on/off writes to the configured timer block plus the EXEC commit."""

    await setup_integration(hass, mock_config_entry)
    entity_id = _light_entity_id(hass, mock_config_entry)

    timer_block = LIGHT_TIMER_BLOCK_REGISTER
    function_addr = LIGHT_FUNCTION_REGISTER

    mock_neopool_client.async_write_register.reset_mock()
    await _turn_on(hass, entity_id)

    # Three writes for ON: function_addr, timer_block (3 = always ON), EXEC
    addresses_on = [
        c.args[0] for c in mock_neopool_client.async_write_register.await_args_list
    ]
    assert function_addr in addresses_on
    assert timer_block in addresses_on
    # EXEC_REGISTER write at the end
    write_calls = mock_neopool_client.async_write_register.await_args_list
    assert any(c.args[0] == timer_block and c.args[1] == 3 for c in write_calls), (
        f"expected timer_block write with value 3, got {write_calls}"
    )

    mock_neopool_client.async_write_register.reset_mock()
    await _turn_off(hass, entity_id)
    write_calls_off = mock_neopool_client.async_write_register.await_args_list
    assert any(c.args[0] == timer_block and c.args[1] == 4 for c in write_calls_off), (
        f"expected timer_block write with value 4, got {write_calls_off}"
    )


async def test_light_is_on_reflects_relay_enable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
) -> None:
    """is_on tracks the "Pool Light" relay state, regardless of mode."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _light_entity_id(hass, mock_config_entry)

    # Manual on: relay active.
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "relay_light_enable": 3,
        "Pool Light": True,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON

    # Manual off: relay inactive.
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "relay_light_enable": 4,
        "Pool Light": False,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_OFF

    # Auto mode with relay currently energized: entity is ON (real state).
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "relay_light_enable": 1,
        "Pool Light": True,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON


async def test_light_turn_on_raises_when_in_auto_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
) -> None:
    """Toggling the light while its relay is in auto mode raises ServiceValidationError."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _light_entity_id(hass, mock_config_entry)

    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "relay_light_enable": 1,  # auto
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    mock_neopool_client.async_write_register.reset_mock()
    with pytest.raises(ServiceValidationError):
        await _turn_on(hass, entity_id)
    assert mock_neopool_client.async_write_register.await_count == 0
    with pytest.raises(ServiceValidationError):
        await _turn_off(hass, entity_id)
    assert mock_neopool_client.async_write_register.await_count == 0


async def test_light_winter_mode_guard_when_called_directly(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """async_turn_on/off short-circuits when winter_mode is on.

    Service-call layer would normally refuse to dispatch to an unavailable
    entity; we drive the entity method directly to cover the early-exit
    branch in the platform code.
    """
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.winter_mode = True

    entity_id = _light_entity_id(hass, mock_config_entry)
    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id == entity_id:
                entity_obj = ent
                break
        if entity_obj is not None:
            break

    assert entity_obj is not None
    mock_neopool_client.async_write_register.reset_mock()
    await entity_obj.async_turn_on()
    await entity_obj.async_turn_off()
    assert "Winter mode is active" in caplog.text
    mock_neopool_client.async_write_register.assert_not_called()


# ---------------------------------------------------------------------------
# Platform-wide snapshots
# ---------------------------------------------------------------------------


async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Snapshot every entity registered by the light platform.

    Snapshot the registry entries directly rather than via
    `snapshot_platform`, which assumes every entity is enabled and has
    state. NeoPool ships several `entity_registry_enabled_default=False`
    entities; including them via state lookup would either fail or pull
    entire state machines into the snapshot. The registry entry alone
    (unique_id, name, disabled_by, ...) is the stable shape we care about.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.LIGHT]):
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
    """Snapshot the light entities registered when no modules are present.

    Drives setup with the lean `mock_neopool_client_minimal` fixture (no
    modules detected, no relay GPIOs assigned). Each platform's gating
    branches fire and entities depending on the missing hardware are
    skipped; the resulting registry shape is captured as a snapshot.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.LIGHT]):
        await setup_integration(hass, mock_config_entry)
    entries = sorted(
        er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id),
        key=lambda e: e.entity_id,
    )
    assert entries == snapshot
