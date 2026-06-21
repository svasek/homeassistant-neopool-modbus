"""Source-to-source transforms applied to each Python file.

Everything is plain string/regex work — no AST. The transforms are
small, idempotent, and order-independent at the file level, which keeps
the script easy to reason about when something doesn't match.
"""

from __future__ import annotations

import re

from .config import (
    EXCLUDE_INTEGRATION_FILES,
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

# After a strip, three or more consecutive blank lines collapse to two.
# Saves us from having to be surgical about which whitespace each
# stripper consumes — we just normalise the result at the end.
_TRIPLE_BLANK = re.compile(r"\n{4,}")

# Match the blank line that often gets left behind right after a
# function/method docstring once a CUSTOM-ONLY block was the very first
# thing inside that function. Implemented as a line-walk in
# :func:`collapse_blank_after_func_docstring` rather than a regex —
# multi-line `def` signatures plus DOTALL would invite catastrophic
# backtracking, and the line-level check is plenty fast for our scale.
_DOCSTRING_LINE = re.compile(r'^[ \t]+""".*"""[ \t]*$')

# A `# pragma: no cover` trailing comment — we strip the comment but
# keep the code on that line. Whitespace before the `#` is also eaten
# so we don't leave dangling spaces.
_PRAGMA_NO_COVER = re.compile(r"[ \t]*#[ \t]*pragma:[ \t]*no cover[^\n]*")

# Matches a full-line comment (optional leading whitespace, then `#`).
# Used by strip_inline_comments to drop standalone comment lines from
# test files — core reviewers expect comment-free test code.
_FULL_LINE_COMMENT = re.compile(r"^[ \t]*#[^\n]*\n?", flags=re.MULTILINE)

# Matches a trailing inline comment on a code line. We only strip the
# comment portion, not the code. The negative lookbehind avoids matching
# `#` inside strings — good enough for our controlled test sources.
_TRAILING_COMMENT = re.compile(r"[ \t]+#[^\n]*")


# Module names we strip imports for, derived from EXCLUDE_INTEGRATION_FILES
# (e.g. {"migration"} → drop `from .migration import …` blocks). Using the
# exclude list as the source of truth keeps the two in lockstep — adding
# a new HACS-only module to EXCLUDE_INTEGRATION_FILES automatically makes
# the sync script remove its imports too.
_EXCLUDED_MODULES: frozenset[str] = frozenset(
    p[: -len(".py")] for p in EXCLUDE_INTEGRATION_FILES if p.endswith(".py")
)


def _excluded_import_pattern(module: str) -> re.Pattern[str]:
    """Match a `from .{module} import …` block (single- or multi-line).

    Captures any leading explanatory comments and the parenthesised or
    unparenthesised name list, plus a trailing newline. Surrounding
    blank lines are normalised by ``_collapse_blank_lines`` afterwards
    so we don't have to be surgical here.
    """
    return re.compile(
        # Optional contiguous comment lines directly above (description
        # of the import — they make no sense without the import below).
        r"(?:^[ \t]*#[^\n]*\n)*"
        # The import statement itself.
        rf"^[ \t]*from[ \t]+\.{re.escape(module)}[ \t]+import[ \t]+"
        # Either a parenthesised multi-line name list…
        r"(?:\([^)]*\)|[^\n]*)"
        # …or a single-line one. Trailing newline only — the
        # blank-line collapser cleans up the rest.
        r"[ \t]*\n",
        flags=re.MULTILINE,
    )


_EXCLUDED_IMPORT_PATTERNS = tuple(
    _excluded_import_pattern(module) for module in _EXCLUDED_MODULES
)


def strip_custom_only_blocks(source: str) -> str:
    """Remove every `# CUSTOM-ONLY START` … `# CUSTOM-ONLY END` block."""
    return _CUSTOM_ONLY_BLOCK.sub("", source)


def strip_excluded_module_imports(source: str) -> str:
    """Remove ``from .<module> import …`` for every excluded module.

    Excluded modules are the ``.py`` files in
    ``EXCLUDE_INTEGRATION_FILES`` — they don't ship to core, so importing
    from them would leave a dangling import. The matching strip in
    `CUSTOM-ONLY` markers on the call sites is still needed; this helper
    just keeps the import block out of the marker noise.
    """
    for pattern in _EXCLUDED_IMPORT_PATTERNS:
        source = pattern.sub("", source)
    return source


def collapse_blank_lines(source: str) -> str:
    """Collapse runs of 3+ consecutive newlines down to 2.

    PEP 8 allows up to two blank lines between top-level constructs;
    after stripping marker blocks and excluded imports we sometimes end
    up with three in a row. Normalising here lets every other transform
    stay simple instead of trying to be precise about whitespace.
    """
    return _TRIPLE_BLANK.sub("\n\n\n", source)


def collapse_blank_after_func_docstring(source: str) -> str:
    """Drop the blank line that some strips leave between a function docstring and its body.

    When a `CUSTOM-ONLY` block was the first thing inside a function and
    we removed it, what remains is the docstring followed by a blank
    line and then the first real statement. Ruff format treats that as
    a legitimate style and refuses to fix it, but it reads as a glitch
    in the otherwise smooth output — collapse it back to the natural
    "docstring, then code on the next line" shape.

    Class docstrings followed by a blank line before class-level
    attributes are *not* affected — the walk only triggers when the
    docstring's nearest preceding non-comment line is a ``def``/``async
    def`` header (possibly continued onto multiple lines for long
    signatures, ending in ``:``).
    """
    lines = source.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        # Look for: (def header ending in `:`) → docstring → blank → indented code
        if (
            _DOCSTRING_LINE.match(line)
            and i + 1 < len(lines)
            and lines[i + 1].strip() == ""
            and i + 2 < len(lines)
            and lines[i + 2].lstrip() != lines[i + 2]  # indented
            and lines[i + 2].strip() != ""
            and _is_function_docstring(lines, i)
        ):
            # Skip the blank line at i + 1.
            i += 2
            continue
        i += 1
    return "".join(out)


def _is_function_docstring(lines: list[str], docstring_idx: int) -> bool:
    """Return True if the docstring at ``docstring_idx`` belongs to a ``def``.

    Walks backwards from the docstring line, skipping any continuation
    lines of a multi-line ``def`` signature (lines that don't end in
    ``:``), until it reaches a line ending in ``:``. The owner is a
    function iff that owner-line starts with ``def`` or ``async def``.
    """
    j = docstring_idx - 1
    while j >= 0 and not lines[j].rstrip().endswith(":"):
        j -= 1
    if j < 0:
        return False
    # Found the line ending in `:`. Walk backwards through any
    # continuation lines (long signatures wrap onto multiple lines)
    # until we hit the actual `def`/`async def`/`class`/etc. keyword.
    owner = lines[j].lstrip()
    while j > 0 and not (owner.startswith(("def ", "async def ", "class "))):
        j -= 1
        owner = lines[j].lstrip()
    return owner.startswith(("def ", "async def "))


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


def strip_inline_comments(source: str) -> str:
    """Remove all ``#``-style comments from Python source.

    Full-line comment lines (including section headers like ``# ---``) are
    dropped entirely. Trailing inline comments are stripped from code lines
    while leaving the code intact. Module/function/class docstrings are not
    touched — they are string literals, not comments.
    """
    source = _FULL_LINE_COMMENT.sub("", source)
    return _TRAILING_COMMENT.sub("", source)


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
    strip_comments: bool = False,
) -> str:
    """Run every transform on a single Python source string."""
    # Order matters: drop CUSTOM-ONLY blocks *first* so the auto-import
    # stripper sees a clean import section without dangling markers
    # interleaved with the imports it wants to remove.
    source = strip_custom_only_blocks(source)
    source = strip_excluded_module_imports(source)
    if strip_license:
        source = strip_license_header(source)
    if strip_pragma:
        source = strip_pragma_no_cover(source)
    if strip_comments:
        source = strip_inline_comments(source)
    source = collapse_blank_lines(source)
    source = collapse_blank_after_func_docstring(source)
    return apply_python_replacements(source)


