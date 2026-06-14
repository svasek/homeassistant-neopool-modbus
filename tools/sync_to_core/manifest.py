"""manifest.json transform: drop HACS-only fields, sort keys."""

from __future__ import annotations

import json
import re
from typing import Any

from .config import MANIFEST_DROP_KEYS, MANIFEST_OVERRIDES, MANIFEST_PIN_REQUIREMENTS
from .json_format import format_compact

# Hassfest convention (verified against esphome, peblar, mqtt, shelly,
# hue, tplink): `domain` first, then `name`, then every other key in
# alphabetical order. The custom repo follows the same shape so this
# transform is a no-op on key order — only the HACS-only keys (version,
# issue_tracker) are dropped.
_LEADING_KEYS: tuple[str, ...] = ("domain", "name")

# Match a leading `>=` (and only `>=`) on a single requirement string.
# Anchored at the start so we don't touch composite specifiers like
# `foo>=1.0,<2.0` mid-string — those are intentional and shouldn't be
# silently rewritten to a pin.
_GTE_PIN_RE = re.compile(r"^([A-Za-z0-9._\-]+)>=([0-9][0-9A-Za-z.\-+]*)$")


def _pin_requirement(spec: str) -> str:
    """Rewrite a `pkg>=X.Y.Z` requirement string to `pkg==X.Y.Z`.

    Leaves any other shape (already-pinned, composite, extras, URL
    requirements) untouched — core convention is exact pin, but a
    composite specifier carrying an upper bound is the author's
    deliberate choice and not ours to overwrite.
    """
    match = _GTE_PIN_RE.match(spec)
    if match is None:
        return spec
    pkg, version = match.group(1), match.group(2)
    return f"{pkg}=={version}"


def transform_manifest(raw: str) -> str:
    """Return a core-friendly manifest.json string from a HACS one.

    - Drops keys listed in ``MANIFEST_DROP_KEYS`` (HACS-only).
    - Applies ``MANIFEST_OVERRIDES`` so fields that differ between the
      HACS and core packaging (``documentation`` URL, ``quality_scale``
      tier) get rewritten to their core-canonical values without
      touching the custom source manifest.
    - When ``MANIFEST_PIN_REQUIREMENTS`` is set, rewrites every
      ``pkg>=X.Y.Z`` entry under ``requirements`` to ``pkg==X.Y.Z``.
      Core integrations pin their library requirements to exact
      versions; the HACS source uses ``>=`` so HACS users pick up
      compatible upstream releases automatically.
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
    if MANIFEST_PIN_REQUIREMENTS:
        reqs = cleaned.get("requirements")
        if isinstance(reqs, list):
            cleaned["requirements"] = [
                _pin_requirement(r) if isinstance(r, str) else r for r in reqs
            ]
    ordered: dict[str, Any] = {}
    for k in _LEADING_KEYS:
        if k in cleaned:
            ordered[k] = cleaned[k]
    for k in sorted(cleaned):
        if k not in ordered:
            ordered[k] = cleaned[k]
    return format_compact(ordered, indent="  ") + "\n"
