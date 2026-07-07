"""Test the NeoPool integration setup and unload."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool.const import (
    CONF_CAPABILITIES,
    CONF_MODBUS_FRAMER,
    CONF_UNIT_ID,
    CONF_WINTER_MODE,
    CURRENT_VERSION,
    DOMAIN,
)

# CUSTOM-ONLY START
from custom_components.neopool.migration import REMOVED_ENTITY_KEYS

# CUSTOM-ONLY END
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration

# ---------------------------------------------------------------------------
# Setup / unload (framework path)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("mock_neopool_client")
async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Set up the integration end-to-end and tear it down again."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_first_refresh_fails_marks_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
) -> None:
    """Setup re-tries when the first Modbus read raises."""
    mock_neopool_client.async_read_all = AsyncMock(
        side_effect=ConnectionError("Modbus down")
    )
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.usefixtures("mock_neopool_client")
async def test_setup_in_winter_mode(
    hass: HomeAssistant,
) -> None:
    """Winter mode loads the entry from the persisted capability snapshot.

    The integration must finish setup successfully even though the
    coordinator's update path skips the actual Modbus read in winter mode.
    """
    snapshot = {"MBF_PAR_FILT_GPIO": 0, "MBF_PAR_LIGHTING_GPIO": 0}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Winter Pool",
        unique_id="neopool_winter_serial",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.2",
            "port": 502,
            "name": "Winter Pool",
            CONF_UNIT_ID: 1,
            CONF_MODBUS_FRAMER: "tcp",
        },
        options={
            CONF_MODBUS_FRAMER: "tcp",
            CONF_WINTER_MODE: True,
            CONF_CAPABILITIES: snapshot,
        },
    )
    await setup_integration(hass, entry)
    assert entry.state is ConfigEntryState.LOADED


# CUSTOM-ONLY START, legacy v1→v4 migration cleanup tests (migration is HACS-only).
@pytest.mark.usefixtures("mock_neopool_client")
async def test_setup_cleans_orphaned_entity_registry_entries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Orphaned entries (matching REMOVED_ENTITY_KEYS) are wiped on setup."""

    mock_config_entry.add_to_hass(hass)

    # Pre-create an entity registry entry that matches the orphan pattern.
    # The cleanup logic matches "{prefix}_{key}" where prefix is entry.entry_id
    # or entry.unique_id.
    registry = er.async_get(hass)
    orphan_uid = f"{mock_config_entry.unique_id}_{REMOVED_ENTITY_KEYS[0]}"
    orphan = registry.async_get_or_create(
        "sensor", "neopool", orphan_uid, config_entry=mock_config_entry
    )
    assert registry.async_get(orphan.entity_id) is not None

    # Setting up the entry runs _cleanup_removed_entities which should
    # delete the orphan.
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(orphan.entity_id) is None


@pytest.mark.usefixtures("mock_neopool_client")
async def test_setup_cleans_legacy_select_timer_rows(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Legacy select.X_start/stop rows are removed after time-platform move.

    New time.X_start/stop siblings (sharing unique_id) survive because
    the wildcard is scoped to the select domain.
    """
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    # Legacy select row that should be wiped (matches "select.filtration*_start").
    legacy_uid = f"{mock_config_entry.unique_id}_filtration1_start"
    legacy = registry.async_get_or_create(
        "select", "neopool", legacy_uid, config_entry=mock_config_entry
    )
    legacy_entity_id = legacy.entity_id

    # Same unique_id under the time domain, must NOT be removed.
    sibling = registry.async_get_or_create(
        "time", "neopool", legacy_uid, config_entry=mock_config_entry
    )
    sibling_entity_id = sibling.entity_id

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(legacy_entity_id) is None
    assert registry.async_get(sibling_entity_id) is not None


@pytest.mark.usefixtures("mock_neopool_client")
async def test_setup_does_not_touch_unrelated_select_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The select wildcards target only ``*_start`` / ``*_stop`` keys.

    A bystander like ``select.filtration_mode`` or ``select.relay_aux1_period``
    must remain untouched even though it lives under the same domain.
    """
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    bystander_uid = f"{mock_config_entry.unique_id}_relay_aux1_period"
    bystander = registry.async_get_or_create(
        "select", "neopool", bystander_uid, config_entry=mock_config_entry
    )
    bystander_entity_id = bystander.entity_id

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # The bystander row may have been re-registered by the platform during
    # setup, but it must still exist under its original entity_id.
    assert registry.async_get(bystander_entity_id) is not None


@pytest.mark.usefixtures("mock_neopool_client")
async def test_setup_renames_legacy_low_flow_unique_ids(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """v3.x -> v4.0.0 rename: `... low flow` unique_ids gain the shorter `... low` suffix."""
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    legacy_uid = f"{mock_config_entry.unique_id}_hidro low flow"
    legacy = registry.async_get_or_create(
        "binary_sensor", "neopool", legacy_uid, config_entry=mock_config_entry
    )
    legacy_entity_id = legacy.entity_id

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    renamed = registry.async_get(legacy_entity_id)
    assert renamed is not None
    assert renamed.unique_id == f"{mock_config_entry.unique_id}_hidro low"


@pytest.mark.usefixtures("mock_neopool_client")
async def test_setup_rename_sweep_is_idempotent(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A second setup finds the new unique_id already present and is a no-op."""
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    new_uid = f"{mock_config_entry.unique_id}_ion low"
    entry = registry.async_get_or_create(
        "binary_sensor", "neopool", new_uid, config_entry=mock_config_entry
    )
    original_entity_id = entry.entity_id

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    still_there = registry.async_get(original_entity_id)
    assert still_there is not None
    assert still_there.unique_id == new_uid


@pytest.mark.usefixtures("mock_neopool_client")
async def test_setup_rename_drops_legacy_on_unique_id_collision(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Legacy row is removed instead of crashing when the target unique_id already exists."""
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)

    legacy_uid = f"{mock_config_entry.unique_id}_hidro low flow"
    new_uid = f"{mock_config_entry.unique_id}_hidro low"
    legacy = registry.async_get_or_create(
        "binary_sensor", "neopool", legacy_uid, config_entry=mock_config_entry
    )
    new_entry = registry.async_get_or_create(
        "binary_sensor", "neopool", new_uid, config_entry=mock_config_entry
    )
    legacy_entity_id = legacy.entity_id
    new_entity_id = new_entry.entity_id

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(legacy_entity_id) is None
    still_there = registry.async_get(new_entity_id)
    assert still_there is not None
    assert still_there.unique_id == new_uid
    assert "already exists" in caplog.text


# CUSTOM-ONLY END
