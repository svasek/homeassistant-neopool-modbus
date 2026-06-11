# Copyright 2025 Miloš Svašek

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.neopool import (
    _cleanup_removed_entities,
    async_migrate_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.neopool.const import DEFAULT_PORT


@pytest.mark.asyncio
async def test_async_setup_registers_services():
    """async_setup registers the neopool services and returns True."""
    hass = MagicMock()
    hass.services.async_register = MagicMock()
    result = await async_setup(hass, {})
    assert result is True
    assert hass.services.async_register.call_count == 2


@pytest.mark.asyncio
async def test_async_setup_entry_success():
    """Test async_setup_entry completes successfully."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    hass.async_add_executor_job = AsyncMock(return_value=[])
    # async_cleanup_legacy_files (called from async_setup_entry) builds a
    # Path() from hass.config.path(...); without a stub MagicMock leaks
    # into Path() and the test only "passes" by accident (and may break on
    # other Python versions where Path rejects MagicMock).
    hass.config.path = MagicMock(side_effect=lambda sub: f"/tmp/ha_test/{sub}")
    config_entry = MagicMock()
    with patch("custom_components.neopool.NeoPoolModbusClient"):
        with patch("custom_components.neopool.NeoPoolCoordinator") as mock_coordinator:
            mock_coord_instance = mock_coordinator.return_value
            mock_coord_instance.async_config_entry_first_refresh = AsyncMock(
                return_value=None
            )
            with patch("custom_components.neopool.er.async_get") as mock_er_get:
                mock_registry = MagicMock()
                mock_er_get.return_value = mock_registry
                with patch(
                    "custom_components.neopool.er.async_entries_for_config_entry",
                    return_value=[],
                ):
                    result = await async_setup_entry(hass, config_entry)
                    assert result is True


@pytest.mark.asyncio
async def test_async_unload_entry_success():
    """Test async_unload_entry completes successfully."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    config_entry = MagicMock()
    config_entry.entry_id = "entry1"
    coordinator = MagicMock()
    coordinator.client = AsyncMock()
    config_entry.runtime_data = coordinator
    result = await async_unload_entry(hass, config_entry)
    assert result is True
    # Check that follow-up refresh was cancelled and client closed
    coordinator.cancel_follow_up_refresh.assert_called_once()
    assert coordinator.client.close.await_count == 1


@pytest.mark.asyncio
async def test_async_unload_entry_no_client():
    """Test async_unload_entry when coordinator has no client."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    config_entry = MagicMock()
    config_entry.entry_id = "entry2"
    coordinator = MagicMock()
    coordinator.client = None
    config_entry.runtime_data = coordinator
    result = await async_unload_entry(hass, config_entry)
    assert result is True


def test_cleanup_removes_orphaned_entities():
    """Test _cleanup_removed_entities removes entities matching REMOVED_ENTITY_KEYS."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    orphan = MagicMock()
    orphan.unique_id = "test_entry_hidro on target"
    orphan.entity_id = "binary_sensor.hydrolysis_on_target"

    valid = MagicMock()
    valid.unique_id = "test_entry_hidro low flow"
    valid.entity_id = "binary_sensor.hydrolysis_low_flow"

    mock_registry = MagicMock()

    with patch("custom_components.neopool.er.async_get", return_value=mock_registry):
        with patch(
            "custom_components.neopool.er.async_entries_for_config_entry",
            return_value=[orphan, valid],
        ):
            _cleanup_removed_entities(hass, entry)

    mock_registry.async_remove.assert_called_once_with(
        "binary_sensor.hydrolysis_on_target"
    )


def test_cleanup_removes_ph_pump_entities():
    """Test _cleanup_removed_entities matches lowercase pH pump unique_ids."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    # unique_ids are built with key.lower() — REMOVED_ENTITY_KEYS must be lowercase
    ph_acid = MagicMock()
    ph_acid.unique_id = "test_entry_ph acid pump active"
    ph_acid.entity_id = "binary_sensor.neopool_ph_acid_pump_active"

    ph_base = MagicMock()
    ph_base.unique_id = "test_entry_ph pump active"
    ph_base.entity_id = "binary_sensor.neopool_ph_pump_active"

    unrelated = MagicMock()
    unrelated.unique_id = "test_entry_ph control module"
    unrelated.entity_id = "binary_sensor.neopool_ph_control_module"

    mock_registry = MagicMock()

    with patch("custom_components.neopool.er.async_get", return_value=mock_registry):
        with patch(
            "custom_components.neopool.er.async_entries_for_config_entry",
            return_value=[ph_acid, ph_base, unrelated],
        ):
            _cleanup_removed_entities(hass, entry)

    assert mock_registry.async_remove.call_count == 2
    removed_ids = [c.args[0] for c in mock_registry.async_remove.call_args_list]
    assert "binary_sensor.neopool_ph_acid_pump_active" in removed_ids
    assert "binary_sensor.neopool_ph_pump_active" in removed_ids


def test_cleanup_no_orphans():
    """Test _cleanup_removed_entities does nothing when no orphans exist."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"

    valid = MagicMock()
    valid.unique_id = "test_entry_hidro low flow"
    valid.entity_id = "binary_sensor.hydrolysis_low_flow"

    mock_registry = MagicMock()

    with patch("custom_components.neopool.er.async_get", return_value=mock_registry):
        with patch(
            "custom_components.neopool.er.async_entries_for_config_entry",
            return_value=[valid],
        ):
            _cleanup_removed_entities(hass, entry)

    mock_registry.async_remove.assert_not_called()


def test_cleanup_removes_orphans_with_serial_unique_id():
    """Test _cleanup_removed_entities matches new unique_id-prefixed entities (v2+)."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "old_entry_id"
    entry.unique_id = "neopool_0000000100AC00CD00120034"

    # Orphan with new unique_id prefix (post-migration)
    orphan_new = MagicMock()
    orphan_new.unique_id = "neopool_0000000100AC00CD00120034_hidro on target"
    orphan_new.entity_id = "binary_sensor.hydrolysis_on_target"

    # Orphan with old entry_id prefix (pre-migration leftover)
    orphan_old = MagicMock()
    orphan_old.unique_id = "old_entry_id_hidro on target"
    orphan_old.entity_id = "binary_sensor.hydrolysis_on_target_old"

    valid = MagicMock()
    valid.unique_id = "neopool_0000000100AC00CD00120034_hidro low flow"
    valid.entity_id = "binary_sensor.hydrolysis_low_flow"

    mock_registry = MagicMock()

    with patch("custom_components.neopool.er.async_get", return_value=mock_registry):
        with patch(
            "custom_components.neopool.er.async_entries_for_config_entry",
            return_value=[orphan_new, orphan_old, valid],
        ):
            _cleanup_removed_entities(hass, entry)

    assert mock_registry.async_remove.call_count == 2
    removed_ids = [c.args[0] for c in mock_registry.async_remove.call_args_list]
    assert "binary_sensor.hydrolysis_on_target" in removed_ids
    assert "binary_sensor.hydrolysis_on_target_old" in removed_ids


# --- Migration tests ---

DEFAULT_SERIAL_REGS = [0x0000, 0x0001, 0x00AC, 0x00CD, 0x0012, 0x0034]
DEFAULT_SERIAL_STRING = "".join(f"{r:04X}" for r in DEFAULT_SERIAL_REGS)


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_to_v2_success():
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


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_to_v2_serial_unavailable():
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


@pytest.mark.asyncio
async def test_async_migrate_entry_v3_to_v4_marker_bump():
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


@pytest.mark.asyncio
async def test_async_migrate_entry_already_at_current_version_is_noop():
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


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_to_v2_duplicate_detected():
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


@pytest.mark.asyncio
async def test_async_migrate_entry_entity_update_error():
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


@pytest.mark.asyncio
async def test_async_migrate_entry_rollback_also_fails():
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
