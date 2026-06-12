"""manifest.json transform: drop HACS-only fields, sort keys."""

from __future__ import annotations

import json
from typing import Any

from .config import MANIFEST_DROP_KEYS, MANIFEST_OVERRIDES
from .json_format import format_compact

# Hassfest convention (verified against esphome, peblar, mqtt, shelly,
# hue, tplink): `domain` first, then `name`, then every other key in
# alphabetical order. The custom repo follows the same shape so this
# transform is a no-op on key order — only the HACS-only keys (version,
# issue_tracker) are dropped.
_LEADING_KEYS: tuple[str, ...] = ("domain", "name")


def transform_manifest(raw: str) -> str:
    """Return a core-friendly manifest.json string from a HACS one.

    - Drops keys listed in ``MANIFEST_DROP_KEYS`` (HACS-only).
    - Applies ``MANIFEST_OVERRIDES`` so fields that differ between the
      HACS and core packaging (``documentation`` URL, ``quality_scale``
      tier) get rewritten to their core-canonical values without
      touching the custom source manifest.
    - Re-emits keys in hassfest order: ``domain`` and ``name`` first,
      then every remaining key alphabetically.
    - 2-space indent + trailing newline (core convention).
    - Compact-when-it-fits layout (see
      :func:`tools.sync_to_core.json_format.format_compact`) — short
      lists like ``["@svasek"]`` stay on one line, matching prettier's
      output that core uses for its own manifests.
    """
    manifest: dict[str, Any] = json.loads(raw)
    cleaned = {k: v for k, v in manifest.items() if k not in MANIFEST_DROP_KEYS}
    cleaned.update(MANIFEST_OVERRIDES)
    ordered: dict[str, Any] = {}
    for k in _LEADING_KEYS:
        if k in cleaned:
            ordered[k] = cleaned[k]
    for k in sorted(cleaned):
        if k not in ordered:
            ordered[k] = cleaned[k]
    return format_compact(ordered, indent="  ") + "\n"
