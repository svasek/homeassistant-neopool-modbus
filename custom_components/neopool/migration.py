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

"""NeoPool integration for Home Assistant - Config entry migration."""

import asyncio
import json
import logging
import shutil
from pathlib import Path
from types import MappingProxyType

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryChange,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CURRENT_VERSION, DOMAIN
from .helpers import async_get_device_serial

_LOGGER = logging.getLogger(__name__)

# The legacy domain we migrate FROM during the v3 cross-domain rename.
OLD_DOMAIN = "vistapool"

# CURRENT_VERSION (imported from .const) is reached in steps:
#   v1 → v2  serial-based unique_id (HA-driven async_migrate_entry, or
#            cross-domain Step 0 if the entry is still under vistapool).
#   v2 → v3  cross-domain rename (migrate_single_entry_cross_domain,
#            invoked from the neopool config flow).
#   v3 → v4  marker bump after the neopool-modbus library extraction
#            (HA-driven async_migrate_entry — no data-shape change).

# Marker used to validate that the orphaned `custom_components/vistapool/`
# directory we're about to delete actually belonged to OUR integration
# (and not, say, an unrelated user-installed fork). Matched against the
# documentation/issue_tracker fields of the old manifest.json.
LEGACY_REPO_URL = "github.com/svasek/homeassistant-vistapool-modbus"

