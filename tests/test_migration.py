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

"""Tests for cross-domain migration (vistapool → neopool) and folder cleanup."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.neopool.migration import (
    CURRENT_VERSION,
    OLD_DOMAIN,
    _DeferredMigration,
    async_cleanup_old_folder,
    async_migrate_from_vistapool,
    migrate_single_entry_cross_domain,
)

DEFAULT_SERIAL = "0000000100AC00CD00120034"
NEW_UID = f"neopool_{DEFAULT_SERIAL}"


def _make_old_entry(
    *,
    entry_id: str = "old_entry_123",
    version: int = 2,
    unique_id: str | None = NEW_UID,
    title: str = "Pool A",
    data: dict | None = None,
    options: dict | None = None,
    state: ConfigEntryState = ConfigEntryState.LOADED,
    source: str = "user",
) -> MagicMock:
    """Build a MagicMock vistapool ConfigEntry with sensible defaults."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.version = version
    entry.minor_version = 1
    entry.unique_id = unique_id
    entry.title = title
    entry.data = data or {"host": "192.168.1.100", "port": 502, "slave_id": 1}
    entry.options = options or {}
    entry.state = state
    entry.source = source
    return entry


@pytest.mark.asyncio
async def test_no_vistapool_entries_is_noop():
    """async_migrate_from_vistapool returns an empty summary when nothing to do."""
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = []
    summary = await async_migrate_from_vistapool(hass)
    assert summary == {
        "entries_found": 0,
        "entries_migrated": 0,
        "entries_failed": 0,
        "entities_migrated": 0,
        "errors": [],
    }
    hass.config_entries.async_entries.assert_called_with(OLD_DOMAIN)


