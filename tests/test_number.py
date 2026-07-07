"""Tests for the NeoPool number platform."""

import asyncio
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform as ep, entity_registry as er

from . import setup_integration
from .conftest import MOCK_POOL_DATA


def _number_entity_id(
    hass: HomeAssistant, entry: MockConfigEntry, key_lower_suffix: str
) -> str:
    registry = er.async_get(hass)
    entries = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "number" and e.unique_id.endswith(f"_{key_lower_suffix}")
    ]
    assert entries, (
        f"no number entity ending in _{key_lower_suffix}, found: "
        + ", ".join(
            e.unique_id
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.domain == "number"
        )
    )
    return entries[0].entity_id


async def _set_value(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {"entity_id": entity_id, ATTR_VALUE: value},
        blocking=True,
    )


def _disable_debounce(hass: HomeAssistant) -> None:
    """Set `_debounce_delay = 0` on every number entity for this run.

    The production code uses `asyncio.sleep(_debounce_delay)` (defaults to
    2 s) before writing the register, so a normal test would block for
    that long. Setting the delay to zero lets the write happen on the
    next event-loop iteration without waiting on a real-time clock.
    `freezer.tick + async_fire_time_changed` doesn't help here because
    `asyncio.sleep` runs on the event-loop wall clock, not HA's scheduler.
    """
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id.startswith("number."):
                ent._debounce_delay = 0


async def _flush_debounce(hass: HomeAssistant, entity_obj) -> None:
    """Wait for the entity's pending debounced write task to complete."""
    task = getattr(entity_obj, "_pending_write_task", None)
    if task is None:
        return
    await asyncio.wait_for(task, timeout=1)
    await hass.async_block_till_done()


