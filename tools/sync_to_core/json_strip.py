"""Strip and reformat JSON files to match HA core's two conventions.

Two helpers cover both styles core uses (verified against esphome,
peblar, mqtt, shelly, hue, tplink — all six match):

- :func:`format_strings_style` — for ``strings.json`` and ``icons.json``:
  2-space indent, sorted keys, raw Unicode, trailing newline. Files
  authors edit by hand.
- :func:`format_translations_style` — for ``translations/<lang>.json``:
  4-space indent, sorted keys, raw Unicode, no trailing newline.
  (Upstream's en.json is ASCII-escaped because Lokalise defaults that
  way, but raw is byte-equivalent for the JSON parser and stays
  readable in editors and grep.)

Each helper accepts a ``paths`` argument — a list of dotted paths to
delete before re-emitting — so the same call can both strip the
HACS-only vistapool / migration keys and normalise the formatting.
Reformatting always runs even when ``paths`` is empty: that way an
ad-hoc edit in the custom repo (extra blank line, mixed indent, IDE
reordering) gets normalised on the next sync without touching the
source file.
"""

from __future__ import annotations

import json
from typing import Any

from .config import JSON_DROP_KEYS
from .json_format import format_compact


def _drop_path(obj: Any, path: tuple[str, ...]) -> None:
    """Mutate ``obj`` to remove the value at the dotted ``path``.

    Walks the path, popping the last segment off whichever container it
    lands in. Missing intermediate segments are tolerated — a path that
    no longer applies (e.g. after a previous strip) is a no-op rather
    than an error, so the strip table can stay slightly larger than
    what's actually present.
    """
    if not path:
        return
    *parents, last = path
    cursor = obj
    for segment in parents:
        if not isinstance(cursor, dict) or segment not in cursor:
            return
        cursor = cursor[segment]
    if isinstance(cursor, dict):
        cursor.pop(last, None)


def _strip_paths(raw: str, paths: tuple[str, ...]) -> Any:
    """Parse ``raw``, drop every dotted path in ``paths``, return the dict."""
    data = json.loads(raw)
    for path in paths:
        _drop_path(data, tuple(path.split(".")))
    return data


def _sort_recursive(value: Any) -> Any:
    """Return ``value`` with every nested ``dict`` keyed alphabetically."""
    if isinstance(value, dict):
        return {k: _sort_recursive(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_sort_recursive(v) for v in value]
    return value


def format_strings_style(raw: str, *, paths: tuple[str, ...] = ()) -> str:
    """Reformat ``raw`` (and optionally drop ``paths``) for `strings.json` / `icons.json`.

    Style convention (HA core, verified 2026-06-12 against esphome,
    peblar, mqtt, shelly, hue, tplink):

    - 2-space indent
    - alphabetically sorted keys
    - **raw** non-ASCII characters preserved (``ensure_ascii=False``)
    - prettier-like compact-when-it-fits layout (see
      :func:`tools.sync_to_core.json_format.format_compact`) — short
      single-element lists and tiny inline dicts collapse to one line
    - trailing newline

    These are human-edited files, so the output stays readable: shallow
    indent, native Unicode, line-final newline.
    """
    sorted_data = _sort_recursive(_strip_paths(raw, paths))
    return format_compact(sorted_data, indent="  ") + "\n"


def format_translations_style(
    raw: str,
    *,
    paths: tuple[str, ...] = (),
    escape_non_ascii: bool = False,
) -> str:
    """Reformat ``raw`` (and optionally drop ``paths``) for `translations/<lang>.json`.

    Style convention (HA core, same verification list as
    :func:`format_strings_style`):

    - 4-space indent
    - alphabetically sorted keys
    - **no** trailing newline

    Non-ASCII characters are emitted raw by default (readable in
    editors and grep). Pass ``escape_non_ascii=True`` to switch to
    ``\\uXXXX`` escapes — that's how upstream's Lokalise pipeline
    serialises `translations/en.json`, so opt in when a byte-for-byte
    diff against an existing upstream file matters. The parsed JSON
    is identical either way.
    """
    return json.dumps(
        _strip_paths(raw, paths),
        indent=4,
        ensure_ascii=escape_non_ascii,
        sort_keys=True,
    )


# Backwards-compatible aliases that keep the original strip-+-format
# call sites readable. They each pass `JSON_DROP_KEYS` as the default,
# which is the HACS-only paths to delete from `strings.json` and
# `translations/en.json`.
def strip_strings_json(raw: str, *, paths: tuple[str, ...] = JSON_DROP_KEYS) -> str:
    """Strip HACS-only paths from `strings.json` and reformat to core style."""
    return format_strings_style(raw, paths=paths)


def strip_translations_en_json(
    raw: str,
    *,
    paths: tuple[str, ...] = JSON_DROP_KEYS,
    escape_non_ascii: bool = False,
) -> str:
    """Strip HACS-only paths from `translations/en.json` and reformat to core style."""
    return format_translations_style(
        raw, paths=paths, escape_non_ascii=escape_non_ascii
    )