# Files removed in v4 because their implementation moved to the
# neopool-modbus PyPI library. HACS unzips releases on top of the
# existing custom_components/neopool/ directory without removing files
# absent from the new ZIP, so we delete them at runtime to prevent
# Python from importing a stale local copy alongside the library.
LEGACY_FILES_REMOVED_IN_V4 = (
    "modbus.py",
    "modbus_compat.py",
    "status_mask.py",
)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate config entry to current version.

    Each step is gated so it only runs when the entry is actually at the
    relevant version — calling this on an already-current entry must be a
    cheap no-op (HA invokes it on every setup whose stored version differs
    from ``ConfigFlow.VERSION``, and we don't want stale "Migrating … from
    v4 to v2 / 0 entities migrated" log noise).

    Handles:
      * v1 → v2 — serial-based unique_id (from PR #146).
      * v3 → v4 — marker bump after the move to the neopool-modbus PyPI
        library; entry data shape is unchanged. Tagging the entry helps
        diagnostics and any future v4-only logic to distinguish entries
        last touched before / after the library extraction.

    The v2 → v3 step (cross-domain ``vistapool`` → ``neopool`` rename)
    cannot run from here — by the time HA dispatches to this function the
    entry is already under ``DOMAIN``. Cross-domain migration lives in
    :func:`migrate_single_entry_cross_domain`, invoked from the neopool
    config flow when the user adds the new integration with a legacy
    vistapool entry still present.
    """
    if config_entry.version < 2:
        if not await _migrate_v1_to_v2(hass, config_entry, source_domain=DOMAIN):
            return False
        # If the v1→v2 prelude deferred (controller offline) the entry is
        # still at v1; skip the v3→v4 bump and let the next setup attempt
        # retry from the top.
        if config_entry.version < 2:
            return True

    if config_entry.version == 3:
        hass.config_entries.async_update_entry(config_entry, version=CURRENT_VERSION)
        _LOGGER.info(
            "Bumped %s config entry %s to v%d (neopool-modbus library marker)",
            DOMAIN,
            config_entry.entry_id,
            CURRENT_VERSION,
        )
    return True


async def _migrate_v1_to_v2(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    *,
    source_domain: str,
) -> bool:
    """Migrate one config entry from v1 (no unique_id) to v2 (serial-based unique_id).

    Parametrized by `source_domain` so the same logic can run:
      * In-domain (HA-driven `async_migrate_entry`) → source_domain = DOMAIN.
      * Cross-domain prelude (legacy vistapool entry encountered during the
        domain rename) → source_domain = "vistapool".

    `source_domain` controls only which (domain, entry_id) tuple is used to
    locate the existing device in the device registry; the new unique_id
    prefix is always "neopool_" (the prefix predates the rename and is
    intentionally kept stable across this migration so entity unique_ids
    don't change again in v2 → v3).

    Old format: entry.unique_id = None
    New format: entry.unique_id = "neopool_{serial}"
    """
    _LOGGER.info(
        "Migrating %s config entry %s from v%s to v2",
        source_domain,
        config_entry.entry_id,
        config_entry.version,
    )

    # Trial read to get serial (dict() unwraps MappingProxy for the Modbus client)
    serial = await async_get_device_serial(dict(config_entry.data))
    if not serial:
        _LOGGER.warning(
            "Migration for %s: Cannot read device serial — "
            "device may be offline. Will retry on next restart.",
            config_entry.entry_id,
        )
        # Don't bump version — migration will be retried on next HA startup
        return True

    new_unique_id = f"neopool_{serial}"

    # Check if this serial is already registered (duplicate after migration).
    # We check both the source domain (where the entry lives now) and our
    # own DOMAIN (in case a fresh neopool entry already exists for the same
    # device — unlikely but possible during a partial migration retry).
    for check_domain in {source_domain, DOMAIN}:
        for entry in hass.config_entries.async_entries(check_domain):
            if (
                entry.entry_id != config_entry.entry_id
                and entry.unique_id == new_unique_id
            ):
                _LOGGER.error(
                    "Migration failed: Device %s is already configured under %s",
                    new_unique_id,
                    check_domain,
                )
                return False

    # Migrate entity unique_ids in registry before bumping version.
    # Use all-or-nothing: collect planned changes, then apply. If any
    # update fails, roll back already-applied changes to avoid a
    # partially-migrated registry.
    entity_registry = er.async_get(hass)
    old_entry_id = config_entry.entry_id
    old_prefix = f"{old_entry_id}_"

    # Build list of (entity_id, old_unique_id, new_unique_id) to migrate
    planned: list[tuple[str, str, str]] = []
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, config_entry.entry_id
    ):
        if entity_entry.unique_id and entity_entry.unique_id.startswith(old_prefix):
            key_part = entity_entry.unique_id.replace(old_prefix, "", 1)
            planned.append(
                (
                    entity_entry.entity_id,
                    entity_entry.unique_id,
                    f"{new_unique_id}_{key_part}",
                )
            )

    # Apply changes, tracking successful updates for potential rollback
    applied: list[tuple[str, str, str]] = []  # (entity_id, old_uid, new_uid)
    for entity_id, old_uid, new_uid in planned:
        _LOGGER.debug("Migrating entity %s: %s → %s", entity_id, old_uid, new_uid)
        try:
            entity_registry.async_update_entity(entity_id, new_unique_id=new_uid)
            applied.append((entity_id, old_uid, new_uid))
        except (HomeAssistantError, ValueError, KeyError) as err:
            _LOGGER.error("Failed to migrate entity %s: %s", entity_id, err)
            # Roll back already-applied changes
            rollback_failed = False
            for rb_entity_id, rb_old_uid, _rb_new_uid in applied:
                try:
                    entity_registry.async_update_entity(
                        rb_entity_id, new_unique_id=rb_old_uid
                    )
                except Exception as rb_err:  # noqa: BLE001
                    _LOGGER.error(
                        "Rollback failed for entity %s: %s", rb_entity_id, rb_err
                    )
                    rollback_failed = True
            if rollback_failed:
                _LOGGER.error(
                    "Migration aborted for %s: rollback incomplete — "
                    "integration will not load to prevent duplicates.",
                    config_entry.title,
                )
                return False
            _LOGGER.error(
                "Migration aborted for %s: entity update error. "
                "Will retry on next restart.",
                config_entry.title,
            )
            return True

    # Bump version only after all entities migrated successfully
    hass.config_entries.async_update_entry(
        config_entry, unique_id=new_unique_id, version=2
    )

    # Update old device identifier to serial-based one (preserves area, labels, etc.).
    # The device was created under (source_domain, entry_id); after the rename it must
    # use (source_domain, new_unique_id) — the cross-domain step (if any) flips the
    # source_domain part of the tuple separately.
    device_registry = dr.async_get(hass)
    old_device = device_registry.async_get_device(
        identifiers={(source_domain, old_entry_id)}
    )
    if old_device:
        device_registry.async_update_device(
            old_device.id,
            new_identifiers={(source_domain, new_unique_id)},
        )
        _LOGGER.debug("Updated device identifier %s → %s", old_entry_id, new_unique_id)

    _LOGGER.info(
        "Migration completed for %s: %d entities migrated, unique_id=…%s",
        config_entry.title,
        len(applied),
        new_unique_id[-6:],
    )
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Cross-domain migration (vistapool → neopool)
# ──────────────────────────────────────────────────────────────────────────────


async def async_migrate_from_vistapool(hass: HomeAssistant) -> dict:
    """Migrate any legacy vistapool config entries to neopool.

    Bulk wrapper that walks every legacy vistapool entry and runs the
    per-entry cross-domain migration on each. The single-entry function
    (`migrate_single_entry_cross_domain`) is what the neopool config_flow
    actually calls when the user opts in via the import step.

    Per-entry pipeline:
      1. If `entry.version == 1`, run the parametrized v1→v2 prelude on the
         vistapool entry in-place. If the controller is offline, the prelude
         defers (returns True without bumping version) and we skip the
         cross-domain step for this entry — both run on the next boot.
      2. Cross-domain step: build a `ConfigEntry(domain="neopool", version=3)`
         with the same data/options/unique_id, retarget entity_registry rows,
         retarget device_registry rows, then `async_add` (which triggers
         setup_entry on the new entry), then `async_remove` the old vistapool
         entry.

    Returns a summary dict suitable for repair issue placeholders.
    """
    summary = {
        "entries_found": 0,
        "entries_migrated": 0,
        "entries_failed": 0,
        "entities_migrated": 0,
        "errors": [],
    }
    vistapool_entries = hass.config_entries.async_entries(OLD_DOMAIN)
    if not vistapool_entries:
        return summary
    summary["entries_found"] = len(vistapool_entries)

    for old_entry in vistapool_entries:
        try:
            entities_count = await migrate_single_entry_cross_domain(hass, old_entry)
            summary["entries_migrated"] += 1
            summary["entities_migrated"] += entities_count
        except _DeferredMigration as exc:
            # v1→v2 prelude deferred (controller offline); leave the vistapool
            # entry in place and try again on the next HA restart. Don't count
            # as failure — it's an expected, recoverable state.
            _LOGGER.info(
                "Migration deferred for %s: %s — will retry on next restart",
                old_entry.title,
                exc,
            )
            summary["errors"].append(
                f"{old_entry.title}: deferred (controller offline)"
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception(
                "Cross-domain migration failed for vistapool entry %s",
                old_entry.entry_id,
            )
            summary["entries_failed"] += 1
            summary["errors"].append(f"{old_entry.title}: {err}")

    return summary


class _DeferredMigration(Exception):
    """Raised when v1→v2 prelude defers because the controller is offline."""


async def migrate_single_entry_cross_domain(
    hass: HomeAssistant, old_entry: ConfigEntry
) -> int:
    """Migrate one vistapool entry to neopool. Returns migrated entity count.

    Performs the **v2 → v3** step ("neopool domain rename"). When the
    legacy entry is still at v1, Step 0 first runs the v1 → v2 prelude on
    the vistapool entry in-place (same code path as HA-driven
    ``async_migrate_entry``). The final v3 → v4 marker bump is left to
    HA-driven ``async_migrate_entry`` during Step 5's setup, keeping
    each migration step in its own one-job function.

    CRITICAL ORDERING: entity_registry retarget MUST happen BEFORE
    `hass.config_entries.async_add(new_entry)`. async_add synchronously runs
    `async_setup_entry` → forward to platforms → `async_add_entities`, and
    that lookup uses (entity_domain, platform, unique_id). If platform is
    still "vistapool" when the new neopool entry is set up, HA creates
    DUPLICATE entity_registry rows under platform="neopool".
    """
    # ── Step 0: v1→v2 prelude (only if entry is still at v1) ─────────────
    # Reuses the existing serial-based unique_id migration with
    # source_domain="vistapool" so device_registry lookup finds the
    # legacy device tuple.
    if old_entry.version < 2:
        v2_ok = await _migrate_v1_to_v2(hass, old_entry, source_domain=OLD_DOMAIN)
        if not v2_ok:
            # _migrate_v1_to_v2 returned False → unrecoverable error
            # (e.g., duplicate serial detected). Surface as a regular failure.
            raise RuntimeError("v1→v2 prelude failed (see previous log entries)")
        if old_entry.version < 2:
            # Prelude returned True but didn't bump version → controller
            # was offline. Defer the whole cross-domain step.
            raise _DeferredMigration("controller offline; v1→v2 prelude deferred")

    # ── Step 1: Unload old vistapool entry ───────────────────────────────
    # async_update_entity_platform refuses entities that still have a state
    # object in hass.states (HA core entity_registry.py L1933-1936). Unloading
    # the entry removes the platform's entities, which in turn removes their
    # state objects via Entity.async_remove (HA core entity.py).
    #
    # We unconditionally call async_unload (not gated on state == LOADED)
    # because:
    #   * a SETUP_ERROR entry can still have stale entity_registry rows
    #     loaded from a previous successful boot
    #   * a NOT_LOADED entry returns immediately so the call is cheap
    #
    # If unload returns False (the integration's async_unload_entry refused
    # or raised), abort the migration loudly — running the retarget against
    # still-loaded entities would produce the cryptic "Only entities that
    # haven't been loaded can be migrated" error.
    unloaded = await hass.config_entries.async_unload(old_entry.entry_id)
    if not unloaded:
        raise RuntimeError(
            f"Failed to unload legacy entry {old_entry.entry_id!r} — "
            "cannot proceed with migration. Restart Home Assistant and "
            "try again."
        )

    # Yield once so any pending entity-removal callbacks scheduled by the
    # unload above get a chance to run before we read entity_sources().
    # In practice async_unload already awaits all platform unloads, but a
    # single async sleep(0) is cheap insurance against future HA core
    # changes that move entity removal to a separate task.
    await asyncio.sleep(0)

    # ── Step 2: Construct + register new ConfigEntry (without setup) ─────
    # We need new_entry.entry_id to retarget entities. We CANNOT call
    # `hass.config_entries.async_add()` yet — that synchronously triggers
    # `async_setup_entry` → forward to platforms → `async_add_entities`,
    # which would create duplicate entity_registry rows (the existing rows
    # are still under platform="vistapool", so HA's dedup key
    # `(entity_domain, platform, unique_id)` doesn't see the collision).
    #
    # But we ALSO can't leave the entry unregistered: HA core entity_registry
    # `_validate_item` (L1044-1048) refuses `async_update_entity_platform`
    # if `hass.config_entries.async_get_entry(new_config_entry_id)` returns
    # None.
    #
    # Resolve the paradox by splitting `async_add` into its two halves:
    #   1. Register the entry in `_entries` so the validator finds it.
    #   2. Call `async_setup` ourselves AFTER the retarget completes
    #      (Step 5 below).
    # This mirrors what `async_add` does internally (HA core
    # config_entries.py L2180-2191) minus the `async_setup` call. Safe
    # because between Step 2 and Step 5 nothing else triggers a setup
    # for this entry (no discovery, no user action).
    new_entry = ConfigEntry(
        # Cross-domain migration is the v2 → v3 step ("neopool domain rename"),
        # nothing more. The v3 → v4 marker bump runs afterwards when Step 5
        # invokes async_setup → HA core sees entry.version=3 != ConfigFlow
        # VERSION (=CURRENT_VERSION) and dispatches to async_migrate_entry,
        # which performs the bump. Keeping each migration step in its own
        # one-job function avoids the "Migrating … from v4 to v2" log noise
        # we used to emit when we built the new entry directly at v4 and HA
        # then re-ran the v1→v2 prelude on it.
        version=3,
        minor_version=1,
        domain=DOMAIN,
        title=old_entry.title,
        data=dict(old_entry.data),
        # Preserve the original source (SOURCE_USER for entries created
        # through the UI, etc.) — overriding it would change reconfigure
        # behavior and how HA presents the entry in the UI.
        source=old_entry.source,
        unique_id=old_entry.unique_id,
        options=dict(old_entry.options),
        discovery_keys=MappingProxyType({}),
        subentries_data=(),
    )
    # Private API: register the entry without invoking async_setup. Mirrors
    # the first three lines of `ConfigEntries.async_add` (HA core
    # config_entries.py L2187-2189). Wrapped in a helper so tests can mock
    # it without touching `_entries` directly.
    _register_entry_without_setup(hass, new_entry)

    # Steps 3-6 may fail (registry retarget collision, platform setup
    # error, etc.). The new_entry is already in `hass.config_entries._entries`
    # at this point, so any failure must remove it — otherwise we leak a
    # ghost entry that has no platforms set up but would still appear in
    # `async_entries(DOMAIN)` and could land in `.storage/core.config_entries`
    # the next time something else triggers a save.
    try:
        # ── Step 3: Retarget entity_registry rows ────────────────────────
        # Change platform from "vistapool" to "neopool". entity_id and
        # unique_id are preserved → recorder history (states + statistics)
        # follows automatically because those tables key on entity_id strings,
        # not on platform/domain.
        entity_registry = er.async_get(hass)
        candidates = [
            e
            for e in entity_registry.entities.values()
            if e.platform == OLD_DOMAIN and e.config_entry_id == old_entry.entry_id
        ]

        # async_update_entity_platform refuses to migrate any entity that still
        # has a non-UNKNOWN state object in hass.states (HA core entity_registry
        # L1933-1936). async_unload_platforms is supposed to remove those, but
        # in practice we still hit the check — most likely recorder restoring
        # the last known state from the database, or a stray async callback
        # that repopulated the state after unload returned. Defensively wipe
        # any lingering state objects for our candidates before retargeting.
        stale_states = [
            e.entity_id for e in candidates if hass.states.get(e.entity_id) is not None
        ]
        if stale_states:
            _LOGGER.debug(
                "Removing %d stale state object(s) before retarget: %s",
                len(stale_states),
                stale_states,
            )
            for entity_id in stale_states:
                hass.states.async_remove(entity_id)

        applied: list[tuple[str, str | None]] = []
        for re_entry in candidates:
            try:
                entity_registry.async_update_entity_platform(
                    re_entry.entity_id,
                    new_platform=DOMAIN,
                    new_config_entry_id=new_entry.entry_id,
                    # No new_unique_id → keeps old unique_id intact.
                )
                applied.append((re_entry.entity_id, re_entry.unique_id))
            except ValueError as exc:
                _LOGGER.error(
                    "Failed to retarget %s: %s — rolling back",
                    re_entry.entity_id,
                    exc,
                )
                for ent_id, _uid in applied:
                    try:
                        entity_registry.async_update_entity_platform(
                            ent_id,
                            OLD_DOMAIN,
                            new_config_entry_id=old_entry.entry_id,
                        )
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception("Rollback failed for %s", ent_id)
                raise

        # ── Step 4: Retarget device_registry ─────────────────────────────
        # Order matters: ADD new_entry_id BEFORE REMOVE old_entry_id, otherwise
        # the device may be auto-deleted (HA core checks if the device's
        # config_entries set becomes empty during remove).
        device_registry = dr.async_get(hass)
        devices = list(
            dr.async_entries_for_config_entry(device_registry, old_entry.entry_id)
        )
        for device in devices:
            # 4a: Add new entry_id (so the device.config_entries set has both)
            device_registry.async_update_device(
                device.id,
                add_config_entry_id=new_entry.entry_id,
            )
            # 4b: Update identifiers (vistapool, X) → (neopool, X)
            new_identifiers = {
                (DOMAIN if d == OLD_DOMAIN else d, ident)
                for d, ident in device.identifiers
            }
            if new_identifiers != device.identifiers:
                device_registry.async_update_device(
                    device.id,
                    new_identifiers=new_identifiers,
                )
            # 4c: Remove old entry_id (safe — device has new entry_id too)
            device_registry.async_update_device(
                device.id,
                remove_config_entry_id=old_entry.entry_id,
            )

        # ── Step 5: Set up the new entry ─────────────────────────────────
        # The entry was registered in `_entries` in Step 2 (without setup) so
        # that the entity_registry validator would accept the retarget. Now
        # that the retarget is done, run setup. This synchronously calls
        # `async_setup_entry` → forward to platforms → `async_add_entities`.
        # The platform lookup finds the already-retargeted (sensor, neopool, X)
        # rows and reuses them — no duplicates are created.
        await _setup_registered_entry(hass, new_entry)

        # ── Step 6: Remove old vistapool entry ───────────────────────────
        await hass.config_entries.async_remove(old_entry.entry_id)
    except BaseException:
        # Migration aborted at some point after Step 2's registration. The
        # new entry's entity_registry retargets may have been rolled back by
        # Step 3's inner handler, but the registration itself (the row in
        # `hass.config_entries._entries`) is ours to clean up. Without this,
        # a failed migration leaves a ghost entry visible to
        # `async_entries(DOMAIN)` and async_setup that does nothing useful.
        #
        # Catch BaseException so the cleanup also runs on cancellations
        # (e.g. HA shutting down mid-migration). We re-raise unconditionally,
        # so callers still see the original failure.
        _unregister_entry_without_save(hass, new_entry)
        raise

    _LOGGER.info(
        "Migrated vistapool entry %r (%d entities) to neopool entry %s",
        old_entry.title,
        len(applied),
        new_entry.entry_id,
    )
    return len(applied)


def _register_entry_without_setup(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register a ConfigEntry in `_entries` without invoking async_setup.

    Mirrors the first three lines of `ConfigEntries.async_add` (HA core
    config_entries.py L2187-2189) but skips the `await async_setup` and
    `_async_schedule_save` calls. Used during cross-domain migration to
    make the entry visible to `entity_registry._validate_item` (which
    refuses to retarget entities to an unknown config entry) before any
    platforms have been set up.

    Persisting to disk is deferred until `_setup_registered_entry` runs,
    so an aborted migration leaves no stale row in
    `.storage/core.config_entries`.
    """
    hass.config_entries._entries[entry.entry_id] = entry  # noqa: SLF001
    hass.config_entries.async_update_issues()
    hass.config_entries._async_dispatch(  # noqa: SLF001
        ConfigEntryChange.ADDED, entry
    )


def _unregister_entry_without_save(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reverse of `_register_entry_without_setup` — drop entry from `_entries`.

    Called from the cross-domain migration error path so that a failure
    after Step 2's registration doesn't leave a ghost entry in
    `hass.config_entries._entries`. Without this, a partially-completed
    migration would leak an unsetup neopool entry that:
      * still appears in `async_entries(DOMAIN)`,
      * has no platforms loaded (would no-op on `async_setup_entry`), and
      * could land in `.storage/core.config_entries` the next time
        another integration triggers `_async_schedule_save`.

    Mirrors `ConfigEntries._async_remove`'s book-keeping but without
    invoking `async_unload` (the entry never got set up) or scheduling
    a save (Step 2 deliberately deferred saving until Step 5; if we got
    here, the save call never ran). The matching REMOVED dispatch keeps
    HACS / frontend listeners consistent with the ADDED we sent earlier.

    Idempotent — silent if the entry is already gone (e.g. test mocks
    that didn't actually populate `_entries`).
    """
    if hass.config_entries._entries.get(entry.entry_id) is None:  # noqa: SLF001
        return
    del hass.config_entries._entries[entry.entry_id]  # noqa: SLF001
    hass.config_entries.async_update_issues()
    hass.config_entries._async_dispatch(  # noqa: SLF001
        ConfigEntryChange.REMOVED, entry
    )


async def _setup_registered_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Run setup for an entry registered via `_register_entry_without_setup`.

    Mirrors the second half of `ConfigEntries.async_add` (HA core
    config_entries.py L2190-2191): invoke `async_setup` and schedule the
    entries store save. Calling this on an entry that wasn't registered
    first will fail inside `async_setup`.
    """
    await hass.config_entries.async_setup(entry.entry_id)
    hass.config_entries._async_schedule_save()  # noqa: SLF001


async def async_cleanup_old_folder(hass: HomeAssistant) -> bool:
    """Remove the legacy `custom_components/vistapool/` directory if present.

    HACS installs the new release into `custom_components/neopool/` (per the
    new manifest domain), but does not touch the previous `vistapool/`
    directory left over from the v2.x release. With no vistapool config
    entries remaining (cross-domain migration moved them all to neopool),
    that directory is dead weight; on HA 2026.6+ it would also keep tripping
    the "custom integration shadows core integration" warning.

    Safety:
      * Refuse if `custom_components/vistapool/` does not exist (nothing to do).
      * Refuse if the directory has no `manifest.json` (looks foreign).
      * Refuse if the manifest's documentation/issue_tracker URL doesn't
        match our repo (an unrelated `vistapool` fork — leave it alone).

    Returns True if the directory was deleted or was already absent. Returns
    False on safety refusal or filesystem error; callers should surface that
    in the repair issue so the user can clean up manually.
    """
    config_dir = Path(hass.config.path("custom_components/vistapool"))
    if not config_dir.exists():
        return True  # Nothing to clean up — fresh install or already removed

    manifest_path = config_dir / "manifest.json"
    if not manifest_path.is_file():
        _LOGGER.warning(
            "Legacy folder %s exists but has no manifest.json — refusing to delete",
            config_dir,
        )
        return False

    try:
        manifest = await hass.async_add_executor_job(_read_manifest_json, manifest_path)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Cannot read legacy manifest %s: %s — refusing to delete",
            manifest_path,
            err,
        )
        return False

    documentation = str(manifest.get("documentation", ""))
    issue_tracker = str(manifest.get("issue_tracker", ""))
    if LEGACY_REPO_URL not in documentation and LEGACY_REPO_URL not in issue_tracker:
        _LOGGER.warning(
            "Legacy folder %s does not match our integration "
            "(documentation=%r, issue_tracker=%r) — refusing to delete",
            config_dir,
            documentation,
            issue_tracker,
        )
        return False

    try:
        await hass.async_add_executor_job(shutil.rmtree, str(config_dir))
    except Exception as err:  # noqa: BLE001
        _LOGGER.error(
            "Failed to delete legacy folder %s: %s — please remove it manually",
            config_dir,
            err,
        )
        return False

    _LOGGER.info("Removed legacy folder %s", config_dir)
    return True


def _read_manifest_json(path: Path) -> dict:
    """Read a manifest.json file (executor-safe — runs blocking I/O)."""
    return json.loads(path.read_text(encoding="utf-8"))


async def async_cleanup_legacy_files(hass: HomeAssistant) -> None:
    """Remove .py modules whose implementation moved to the neopool-modbus PyPI library.

    HACS extracts ZIP releases on top of the existing
    `custom_components/neopool/` directory without deleting files that no
    longer exist in the new release. After upgrading to v4.0.0 the modules
    listed in :data:`LEGACY_FILES_REMOVED_IN_V4` remain on disk as stale
    duplicates of the library code; this routine removes both the .py
    sources and any matching `__pycache__/<stem>.cpython-*.pyc` byte-code
    so a leftover cannot shadow the library on the next reload (Python
    can import a module from .pyc alone if the .py is missing).

    The function is idempotent: each unlink swallows :exc:`FileNotFoundError`
    so it is safe to call on every integration setup, even concurrently
    for multiple config entries. Other :exc:`OSError` failures are logged
    individually and the cleanup continues with the remaining files so
    the user can finish the cleanup manually.
    """
    integration_dir = Path(hass.config.path(f"custom_components/{DOMAIN}"))
    pycache_dir = integration_dir / "__pycache__"

    def _purge_legacy_files() -> list[tuple[Path, OSError]]:
        """Delete legacy sources and their bytecode. Return [(path, error), ...]."""
        failures: list[tuple[Path, OSError]] = []

        def _unlink(path: Path) -> None:
            try:
                path.unlink()
            except FileNotFoundError:
                # Either never existed or another concurrent setup removed
                # it first — both are fine.
                return
            except OSError as err:
                failures.append((path, err))
                return
            _LOGGER.info("Removed legacy file %s", path)

        for filename in LEGACY_FILES_REMOVED_IN_V4:
            stem = filename.removesuffix(".py")
            _unlink(integration_dir / filename)
            if pycache_dir.is_dir():
                # `<stem>.cpython-XYZ.pyc` for any Python version
                for pyc in pycache_dir.glob(f"{stem}.cpython-*.pyc"):
                    _unlink(pyc)
        return failures

    failures = await hass.async_add_executor_job(_purge_legacy_files)
    for path, err in failures:
        _LOGGER.warning(
            "Failed to remove legacy file %s: %s — please remove it manually",
            path,
            err,
        )