def transform_yaml(source: str, *, strip_license: bool) -> str:
    """Run YAML-safe transforms on a single yaml source string.

    Only the license header and `CUSTOM-ONLY` marker blocks are touched
    here — both rely on `#` line comments, which YAML and Python share.
    The Python import replacements would be wrong inside YAML strings,
    so they are deliberately skipped.
    """
    source = strip_custom_only_blocks(source)
    if strip_license:
        source = strip_license_header(source)
    return collapse_blank_lines(source)


# Match a syrupy snapshot dict line like `        'scan_interval': 30,`
# (any indent, any scalar value before the trailing comma). Used to drop
# HACS-only entry-options keys from .ambr snapshots so the snapshot stays
# consistent with the stripped dist conftest fixtures.
_AMBR_HACS_ONLY_OPTIONS = re.compile(
    r"^[ \t]+'(?:scan_interval|unlock_advanced|enable_backwash_option|"
    r"dev_overrides|dev_overrides_enabled)':[^\n]*\n",
    flags=re.MULTILINE,
)


def transform_snapshot(source: str) -> str:
    """Strip HACS-only entry-options keys from a syrupy .ambr snapshot.

    The snapshot is otherwise copied verbatim — only the lines whose key
    matches a HACS-only options name are removed. Leaves indentation,
    surrounding context and ordering intact.
    """
    return _AMBR_HACS_ONLY_OPTIONS.sub("", source)
