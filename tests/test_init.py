"""Test the NeoPool integration setup and unload."""

from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neopool import async_migrate_entry
from custom_components.neopool.const import (
    CURRENT_VERSION,
    DEFAULT_PORT,
    DOMAIN,
    REMOVED_ENTITY_KEYS,
)
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


# ---------------------------------------------------------------------------
# async_migrate_entry — version transitions
#
# These tests drive the migration helper directly with MagicMock(hass) so
# they cover branches the framework path doesn't reach in a single hass
# run (rollback failures, duplicate detection, version-bump-only paths).
# ---------------------------------------------------------------------------


DEFAULT_SERIAL_REGS = [0x0000, 0x0001, 0x00AC, 0x00CD, 0x0012, 0x0034]
DEFAULT_SERIAL_STRING = "".join(f"{r:04X}" for r in DEFAULT_SERIAL_REGS)


async def test_async_migrate_entry_v1_to_v2_success() -> None:
    """Test migration from v1 (no unique_id) to v2 (serial-based unique_id)."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_123"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    hass.config_entries.async_entries.return_value = []

    mock_entity1 = MagicMock()
    mock_entity1.unique_id = "old_entry_id_123_mbf_ph_measure"
    mock_entity1.entity_id = "sensor.pool_ph"

    mock_entity2 = MagicMock()
    mock_entity2.unique_id = "old_entry_id_123_mbf_temperature"
    mock_entity2.entity_id = "sensor.pool_temperature"

    mock_entity_registry = MagicMock()
    mock_entity_registry.async_update_entity = MagicMock()

    mock_old_device = MagicMock()
    mock_old_device.id = "old_device_id"
    mock_device_registry = MagicMock()
    mock_device_registry.async_get_device.return_value = mock_old_device

    # Simulate HA's behavior: async_update_entry mutates entry.version so the
    # subsequent v3→v4 marker bump can see the post-v2 state of the entry.
    def _apply_update(entry, **kwargs):
        for key, value in kwargs.items():
            setattr(entry, key, value)

    hass.config_entries.async_update_entry.side_effect = _apply_update

    expected_unique_id = f"neopool_{DEFAULT_SERIAL_STRING}"

    with (
        patch(
            "custom_components.neopool.migration.async_get_device_serial",
            new=AsyncMock(return_value=DEFAULT_SERIAL_STRING),
        ),
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=mock_entity_registry,
        ),
        patch(
            "custom_components.neopool.migration.er.async_entries_for_config_entry",
            return_value=[mock_entity1, mock_entity2],
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=mock_device_registry,
        ),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    # async_migrate_entry only performs the v1 → v2 step here (unique_id +
    # version=2). The v3 → v4 marker bump is gated on `version == 3`, which
    # this neopool entry never reaches via HA-driven migration alone — that
    # transition is owned by the cross-domain pipeline (vistapool v2 →
    # neopool v3) and only then does async_migrate_entry pick up the bump.
    assert hass.config_entries.async_update_entry.call_count == 1
    hass.config_entries.async_update_entry.assert_called_once_with(
        config_entry, unique_id=expected_unique_id, version=2
    )
    assert mock_entity_registry.async_update_entity.call_count == 2
    mock_entity_registry.async_update_entity.assert_any_call(
        "sensor.pool_ph",
        new_unique_id=f"{expected_unique_id}_mbf_ph_measure",
    )
    mock_entity_registry.async_update_entity.assert_any_call(
        "sensor.pool_temperature",
        new_unique_id=f"{expected_unique_id}_mbf_temperature",
    )
    # Old device identifier is keyed by the current DOMAIN ("neopool")
    # because async_migrate_entry uses source_domain=DOMAIN by default;
    # legacy vistapool entries reach this code path via the cross-domain
    # migration flow which passes source_domain="vistapool" explicitly.
    mock_device_registry.async_get_device.assert_called_once_with(
        identifiers={("neopool", "old_entry_id_123")}
    )
    mock_device_registry.async_update_device.assert_called_once_with(
        "old_device_id",
        new_identifiers={("neopool", expected_unique_id)},
    )


async def test_async_migrate_entry_v1_to_v2_serial_unavailable() -> None:
    """Test migration defers when serial cannot be read (retries on next restart)."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_456"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    with patch(
        "custom_components.neopool.migration.async_get_device_serial",
        new=AsyncMock(return_value=None),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    # Version must NOT be bumped — migration will retry on next HA restart
    hass.config_entries.async_update_entry.assert_not_called()


async def test_async_migrate_entry_v3_to_v4_marker_bump() -> None:
    """Test that a v3 entry is bumped to v4 (the neopool-modbus library marker).

    v3 entries are produced by the cross-domain pipeline (vistapool v2 →
    neopool v3 rename). HA picks up the resulting entry, sees its stored
    version differs from ConfigFlow.VERSION (=CURRENT_VERSION=4) and
    dispatches to async_migrate_entry, which performs the trivial
    ``version=4`` write — no data shape change, no serial read, no
    entity_registry walk.
    """
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "neopool_entry_v3"
    config_entry.unique_id = "neopool_AABBCCDD11223344EEFF0011"
    config_entry.version = 3
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    result = await async_migrate_entry(hass, config_entry)

    assert result is True
    # The v1→v2 prelude is gated on `version < 2` and must not run on a v3
    # entry — no serial probe, no entity walk, just the marker bump.
    hass.config_entries.async_update_entry.assert_called_once_with(
        config_entry, version=4
    )


async def test_async_migrate_entry_already_at_current_version_is_noop() -> None:
    """Test that calling async_migrate_entry on a v4 entry does nothing.

    HA may invoke this function on every setup whose stored version
    differs from ConfigFlow.VERSION. Once entries reach CURRENT_VERSION
    that should never happen, but guarding the function makes it robust
    against unexpected dispatches and prevents stale "Migrating … from
    v4 to v2" log noise.
    """
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "neopool_entry_v4"
    config_entry.unique_id = "neopool_AABBCCDD11223344EEFF0011"
    config_entry.version = 4
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    result = await async_migrate_entry(hass, config_entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_not_called()


async def test_async_migrate_entry_v1_to_v2_duplicate_detected() -> None:
    """Test migration fails when another entry already has the same serial."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "entry_aaa"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    existing_entry = MagicMock()
    existing_entry.entry_id = "entry_bbb"
    existing_entry.unique_id = f"neopool_{DEFAULT_SERIAL_STRING}"
    hass.config_entries.async_entries.return_value = [existing_entry]

    with patch(
        "custom_components.neopool.migration.async_get_device_serial",
        new=AsyncMock(return_value=DEFAULT_SERIAL_STRING),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is False
    hass.config_entries.async_update_entry.assert_not_called()


async def test_async_migrate_entry_entity_update_error() -> None:
    """Test migration rolls back and defers when entity update fails."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_789"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    hass.config_entries.async_entries.return_value = []

    # First entity will succeed, second will fail → first must be rolled back
    mock_entity1 = MagicMock()
    mock_entity1.unique_id = "old_entry_id_789_mbf_ph_measure"
    mock_entity1.entity_id = "sensor.pool_ph"

    mock_entity2 = MagicMock()
    mock_entity2.unique_id = "old_entry_id_789_mbf_temperature"
    mock_entity2.entity_id = "sensor.pool_temperature"

    call_count = 0

    def update_side_effect(entity_id, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call (entity1 migration) succeeds
        # Second call (entity2 migration) fails
        # Third call (entity1 rollback) succeeds
        if call_count == 2:
            raise ValueError("registry conflict")

    mock_registry = MagicMock()
    mock_registry.async_update_entity.side_effect = update_side_effect

    with (
        patch(
            "custom_components.neopool.migration.async_get_device_serial",
            new=AsyncMock(return_value=DEFAULT_SERIAL_STRING),
        ),
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=mock_registry,
        ),
        patch(
            "custom_components.neopool.migration.er.async_entries_for_config_entry",
            return_value=[mock_entity1, mock_entity2],
        ),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    # 3 calls: migrate entity1 (ok), migrate entity2 (fail), rollback entity1
    assert mock_registry.async_update_entity.call_count == 3
    # Verify rollback call restored entity1's original unique_id
    mock_registry.async_update_entity.assert_any_call(
        "sensor.pool_ph",
        new_unique_id="old_entry_id_789_mbf_ph_measure",
    )
    # Version must NOT be bumped — migration will retry on next HA restart
    hass.config_entries.async_update_entry.assert_not_called()


async def test_async_migrate_entry_rollback_also_fails() -> None:
    """Test migration returns False when rollback fails to prevent duplicates."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_789"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 1}

    hass.config_entries.async_entries.return_value = []

    mock_entity1 = MagicMock()
    mock_entity1.unique_id = "old_entry_id_789_mbf_ph_measure"
    mock_entity1.entity_id = "sensor.pool_ph"

    mock_entity2 = MagicMock()
    mock_entity2.unique_id = "old_entry_id_789_mbf_temperature"
    mock_entity2.entity_id = "sensor.pool_temperature"

    call_count = 0

    def update_side_effect(entity_id, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            # entity2 migration fails, then entity1 rollback also fails
            raise ValueError("registry conflict")

    mock_registry = MagicMock()
    mock_registry.async_update_entity.side_effect = update_side_effect

    with (
        patch(
            "custom_components.neopool.migration.async_get_device_serial",
            new=AsyncMock(return_value=DEFAULT_SERIAL_STRING),
        ),
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=mock_registry,
        ),
        patch(
            "custom_components.neopool.migration.er.async_entries_for_config_entry",
            return_value=[mock_entity1, mock_entity2],
        ),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is False
    # 3 calls: migrate entity1 (ok), migrate entity2 (fail), rollback entity1 (fail)
    assert mock_registry.async_update_entity.call_count == 3
    hass.config_entries.async_update_entry.assert_not_called()


# ---------------------------------------------------------------------------
# Legacy data → options migration (custom-only; runs on async_setup_entry)
# ---------------------------------------------------------------------------


async def test_legacy_data_to_options_migration(
    hass: HomeAssistant,
    mock_neopool_client: MagicMock,
) -> None:
    """Pre-v1.x entries kept user options inside `data` — async_setup_entry
    moves every non-connection key from data to options on first load.
    """
    legacy_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Legacy Pool",
        unique_id="neopool_legacy_options",
        version=CURRENT_VERSION,
        data={
            "host": "192.0.2.40",
            "port": 502,
            "name": "Legacy Pool",
            "slave_id": 1,
            # Old-style: framer + use_* sat in data
            "modbus_framer": "tcp",
            "use_filtration1": True,
            "use_light": True,
        },
        options={},  # empty → migration triggers
    )
    await setup_integration(hass, legacy_entry)

    # use_* keys must have been promoted to options.
    assert legacy_entry.options.get("use_filtration1") is True
    assert legacy_entry.options.get("use_light") is True
    assert legacy_entry.options.get("modbus_framer") == "tcp"
