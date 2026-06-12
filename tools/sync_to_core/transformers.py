"""Source-to-source transforms applied to each Python file.

Everything is plain string/regex work — no AST. The transforms are
small, idempotent, and order-independent at the file level, which keeps
the script easy to reason about when something doesn't match.
"""

from __future__ import annotations

import re

from .config import (
    LICENSE_HEADER_PREFIX,
    PYTHON_REPLACEMENTS,
)

# Match `# CUSTOM-ONLY START` ... `# CUSTOM-ONLY END` (and the trailing
# newline of the END line) anywhere in the file. DOTALL so `.` spans
# newlines; non-greedy so adjacent blocks don't merge.
_CUSTOM_ONLY_BLOCK = re.compile(
    r"^[ \t]*#[ \t]*CUSTOM-ONLY START.*?#[ \t]*CUSTOM-ONLY END[^\n]*\n?",
    flags=re.DOTALL | re.MULTILINE,
)

# A `# pragma: no cover` trailing comment — we strip the comment but
# keep the code on that line. Whitespace before the `#` is also eaten
# so we don't leave dangling spaces.
_PRAGMA_NO_COVER = re.compile(r"[ \t]*#[ \t]*pragma:[ \t]*no cover[^\n]*")


def strip_custom_only_blocks(source: str) -> str:
    """Remove every `# CUSTOM-ONLY START` … `# CUSTOM-ONLY END` block."""
    return _CUSTOM_ONLY_BLOCK.sub("", source)


def strip_license_header(source: str) -> str:
    """Drop a leading copyright/license comment block, if present.

    The header is recognised by a first non-empty line that begins with
    ``LICENSE_HEADER_PREFIX``. From there, every contiguous line that
    starts with ``#`` (or is blank) is part of the header and is removed.
    A single blank line below the header is also consumed so the file
    starts cleanly with its docstring.
    """
    lines = source.splitlines(keepends=True)
    i = 0
    # Skip leading blank lines (rare, but tolerate them).
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines) or not lines[i].lstrip().startswith(LICENSE_HEADER_PREFIX):
        return source
    # Consume the comment block.
    while i < len(lines) and (
        lines[i].lstrip().startswith("#") or lines[i].strip() == ""
    ):
        # Stop at the first non-comment, non-blank line.
        if lines[i].strip() and not lines[i].lstrip().startswith("#"):
            break
        i += 1
    # Re-attach a single trailing blank if we landed on one — but the
    # join below skips up to here, so just drop everything before `i`.
    return "".join(lines[i:])


def strip_pragma_no_cover(source: str) -> str:
    """Drop trailing ``# pragma: no cover`` comments (keep the code)."""
    return _PRAGMA_NO_COVER.sub("", source)


def apply_python_replacements(source: str) -> str:
    """Apply every (old, new) pair from `PYTHON_REPLACEMENTS` in order."""
    for old, new in PYTHON_REPLACEMENTS:
        source = source.replace(old, new)
    return source


def transform_python(
    source: str,
    *,
    strip_license: bool,
    strip_pragma: bool,
) -> str:
    """Run every transform on a single Python source string."""
    source = strip_custom_only_blocks(source)
    if strip_license:
        source = strip_license_header(source)
    if strip_pragma:
        source = strip_pragma_no_cover(source)
    source = apply_python_replacements(source)
    return source