@pytest.mark.asyncio
async def test_single_v2_entry_success():
    """One v2 vistapool entry migrates cleanly: registry retargeted, old removed."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock(return_value=True)
    hass.config_entries.async_setup = AsyncMock(return_value=True)
    hass.config_entries.async_remove = AsyncMock(return_value=None)

    old = _make_old_entry(source="user")
    hass.config_entries.async_entries.return_value = [old]

    # Two entity registry rows under platform="vistapool"
    e1 = MagicMock()
    e1.entity_id = "sensor.pool_ph"
    e1.unique_id = f"{NEW_UID}_mbf_ph_measure"
    e1.platform = OLD_DOMAIN
    e1.config_entry_id = old.entry_id
    e2 = MagicMock()
    e2.entity_id = "sensor.pool_temperature"
    e2.unique_id = f"{NEW_UID}_mbf_temperature"
    e2.platform = OLD_DOMAIN
    e2.config_entry_id = old.entry_id
    # An unrelated row under a different platform — must NOT be touched
    other = MagicMock()
    other.platform = "some_other_integration"
    other.config_entry_id = "different_entry"

    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = [e1, e2, other]

    # One device under the old vistapool entry
    device = MagicMock()
    device.id = "device_1"
    device.identifiers = {(OLD_DOMAIN, NEW_UID)}

    device_registry = MagicMock()

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=entity_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=device_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_entries_for_config_entry",
            return_value=[device],
        ),
        patch(
            "custom_components.neopool.migration._register_entry_without_setup",
        ) as register_mock,
        patch(
            "custom_components.neopool.migration._setup_registered_entry",
            new=AsyncMock(),
        ) as setup_mock,
        patch(
            "custom_components.neopool.migration._unregister_entry_without_save",
        ) as unregister_mock,
    ):
        summary = await async_migrate_from_vistapool(hass)

    assert summary["entries_found"] == 1
    assert summary["entries_migrated"] == 1
    assert summary["entries_failed"] == 0
    assert summary["entities_migrated"] == 2
    assert summary["errors"] == []

    # Old entry was unloaded before retarget, then removed at the end
    hass.config_entries.async_unload.assert_awaited_once_with(old.entry_id)
    register_mock.assert_called_once()
    setup_mock.assert_awaited_once()
    # Happy path: new entry must NOT be unregistered — it's the one we just
    # successfully migrated to. Unregister belongs only to the failure paths.
    unregister_mock.assert_not_called()
    new_entry = register_mock.call_args.args[1]
    assert new_entry.domain == "neopool"
    assert new_entry.version == CURRENT_VERSION
    assert new_entry.unique_id == NEW_UID
    assert new_entry.title == old.title
    # Original source must be preserved — overriding it would change
    # reconfigure semantics and how HA presents the entry in the UI.
    assert new_entry.source == "user"
    hass.config_entries.async_remove.assert_awaited_once_with(old.entry_id)

    # Both vistapool entities retargeted; the unrelated row was left alone
    assert entity_registry.async_update_entity_platform.call_count == 2
    targets = {
        c.args[0] for c in entity_registry.async_update_entity_platform.call_args_list
    }
    assert targets == {"sensor.pool_ph", "sensor.pool_temperature"}

    # Device retargeted: add new -> change identifiers -> remove old
    assert device_registry.async_update_device.call_count == 3


@pytest.mark.asyncio
async def test_unload_called_unconditionally():
    """Unload runs even for a NOT_LOADED entry — defensive against stale state."""
    hass = MagicMock()
    # async_unload returns True for any entry state, including NOT_LOADED
    hass.config_entries.async_unload = AsyncMock(return_value=True)
    hass.config_entries.async_setup = AsyncMock()
    hass.config_entries.async_remove = AsyncMock()

    old = _make_old_entry(state=ConfigEntryState.NOT_LOADED)
    hass.config_entries.async_entries.return_value = [old]

    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = []
    device_registry = MagicMock()

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=entity_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=device_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_entries_for_config_entry",
            return_value=[],
        ),
    ):
        await async_migrate_from_vistapool(hass)

    # Unload runs even for NOT_LOADED — guards against entity_registry rows
    # left over from a previous boot that haven't been cleared yet.
    hass.config_entries.async_unload.assert_awaited_once_with(old.entry_id)
    hass.config_entries.async_setup.assert_awaited_once()
    hass.config_entries.async_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_unload_failure_aborts_migration():
    """When async_unload returns False, migration aborts before retargeting."""
    hass = MagicMock()
    # Simulate unload refusal: integration's async_unload_entry returned False
    hass.config_entries.async_unload = AsyncMock(return_value=False)
    hass.config_entries.async_setup = AsyncMock()
    hass.config_entries.async_remove = AsyncMock()

    old = _make_old_entry()
    hass.config_entries.async_entries.return_value = [old]

    summary = await async_migrate_from_vistapool(hass)

    # The per-entry try/except records the unload failure as a hard failure
    assert summary["entries_failed"] == 1
    assert summary["entries_migrated"] == 0
    assert any("Failed to unload" in err for err in summary["errors"])
    # async_setup and async_remove must NOT have been called — we never reached them
    hass.config_entries.async_setup.assert_not_awaited()
    hass.config_entries.async_remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_multiple_entries_each_migrated_independently():
    """Two vistapool entries (multi-pool setup) both migrate successfully."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock(return_value=True)
    hass.config_entries.async_setup = AsyncMock()
    hass.config_entries.async_remove = AsyncMock()

    e_a = _make_old_entry(entry_id="entry_a", title="Pool A")
    e_b = _make_old_entry(entry_id="entry_b", title="Pool B")
    hass.config_entries.async_entries.return_value = [e_a, e_b]

    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = []
    device_registry = MagicMock()

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=entity_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=device_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_entries_for_config_entry",
            return_value=[],
        ),
    ):
        summary = await async_migrate_from_vistapool(hass)

    assert summary["entries_found"] == 2
    assert summary["entries_migrated"] == 2
    assert summary["entries_failed"] == 0
    assert hass.config_entries.async_setup.await_count == 2
    assert hass.config_entries.async_remove.await_count == 2


