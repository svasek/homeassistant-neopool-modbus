"""Tests for the NeoPool button platform."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.neopool.const import DOMAIN
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration
from .conftest import MOCK_POOL_DATA, MOCK_SERIAL


def _button_entity_id(
    hass: HomeAssistant, entry: MockConfigEntry, key_lower: str
) -> str:
    """Resolve a button entity by its trailing unique_id segment."""
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "button" and e.unique_id.endswith(f"_{key_lower}")
    ]
    assert entries, f"no button entity ending in _{key_lower}"
    return entries[0].entity_id


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {"entity_id": entity_id},
        blocking=True,
    )


async def test_sync_time_button_writes_time_and_commit(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """SYNC_TIME button delegates to async_sync_device_time."""
    await setup_integration(hass, mock_config_entry)

    entity_id = _button_entity_id(hass, mock_config_entry, "sync_time")
    mock_neopool_client.async_sync_device_time.reset_mock()
    await _press(hass, entity_id)
    assert mock_neopool_client.async_sync_device_time.await_count == 1


async def test_escape_button_writes_clear_register(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """MBF_ESCAPE button delegates to async_clear_errors."""
    await setup_integration(hass, mock_config_entry)

    entity_id = _button_entity_id(hass, mock_config_entry, "mbf_escape")
    mock_neopool_client.async_clear_errors.reset_mock()
    await _press(hass, entity_id)
    mock_neopool_client.async_clear_errors.assert_awaited_once()


async def test_backwash_button_writes_filt_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """BACKWASH delegates to async_set_filtration_mode("backwash")."""
    await setup_integration(hass, mock_config_entry)

    entity_id = _button_entity_id(hass, mock_config_entry, "backwash")
    mock_neopool_client.async_set_filtration_mode.reset_mock()
    await _press(hass, entity_id)
    mock_neopool_client.async_set_filtration_mode.assert_awaited_once_with("backwash")


async def test_button_press_blocked_in_winter_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """async_press short-circuits when winter_mode is on (entity-method-level guard)."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.winter_mode = True

    # Reach the entity object directly so the unavailable-entity service
    # filter doesn't refuse the dispatch.

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id.startswith("button.") and ent._key == "SYNC_TIME":
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None

    mock_neopool_client.async_sync_device_time.reset_mock()
    await entity_obj.async_press()
    assert "Winter mode is active" in caplog.text
    mock_neopool_client.async_sync_device_time.assert_not_called()


async def test_backwash_button_aborts_when_valve_disappears(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If the valve disappears between setup and press, the press logs and exits."""
    await setup_integration(hass, mock_config_entry)
    entity_id = _button_entity_id(hass, mock_config_entry, "backwash")

    # Drop the filt valve from the next read after the entity is registered.
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_FILTVALVE_GPIO": 0,
        "MBF_PAR_FILTVALVE_ENABLE": 0,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    mock_neopool_client.async_set_filtration_mode.reset_mock()
    await _press(hass, entity_id)
    assert "Backwash valve not configured" in caplog.text
    mock_neopool_client.async_set_filtration_mode.assert_not_called()


async def test_reset_cell_partial_button_writes_reset_and_save(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """RESET_CELL_PARTIAL delegates to async_reset_user_counters."""
    # The reset button is destructive (clears partial counters) so it ships
    # disabled-by-default. Pre-enable it in the registry before setup so the
    # platform constructs the entity object.
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "button",
        DOMAIN,
        f"{MOCK_SERIAL}_reset_cell_partial",
        config_entry=mock_config_entry,
        disabled_by=None,
    )
    await setup_integration(hass, mock_config_entry)

    entity_id = _button_entity_id(hass, mock_config_entry, "reset_cell_partial")
    mock_neopool_client.async_reset_user_counters.reset_mock()
    await _press(hass, entity_id)
    mock_neopool_client.async_reset_user_counters.assert_awaited_once()


@pytest.mark.usefixtures("mock_neopool_client")
async def test_reset_cell_partial_button_disabled_by_default(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reset button registers but is disabled-by-default (destructive action)."""
    await setup_integration(hass, mock_config_entry)

    registry = er.async_get(hass)
    matches = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == "button" and e.unique_id.endswith("_reset_cell_partial")
    ]
    assert len(matches) == 1
    assert matches[0].disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_reset_cell_partial_button_skipped_without_hydrolysis(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """No RESET_CELL_PARTIAL entity is registered when hydrolysis isn't detected."""
    no_hidro_data = dict(mock_neopool_client.async_read_all.return_value)
    no_hidro_data["Hydrolysis module detected"] = False
    mock_neopool_client.async_read_all.return_value = no_hidro_data

    await setup_integration(hass, mock_config_entry)

    registry = er.async_get(hass)
    matches = [
        e
        for e in er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
        if e.domain == "button" and e.unique_id.endswith("_reset_cell_partial")
    ]
    assert matches == []


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
    """Snapshot every entity registered by the button platform.

    Snapshot the registry entries directly rather than via
    `snapshot_platform`, which assumes every entity is enabled and has
    state. NeoPool ships several `entity_registry_enabled_default=False`
    entities; including them via state lookup would either fail or pull
    entire state machines into the snapshot. The registry entry alone
    (unique_id, name, disabled_by, ...) is the stable shape we care about.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.BUTTON]):
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
    """Snapshot the button entities registered when no modules are present.

    Drives setup with the lean `mock_neopool_client_minimal` fixture (no
    modules detected, no relay GPIOs assigned). Each platform's gating
    branches fire and entities depending on the missing hardware are
    skipped; the resulting registry shape is captured as a snapshot.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.BUTTON]):
        await setup_integration(hass, mock_config_entry)
    entries = sorted(
        er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id),
        key=lambda e: e.entity_id,
    )
    assert entries == snapshot
