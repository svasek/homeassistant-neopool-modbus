"""manifest.json transform: drop HACS-only fields, sort keys."""

from __future__ import annotations

import json
from typing import Any

from .config import MANIFEST_DROP_KEYS


def transform_manifest(raw: str) -> str:
    """Return a core-friendly manifest.json string from a HACS one.

    - Drops keys listed in ``MANIFEST_DROP_KEYS`` (HACS-only).
    - Re-emits keys in alphabetical order, matching how core/scripts/
      hassfest stores manifests after running ``python -m script.hassfest``.
    """
    manifest: dict[str, Any] = json.loads(raw)
    cleaned = {k: v for k, v in manifest.items() if k not in MANIFEST_DROP_KEYS}
    ordered = {k: cleaned[k] for k in sorted(cleaned)}
    return json.dumps(ordered, indent=2) + "\n"