@pytest.mark.asyncio
async def test_one_entry_fails_others_continue():
    """When one entry fails (e.g. async_setup raises), others still migrate."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock(return_value=True)
    hass.config_entries.async_remove = AsyncMock()

    # First setup() succeeds, second raises — but the per-entry try/except must
    # ensure the loop keeps running and summary records both outcomes.
    setup_calls = {"n": 0}

    async def setup_side_effect(entry_id):
        setup_calls["n"] += 1
        if setup_calls["n"] == 2:
            raise RuntimeError("simulated failure")

    hass.config_entries.async_setup = AsyncMock(side_effect=setup_side_effect)

    e_a = _make_old_entry(entry_id="entry_a", title="Pool A")
    e_b = _make_old_entry(entry_id="entry_b", title="Pool B")
    hass.config_entries.async_entries.return_value = [e_a, e_b]

    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = []
    device_registry = MagicMock()

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=entity_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=device_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_entries_for_config_entry",
            return_value=[],
        ),
    ):
        summary = await async_migrate_from_vistapool(hass)

    assert summary["entries_found"] == 2
    assert summary["entries_migrated"] == 1
    assert summary["entries_failed"] == 1
    assert any("Pool B" in err for err in summary["errors"])


@pytest.mark.asyncio
async def test_entity_retarget_failure_rolls_back():
    """If async_update_entity_platform raises, applied retargets are undone."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock(return_value=True)
    hass.config_entries.async_setup = AsyncMock()
    hass.config_entries.async_remove = AsyncMock()

    old = _make_old_entry()
    hass.config_entries.async_entries.return_value = [old]

    e1 = MagicMock()
    e1.entity_id = "sensor.pool_ph"
    e1.unique_id = f"{NEW_UID}_mbf_ph_measure"
    e1.platform = OLD_DOMAIN
    e1.config_entry_id = old.entry_id
    e2 = MagicMock()
    e2.entity_id = "sensor.pool_temperature"
    e2.unique_id = f"{NEW_UID}_mbf_temperature"
    e2.platform = OLD_DOMAIN
    e2.config_entry_id = old.entry_id

    # First call succeeds (e1 retargeted), second raises ValueError.
    # The rollback then re-targets e1 back to OLD_DOMAIN.
    call_count = {"n": 0}

    def update_side_effect(entity_id, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise ValueError("registry collision")
        # third call is the rollback — must succeed silently

    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = [e1, e2]
    entity_registry.async_update_entity_platform.side_effect = update_side_effect

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=entity_registry,
        ),
        patch(
            "custom_components.neopool.migration._register_entry_without_setup",
        ) as register_mock,
        patch(
            "custom_components.neopool.migration._unregister_entry_without_save",
        ) as unregister_mock,
    ):
        summary = await async_migrate_from_vistapool(hass)

    # Migration failed for this entry — the per-entry try/except records it
    assert summary["entries_failed"] == 1
    # 3 calls: e1 retarget, e2 retarget (raises), e1 rollback
    assert entity_registry.async_update_entity_platform.call_count == 3
    # async_setup and async_remove must NOT have been called — we never reached them
    hass.config_entries.async_setup.assert_not_awaited()
    hass.config_entries.async_remove.assert_not_awaited()
    # Critical: the new entry was registered in step 2, so step 3's failure
    # must trigger the unregister cleanup — otherwise we leak a ghost entry.
    register_mock.assert_called_once()
    unregister_mock.assert_called_once()
    # The unregister call must reference the SAME entry that was registered
    assert unregister_mock.call_args.args[1] is register_mock.call_args.args[1]