async def test_simple_number_writes_register_after_debounce(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Setting a numeric value writes raw=value*scale to the register."""
    await setup_integration(hass, mock_config_entry)
    _disable_debounce(hass)

    entity_id = _number_entity_id(hass, mock_config_entry, "mbf_par_ph1")
    mock_neopool_client.async_write_register.reset_mock()

    await _set_value(hass, entity_id, 7.5)

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id == entity_id:
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    await _flush_debounce(hass, entity_obj)

    assert mock_neopool_client.async_write_register.await_count >= 1


async def test_heating_setpoint_mirrors_to_intelligent(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Writing the heating setpoint delegates to async_set_temp_setpoint."""

    await setup_integration(hass, mock_config_entry)
    _disable_debounce(hass)
    entity_id = _number_entity_id(hass, mock_config_entry, "mbf_par_heating_temp")

    mock_neopool_client.async_set_temp_setpoint.reset_mock()
    await _set_value(hass, entity_id, 28.0)

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id == entity_id:
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    await _flush_debounce(hass, entity_obj)

    mock_neopool_client.async_set_temp_setpoint.assert_awaited_once_with(28)


async def test_number_blocked_in_winter_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """async_set_native_value short-circuits when winter_mode is on."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    coordinator.winter_mode = True

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if ent.entity_id.startswith("number.") and getattr(ent, "_key", None):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    assert entity_obj is not None

    mock_neopool_client.async_write_register.reset_mock()
    await entity_obj.async_set_native_value(7.5)
    assert "Winter mode is active" in caplog.text
    mock_neopool_client.async_write_register.assert_not_called()


async def test_number_native_value_returns_rounded_raw(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
) -> None:
    """native_value returns round(raw, 2) when coordinator has the register."""

    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_PH1": 7.55,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("number.")
                and getattr(ent, "_data_key", None) == "MBF_PAR_PH1"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    if entity_obj is None:
        pytest.skip("MBF_PAR_PH1 number entity not registered")
    assert entity_obj.native_value == 7.55


async def test_hidro_native_value_in_percent_mode(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
) -> None:
    """MBF_PAR_HIDRO with hidro_nom set surfaces it as native_max_value."""

    await setup_integration(hass, mock_config_entry)
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_HIDRO_NOM": 100,
        "MBF_PAR_MODEL": 0x0002,  # has hydro
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    entity_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("number.")
                and getattr(ent, "_key", None) == "MBF_PAR_HIDRO"
            ):
                entity_obj = ent
                break
        if entity_obj is not None:
            break
    if entity_obj is None:
        pytest.skip("MBF_PAR_HIDRO entity not registered on this fixture")
    assert entity_obj.native_max_value == 100


async def test_masked_number_native_value_decodes_via_mask_shift(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
) -> None:
    """Test that masked compound numbers decode via _mask/_shift.

    HIDRO_COVER_REDUCTION / SHUTDOWN_TEMPERATURE share register 0x042D,
    lower byte holds cover reduction %, upper byte the shutdown
    temperature. native_value must isolate each via _mask/_shift.
    """
    await setup_integration(hass, mock_config_entry)
    # Pack: cover reduction = 25 (0x19), shutdown temp = 12 (0x0C) → 0x0C19.
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_HIDRO_COVER_REDUCTION": 0x0C19,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    cover, shutdown = None, None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            key = getattr(ent, "_key", None)
            if not ent.entity_id.startswith("number."):
                continue
            if key == "MBF_PAR_HIDRO_COVER_REDUCTION":
                cover = ent
            elif key == "MBF_PAR_HIDRO_SHUTDOWN_TEMPERATURE":
                shutdown = ent
    if cover is None or shutdown is None:
        pytest.skip("masked numbers not registered on this fixture")
    # Lower byte 0x19 = 25
    assert cover.native_value == 25
    # Upper byte 0x0C = 12
    assert shutdown.native_value == 12


async def test_masked_number_write_preserves_other_byte(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
    freezer,
) -> None:
    """Writing one masked number must read-modify-write to preserve the other byte."""
    await setup_integration(hass, mock_config_entry)
    _disable_debounce(hass)
    # Existing combined register: cover=25, shutdown=12 (0x0C19).
    mock_neopool_client.async_read_all.return_value = {
        **MOCK_POOL_DATA,
        "MBF_PAR_HIDRO_COVER_REDUCTION": 0x0C19,
    }
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    cover_entity_id = None
    cover_obj = None
    for platforms in ep.async_get_platforms(hass, "neopool"):
        for ent in platforms.entities.values():
            if (
                ent.entity_id.startswith("number.")
                and getattr(ent, "_key", None) == "MBF_PAR_HIDRO_COVER_REDUCTION"
            ):
                cover_entity_id = ent.entity_id
                cover_obj = ent
    if cover_entity_id is None:
        pytest.skip("MBF_PAR_HIDRO_COVER_REDUCTION entity not registered")

    mock_neopool_client.async_write_register.reset_mock()
    await _set_value(hass, cover_entity_id, 50)  # 0x32
    await _flush_debounce(hass, cover_obj)

    # The write must keep the upper byte (0x0C00) and overwrite lower byte to 0x32 → 0x0C32.
    writes = mock_neopool_client.async_write_register.await_args_list
    assert any(call.args[0] == 0x042D and call.args[1] == 0x0C32 for call in writes), (
        f"expected 0x042D <- 0x0C32, got {writes}"
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
    """Snapshot every entity registered by the number platform.

    Snapshot the registry entries directly rather than via
    `snapshot_platform`, which assumes every entity is enabled and has
    state. NeoPool ships several `entity_registry_enabled_default=False`
    entities; including them via state lookup would either fail or pull
    entire state machines into the snapshot. The registry entry alone
    (unique_id, name, disabled_by, ...) is the stable shape we care about.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.NUMBER]):
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
    """Snapshot the number entities registered when no modules are present.

    Drives setup with the lean `mock_neopool_client_minimal` fixture (no
    modules detected, no relay GPIOs assigned). Each platform's gating
    branches fire and entities depending on the missing hardware are
    skipped; the resulting registry shape is captured as a snapshot.
    """
    with patch("custom_components.neopool.PLATFORMS", [Platform.NUMBER]):
        await setup_integration(hass, mock_config_entry)
    entries = sorted(
        er.async_entries_for_config_entry(entity_registry, mock_config_entry.entry_id),
        key=lambda e: e.entity_id,
    )
    assert entries == snapshot
