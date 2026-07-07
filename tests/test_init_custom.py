"""HACS-only init tests, version migrations.

These cover behaviour that has no counterpart in the core integration:
``async_migrate_entry`` was added to bridge v1 (no ``unique_id``) → v2
(serial-based ``unique_id``) → v3 (vistapool→neopool rename) → v4 (the
``neopool-modbus`` library marker bump) → v5 (slave_id → unit_id rename).

Core ships fresh entries at v1 with no migration story, the sync
script excludes this whole file via ``EXCLUDE_TEST_FILES``.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from neopool_modbus.exceptions import NeoPoolError

from custom_components.neopool import async_migrate_entry
from custom_components.neopool.const import CONF_UNIT_ID, DEFAULT_PORT, DOMAIN

# ---------------------------------------------------------------------------
# async_migrate_entry, version transitions
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
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

    hass.config_entries.async_entries.return_value = []

    mock_entity1 = MagicMock()
    mock_entity1.unique_id = "old_entry_id_123_mbf_ph_measure"
    mock_entity1.entity_id = "sensor.neopool_ph"

    mock_entity2 = MagicMock()
    mock_entity2.unique_id = "old_entry_id_123_mbf_temperature"
    mock_entity2.entity_id = "sensor.neopool_temperature"

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

    expected_unique_id = DEFAULT_SERIAL_STRING

    with (
        patch(
            "custom_components.neopool.migration.async_probe_serial",
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
    # this neopool entry never reaches via HA-driven migration alone, that
    # transition is owned by the cross-domain pipeline (vistapool v2 →
    # neopool v3) and only then does async_migrate_entry pick up the bump.
    assert hass.config_entries.async_update_entry.call_count == 1
    hass.config_entries.async_update_entry.assert_called_once_with(
        config_entry, unique_id=expected_unique_id, version=2
    )
    assert mock_entity_registry.async_update_entity.call_count == 2
    mock_entity_registry.async_update_entity.assert_any_call(
        "sensor.neopool_ph",
        new_unique_id=f"{expected_unique_id}_mbf_ph_measure",
    )
    mock_entity_registry.async_update_entity.assert_any_call(
        "sensor.neopool_temperature",
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
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

    with patch(
        "custom_components.neopool.migration.async_probe_serial",
        new=AsyncMock(return_value=None),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    # Version must NOT be bumped, migration will retry on next HA restart
    hass.config_entries.async_update_entry.assert_not_called()


async def test_async_migrate_entry_v1_to_v2_probe_raises_neopool_error() -> None:
    """A NeoPoolError from the lib probe is swallowed and the migration defers."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_789"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

    with patch(
        "custom_components.neopool.migration.async_probe_serial",
        new=AsyncMock(side_effect=NeoPoolError("connection refused")),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_not_called()


async def test_async_migrate_entry_v3_to_v4_marker_bump() -> None:
    """Test that a v3 entry is bumped through v4, v5 and v6.

    v3 entries are produced by the cross-domain pipeline (vistapool v2 →
    neopool v3 rename). HA picks up the resulting entry, sees its stored
    version differs from ConfigFlow.VERSION (=CURRENT_VERSION=6) and
    dispatches to async_migrate_entry, which bumps v3→v4 → v5 → v6.
    """
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "neopool_entry_v3"
    config_entry.unique_id = "neopool_AABBCCDD11223344EEFF0011"
    config_entry.version = 3
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

    def _update_entry(entry: MagicMock, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if k == "data":
                entry.data = v
            else:
                setattr(entry, k, v)

    hass.config_entries.async_update_entry.side_effect = _update_entry
    hass.config_entries.async_entries.return_value = [config_entry]

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.neopool.migration.er.async_entries_for_config_entry",
            return_value=[],
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=MagicMock(async_get_device=MagicMock(return_value=None)),
        ),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    assert hass.config_entries.async_update_entry.call_count == 3
    hass.config_entries.async_update_entry.assert_any_call(config_entry, version=4)
    hass.config_entries.async_update_entry.assert_any_call(
        config_entry,
        data={"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1},
        version=5,
    )
    hass.config_entries.async_update_entry.assert_any_call(
        config_entry,
        unique_id="AABBCCDD11223344EEFF0011",
        version=6,
    )


async def test_async_migrate_entry_v4_to_v5_slave_id_renamed() -> None:
    """Test that a v4 entry with slave_id is migrated through v5 to v6."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "neopool_entry_v4"
    config_entry.unique_id = "neopool_AABBCCDD11223344EEFF0011"
    config_entry.version = 4
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, "slave_id": 3}

    def _update_entry(entry: MagicMock, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if k == "data":
                entry.data = v
            else:
                setattr(entry, k, v)

    hass.config_entries.async_update_entry.side_effect = _update_entry

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.neopool.migration.er.async_entries_for_config_entry",
            return_value=[],
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=MagicMock(async_get_device=MagicMock(return_value=None)),
        ),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    assert hass.config_entries.async_update_entry.call_count == 2
    hass.config_entries.async_update_entry.assert_any_call(
        config_entry,
        data={"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 3},
        version=5,
    )
    hass.config_entries.async_update_entry.assert_any_call(
        config_entry,
        unique_id="AABBCCDD11223344EEFF0011",
        version=6,
    )


async def test_async_migrate_entry_v5_to_v6_drops_legacy_prefix() -> None:
    """Test that a v5 entry with neopool_ prefix is migrated to v6 (bare serial)."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "neopool_entry_v5"
    config_entry.unique_id = "neopool_AABBCCDD11223344EEFF0011"
    config_entry.version = 5
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

    mock_entity1 = MagicMock()
    mock_entity1.entity_id = "sensor.neopool_temperature"
    mock_entity1.unique_id = "neopool_AABBCCDD11223344EEFF0011_mbf_measure_temperature"
    mock_entity2 = MagicMock()
    mock_entity2.entity_id = "sensor.neopool_ph"
    mock_entity2.unique_id = "neopool_AABBCCDD11223344EEFF0011_mbf_measure_ph"
    # Entity from a different integration that happens to share the registry.
    mock_entity_unrelated = MagicMock()
    mock_entity_unrelated.entity_id = "sensor.other"
    mock_entity_unrelated.unique_id = "unrelated_xyz"

    mock_entity_registry = MagicMock()
    mock_old_device = MagicMock()
    mock_old_device.id = "old_device_id"
    mock_device_registry = MagicMock()
    mock_device_registry.async_get_device.return_value = mock_old_device

    def _update_entry(entry: MagicMock, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(entry, k, v)

    hass.config_entries.async_update_entry.side_effect = _update_entry

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=mock_entity_registry,
        ),
        patch(
            "custom_components.neopool.migration.er.async_entries_for_config_entry",
            return_value=[mock_entity1, mock_entity2, mock_entity_unrelated],
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=mock_device_registry,
        ),
    ):
        result = await async_migrate_entry(hass, config_entry)

    assert result is True
    # Entity registry rewritten for the prefixed pair, untouched for the unrelated one.
    assert mock_entity_registry.async_update_entity.call_count == 2
    mock_entity_registry.async_update_entity.assert_any_call(
        "sensor.neopool_temperature",
        new_unique_id="AABBCCDD11223344EEFF0011_mbf_measure_temperature",
    )
    mock_entity_registry.async_update_entity.assert_any_call(
        "sensor.neopool_ph",
        new_unique_id="AABBCCDD11223344EEFF0011_mbf_measure_ph",
    )
    # Device registry identifier rewritten.
    mock_device_registry.async_update_device.assert_called_once_with(
        "old_device_id",
        new_identifiers={(DOMAIN, "AABBCCDD11223344EEFF0011")},
    )
    # Config entry unique_id rewritten and version bumped.
    hass.config_entries.async_update_entry.assert_called_once_with(
        config_entry,
        unique_id="AABBCCDD11223344EEFF0011",
        version=6,
    )


async def test_async_migrate_entry_v5_to_v6_already_bare_just_bumps_version() -> None:
    """v5 entry with bare unique_id (no neopool_ prefix) only gets a version bump."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "neopool_entry_v5"
    config_entry.unique_id = "AABBCCDD11223344EEFF0011"
    config_entry.version = 5
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

    result = await async_migrate_entry(hass, config_entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_called_once_with(
        config_entry, version=6
    )


async def test_async_migrate_entry_already_at_current_version_is_noop() -> None:
    """Test that calling async_migrate_entry on a v6 entry does nothing."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "neopool_entry_v6"
    config_entry.unique_id = "AABBCCDD11223344EEFF0011"
    config_entry.version = 6
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

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
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

    existing_entry = MagicMock()
    existing_entry.entry_id = "entry_bbb"
    existing_entry.unique_id = DEFAULT_SERIAL_STRING
    hass.config_entries.async_entries.return_value = [existing_entry]

    with patch(
        "custom_components.neopool.migration.async_probe_serial",
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
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

    hass.config_entries.async_entries.return_value = []

    # First entity will succeed, second will fail → first must be rolled back
    mock_entity1 = MagicMock()
    mock_entity1.unique_id = "old_entry_id_789_mbf_ph_measure"
    mock_entity1.entity_id = "sensor.neopool_ph"

    mock_entity2 = MagicMock()
    mock_entity2.unique_id = "old_entry_id_789_mbf_temperature"
    mock_entity2.entity_id = "sensor.neopool_temperature"

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
            "custom_components.neopool.migration.async_probe_serial",
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
        "sensor.neopool_ph",
        new_unique_id="old_entry_id_789_mbf_ph_measure",
    )
    # Version must NOT be bumped, migration will retry on next HA restart
    hass.config_entries.async_update_entry.assert_not_called()


async def test_async_migrate_entry_rollback_also_fails() -> None:
    """Test migration returns False when rollback fails to prevent duplicates."""
    hass = MagicMock()

    config_entry = MagicMock()
    config_entry.entry_id = "old_entry_id_789"
    config_entry.unique_id = None
    config_entry.version = 1
    config_entry.title = "My Pool"
    config_entry.data = {"host": "192.168.1.100", "port": DEFAULT_PORT, CONF_UNIT_ID: 1}

    hass.config_entries.async_entries.return_value = []

    mock_entity1 = MagicMock()
    mock_entity1.unique_id = "old_entry_id_789_mbf_ph_measure"
    mock_entity1.entity_id = "sensor.neopool_ph"

    mock_entity2 = MagicMock()
    mock_entity2.unique_id = "old_entry_id_789_mbf_temperature"
    mock_entity2.entity_id = "sensor.neopool_temperature"

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
            "custom_components.neopool.migration.async_probe_serial",
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