@pytest.mark.asyncio
async def test_setup_failure_unregisters_entry():
    """If async_setup fails after retarget completes, entry is unregistered."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock(return_value=True)
    hass.config_entries.async_setup = AsyncMock(
        side_effect=RuntimeError("platform setup blew up")
    )
    hass.config_entries.async_remove = AsyncMock()

    old = _make_old_entry()
    hass.config_entries.async_entries.return_value = [old]

    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = []
    device_registry = MagicMock()

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=entity_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=device_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_entries_for_config_entry",
            return_value=[],
        ),
        patch(
            "custom_components.neopool.migration._register_entry_without_setup",
        ) as register_mock,
        patch(
            "custom_components.neopool.migration._setup_registered_entry",
            new=AsyncMock(side_effect=RuntimeError("platform setup blew up")),
        ),
        patch(
            "custom_components.neopool.migration._unregister_entry_without_save",
        ) as unregister_mock,
    ):
        summary = await async_migrate_from_vistapool(hass)

    # Migration failed — recorded as a hard failure
    assert summary["entries_failed"] == 1
    assert any("platform setup blew up" in err for err in summary["errors"])
    # async_remove (step 6) must NOT have run
    hass.config_entries.async_remove.assert_not_awaited()
    # Critical: ghost entry cleanup must have run
    register_mock.assert_called_once()
    unregister_mock.assert_called_once()
    assert unregister_mock.call_args.args[1] is register_mock.call_args.args[1]


@pytest.mark.asyncio
async def test_unregister_helper_removes_entry_and_dispatches():
    """_unregister_entry_without_save deletes from _entries and dispatches REMOVED."""
    from custom_components.neopool.migration import _unregister_entry_without_save

    hass = MagicMock()
    hass.config_entries._entries = {"entry_xyz": "the_entry_object"}

    entry = MagicMock()
    entry.entry_id = "entry_xyz"

    _unregister_entry_without_save(hass, entry)

    # Entry removed from _entries
    assert "entry_xyz" not in hass.config_entries._entries
    # update_issues + REMOVED dispatch fired
    hass.config_entries.async_update_issues.assert_called_once()
    hass.config_entries._async_dispatch.assert_called_once()
    # The dispatch arg must be the REMOVED change kind
    from homeassistant.config_entries import ConfigEntryChange

    assert (
        hass.config_entries._async_dispatch.call_args.args[0]
        == ConfigEntryChange.REMOVED
    )
    assert hass.config_entries._async_dispatch.call_args.args[1] is entry


@pytest.mark.asyncio
async def test_unregister_helper_is_idempotent():
    """_unregister_entry_without_save no-ops when entry isn't in _entries."""
    from custom_components.neopool.migration import _unregister_entry_without_save

    hass = MagicMock()
    hass.config_entries._entries = {}  # empty — entry was never registered

    entry = MagicMock()
    entry.entry_id = "entry_xyz"

    # Must not raise
    _unregister_entry_without_save(hass, entry)

    # Nothing dispatched because there was nothing to remove
    hass.config_entries.async_update_issues.assert_not_called()
    hass.config_entries._async_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_v1_entry_runs_prelude_then_cross_domain():
    """A v1 entry first goes through the v1→v2 prelude, then cross-domain."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock(return_value=True)
    hass.config_entries.async_setup = AsyncMock()
    hass.config_entries.async_remove = AsyncMock()

    old = _make_old_entry(version=1, unique_id=None)
    hass.config_entries.async_entries.return_value = [old]

    # Simulate the prelude bumping version + unique_id on the live MagicMock
    async def fake_v1_to_v2(_hass, entry, *, source_domain):
        assert source_domain == OLD_DOMAIN
        entry.version = 2
        entry.unique_id = NEW_UID
        return True

    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = []
    device_registry = MagicMock()

    with (
        patch(
            "custom_components.neopool.migration._migrate_v1_to_v2",
            new=AsyncMock(side_effect=fake_v1_to_v2),
        ),
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=entity_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=device_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_entries_for_config_entry",
            return_value=[],
        ),
    ):
        summary = await async_migrate_from_vistapool(hass)

    assert summary["entries_migrated"] == 1
    assert summary["entries_failed"] == 0
    # Cross-domain step ran after prelude
    hass.config_entries.async_setup.assert_awaited_once()
    hass.config_entries.async_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_v1_entry_offline_defers():
    """When the v1→v2 prelude defers (HW offline), cross-domain is skipped."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock()
    hass.config_entries.async_setup = AsyncMock()
    hass.config_entries.async_remove = AsyncMock()

    old = _make_old_entry(version=1, unique_id=None)
    hass.config_entries.async_entries.return_value = [old]

    # Prelude returns True but does NOT bump version → defer
    async def fake_v1_to_v2(_hass, _entry, *, source_domain):
        return True  # entry.version stays at 1

    with patch(
        "custom_components.neopool.migration._migrate_v1_to_v2",
        new=AsyncMock(side_effect=fake_v1_to_v2),
    ):
        summary = await async_migrate_from_vistapool(hass)

    # Not a failure — the deferred path is recoverable
    assert summary["entries_migrated"] == 0
    assert summary["entries_failed"] == 0
    assert any("deferred" in err.lower() for err in summary["errors"])
    # Nothing else should have run
    hass.config_entries.async_unload.assert_not_awaited()
    hass.config_entries.async_setup.assert_not_awaited()
    hass.config_entries.async_remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_v1_prelude_hard_failure_records_error():
    """When the v1→v2 prelude returns False, the entry is counted as failed."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock()
    hass.config_entries.async_setup = AsyncMock()
    hass.config_entries.async_remove = AsyncMock()

    old = _make_old_entry(version=1, unique_id=None, title="Bad Pool")
    hass.config_entries.async_entries.return_value = [old]

    with patch(
        "custom_components.neopool.migration._migrate_v1_to_v2",
        new=AsyncMock(return_value=False),
    ):
        summary = await async_migrate_from_vistapool(hass)

    assert summary["entries_migrated"] == 0
    assert summary["entries_failed"] == 1
    assert any("Bad Pool" in err for err in summary["errors"])


@pytest.mark.asyncio
async def test_deferred_migration_signal_class():
    """_DeferredMigration is a sentinel exception, not a hard failure."""
    # Sanity: it must inherit from Exception so the per-entry try/except
    # in async_migrate_from_vistapool can distinguish it from real errors.
    assert issubclass(_DeferredMigration, Exception)


@pytest.mark.asyncio
async def test_device_identifiers_flipped_to_neopool():
    """Device identifier (vistapool, X) is rewritten to (neopool, X)."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock(return_value=True)
    hass.config_entries.async_setup = AsyncMock()
    hass.config_entries.async_remove = AsyncMock()

    old = _make_old_entry()

    # Device has the legacy vistapool identifier tuple
    device = MagicMock()
    device.id = "dev_1"
    device.identifiers = {(OLD_DOMAIN, NEW_UID)}

    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = []
    device_registry = MagicMock()

    with (
        patch(
            "custom_components.neopool.migration.er.async_get",
            return_value=entity_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_get",
            return_value=device_registry,
        ),
        patch(
            "custom_components.neopool.migration.dr.async_entries_for_config_entry",
            return_value=[device],
        ),
    ):
        await migrate_single_entry_cross_domain(hass, old)

    # Three async_update_device calls: add new entry → flip identifiers → remove old
    calls = device_registry.async_update_device.call_args_list
    assert len(calls) == 3
    # Middle call must update identifiers to neopool tuple
    flip_call = calls[1]
    assert flip_call.kwargs.get("new_identifiers") == {("neopool", NEW_UID)}


