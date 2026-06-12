"""Test the NeoPool integration setup and unload."""

from unittest.mock import AsyncMock, MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool.const import CURRENT_VERSION, DOMAIN, REMOVED_ENTITY_KEYS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration

# ---------------------------------------------------------------------------
# Setup / unload (framework path)
# ---------------------------------------------------------------------------


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
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


async def test_setup_in_winter_mode(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
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


async def test_setup_cleans_orphaned_entity_registry_entries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_neopool_client: MagicMock,
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
