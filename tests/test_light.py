"""Tests for the NeoPool light platform."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from neopool_modbus import NeoPoolInvalidStateError
from neopool_modbus.registers import RelayKind, TimerRelayMode
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
    """Light on/off delegates to the high-level async_set_relay_state API."""

    await setup_integration(hass, mock_config_entry)
    entity_id = _light_entity_id(hass, mock_config_entry)

    # Stub the high-level relay setter to return an optimistic-update dict
    # (light.py merges it into coordinator.data via ``data.update(overrides)``).
    mock_neopool_client.async_set_relay_state = AsyncMock(
        return_value={"Pool Light": True}
    )

    await _turn_on(hass, entity_id)

    mock_neopool_client.async_set_relay_state.assert_awaited_once_with(
        RelayKind.LIGHT, True
    )
    coordinator = mock_config_entry.runtime_data
    assert coordinator.data.get("Pool Light") is True

    mock_neopool_client.async_set_relay_state = AsyncMock(
        return_value={"Pool Light": False}
    )
    await _turn_off(hass, entity_id)

    mock_neopool_client.async_set_relay_state.assert_awaited_once_with(
        RelayKind.LIGHT, False
    )
    assert coordinator.data.get("Pool Light") is False


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
        "relay_light_enable": TimerRelayMode.ALWAYS_ON,
        "Pool Light": True,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON

    # Manual off: relay inactive.
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "relay_light_enable": TimerRelayMode.ALWAYS_OFF,
        "Pool Light": False,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_OFF

    # Auto mode with relay currently energized: entity is ON (real state).
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "relay_light_enable": TimerRelayMode.ENABLED,
        "Pool Light": True,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON


@pytest.mark.parametrize(
    "enable_value",
    [
        pytest.param(TimerRelayMode.ENABLED, id="auto"),
        pytest.param(None, id="missing"),
        pytest.param(0, id="disabled"),
        pytest.param(2, id="unknown-state"),
    ],
)
async def test_light_turn_on_raises_when_not_in_manual_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
    enable_value: int | None,
) -> None:
    """Light refuses to fire unless the relay is in a manual mode."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _light_entity_id(hass, mock_config_entry)

    data = {**MOCK_POOL_DATA}
    if enable_value is None:
        data.pop("relay_light_enable", None)
    else:
        data["relay_light_enable"] = enable_value
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


async def test_light_turn_on_maps_lib_invalid_state_to_service_validation_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Race window: custom guard sees manual but the lib sees AUTO and refuses.

    ``coordinator.data`` may lag briefly behind the lib's internal cache
    (e.g. a poll landed between the custom pre-check and the write). If the
    lib raises ``NeoPoolInvalidStateError``, the light platform remaps it to
    a translated ``ServiceValidationError`` instead of leaking the raw error.
    """
    await setup_integration(hass, mock_config_entry)
    entity_id = _light_entity_id(hass, mock_config_entry)

    mock_neopool_client.async_set_relay_state = AsyncMock(
        side_effect=NeoPoolInvalidStateError("relay in auto mode")
    )

    with pytest.raises(ServiceValidationError):
        await _turn_on(hass, entity_id)
    mock_neopool_client.async_set_relay_state.assert_awaited_once_with(
        RelayKind.LIGHT, True
    )


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


@pytest.mark.usefixtures("mock_neopool_client")
async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
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