# ──────────────────────────────────────────────────────────────────────────────
# async_cleanup_old_folder
# ──────────────────────────────────────────────────────────────────────────────


def _executor_passthrough(func, *args, **kwargs):
    """Synchronous fake for hass.async_add_executor_job — runs the callable inline."""
    return func(*args, **kwargs)


@pytest.fixture
def hass_with_config_path(tmp_path: Path) -> MagicMock:
    """Build a hass mock whose config.path() resolves under the temp dir."""
    hass = MagicMock()
    hass.config.path.side_effect = lambda *parts: str(tmp_path.joinpath(*parts))
    # Make async_add_executor_job invoke the function synchronously, returning
    # an awaitable that yields its result.

    async def fake_executor_job(func, *args, **kwargs):
        return func(*args, **kwargs)

    hass.async_add_executor_job = fake_executor_job
    return hass


@pytest.mark.asyncio
async def test_cleanup_missing_folder_is_noop(hass_with_config_path):
    """When custom_components/vistapool/ doesn't exist, return True."""
    result = await async_cleanup_old_folder(hass_with_config_path)
    assert result is True


@pytest.mark.asyncio
async def test_cleanup_no_manifest_refuses(hass_with_config_path, tmp_path):
    """When the folder exists but has no manifest.json, refuse to delete."""
    folder = tmp_path / "custom_components" / "vistapool"
    folder.mkdir(parents=True)
    # Folder has some content but no manifest
    (folder / "stray.txt").write_text("hi")

    result = await async_cleanup_old_folder(hass_with_config_path)
    assert result is False
    # Folder must still exist
    assert folder.exists()


@pytest.mark.asyncio
async def test_cleanup_unreadable_manifest_refuses(hass_with_config_path, tmp_path):
    """If manifest.json can't be parsed, refuse to delete."""
    folder = tmp_path / "custom_components" / "vistapool"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text("{not valid json")

    result = await async_cleanup_old_folder(hass_with_config_path)
    assert result is False
    assert folder.exists()


@pytest.mark.asyncio
async def test_cleanup_foreign_manifest_refuses(hass_with_config_path, tmp_path):
    """A foreign vistapool fork (different repo URL) must NOT be deleted."""
    folder = tmp_path / "custom_components" / "vistapool"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        '{"domain": "vistapool",'
        ' "documentation": "https://github.com/someone/else",'
        ' "issue_tracker": "https://github.com/someone/else/issues"}'
    )

    result = await async_cleanup_old_folder(hass_with_config_path)
    assert result is False
    assert folder.exists()


@pytest.mark.asyncio
async def test_cleanup_our_folder_deletes(hass_with_config_path, tmp_path):
    """Our legacy folder (matching repo URL) is deleted recursively."""
    folder = tmp_path / "custom_components" / "vistapool"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        '{"domain": "vistapool",'
        ' "documentation": "https://github.com/svasek/homeassistant-vistapool-modbus",'
        ' "issue_tracker": "https://github.com/svasek/homeassistant-vistapool-modbus/issues"}'
    )
    # Simulate a few subdirs and files
    (folder / "translations").mkdir()
    (folder / "translations" / "en.json").write_text("{}")
    (folder / "modbus.py").write_text("# placeholder")

    result = await async_cleanup_old_folder(hass_with_config_path)
    assert result is True
    assert not folder.exists()


@pytest.mark.asyncio
async def test_cleanup_matches_via_issue_tracker_only(hass_with_config_path, tmp_path):
    """If only issue_tracker URL matches, deletion still proceeds (logical OR)."""
    folder = tmp_path / "custom_components" / "vistapool"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        '{"domain": "vistapool",'
        ' "documentation": "https://example.com/some-other-doc-site",'
        ' "issue_tracker": "https://github.com/svasek/homeassistant-vistapool-modbus/issues"}'
    )

    result = await async_cleanup_old_folder(hass_with_config_path)
    assert result is True
    assert not folder.exists()


@pytest.mark.asyncio
async def test_entity_retarget_failure_rollback_also_fails():
    """Rollback exceptions during entity retarget are logged, then the original error re-raises."""
    hass = MagicMock()
    hass.config_entries.async_unload = AsyncMock(return_value=True)
    hass.config_entries.async_setup = AsyncMock()
    hass.config_entries.async_remove = AsyncMock()

    old = _make_old_entry()
    hass.config_entries.async_entries.return_value = [old]

    e1 = MagicMock()
    e1.entity_id = "sensor.pool_ph"
    e1.unique_id = f"{NEW_UID}_mbf_ph_measure"
    e1.platform = OLD_DOMAIN
    e1.config_entry_id = old.entry_id
    e2 = MagicMock()
    e2.entity_id = "sensor.pool_temperature"
    e2.unique_id = f"{NEW_UID}_mbf_temperature"
    e2.platform = OLD_DOMAIN
    e2.config_entry_id = old.entry_id

    # Both forward retarget and rollback raise — covers the inner except branch
    call_count = {"n": 0}

    def update_side_effect(entity_id, *args, **kwargs):
        call_count["n"] += 1
        # Call 1: e1 retarget OK; call 2: e2 retarget fails;
        # call 3: e1 rollback also fails (logged but swallowed).
        if call_count["n"] >= 2:
            raise ValueError("registry collision")

    entity_registry = MagicMock()
    entity_registry.entities.values.return_value = [e1, e2]
    entity_registry.async_update_entity_platform.side_effect = update_side_effect

    with patch(
        "custom_components.neopool.migration.er.async_get",
        return_value=entity_registry,
    ):
        summary = await async_migrate_from_vistapool(hass)

    assert summary["entries_failed"] == 1
    # Three calls: e1 retarget (ok), e2 retarget (fail), e1 rollback (fail)
    assert entity_registry.async_update_entity_platform.call_count == 3


@pytest.mark.asyncio
async def test_cleanup_rmtree_failure_returns_false(
    hass_with_config_path, tmp_path, monkeypatch
):
    """If shutil.rmtree raises (e.g. permission error), return False."""
    folder = tmp_path / "custom_components" / "vistapool"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        '{"domain": "vistapool",'
        ' "documentation": "https://github.com/svasek/homeassistant-vistapool-modbus",'
        ' "issue_tracker": "https://github.com/svasek/homeassistant-vistapool-modbus/issues"}'
    )

    def boom(*args, **kwargs):
        raise PermissionError("simulated")

    monkeypatch.setattr("custom_components.neopool.migration.shutil.rmtree", boom)

    result = await async_cleanup_old_folder(hass_with_config_path)
    assert result is False
    # Folder must still be present — the failed rmtree didn't actually delete it
    assert folder.exists()
