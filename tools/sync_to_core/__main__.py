"""Entry point for ``python -m tools.sync_to_core``.

Wires together the copy walk, the per-file transforms, the manifest
rewrite, and the optional license/pragma strippers. Output goes to
``dist/neopool/`` — gitignored — so the user can compare it against the
core repo manually.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
import shutil
import sys

from .config import (
    DEFAULT_STRIP_LICENSE,
    DEFAULT_STRIP_PRAGMA,
    DEST_INTEGRATION,
    DEST_SNAPSHOTS,
    DEST_TESTS,
    DIST_ROOT,
    EXCLUDE_INTEGRATION_DIRS,
    EXCLUDE_INTEGRATION_FILES,
    EXCLUDE_TEST_DIRS,
    EXCLUDE_TEST_FILES,
    SOURCE_INTEGRATION,
    SOURCE_TESTS,
)
from .manifest import transform_manifest
from .transformers import transform_python, transform_yaml

# ---------------------------------------------------------------------------
# Walk helpers
# ---------------------------------------------------------------------------


def _iter_files(
    src: Path, *, exclude_files: Iterable[str], exclude_dirs: Iterable[str]
) -> Iterable[Path]:
    """Yield every file under ``src`` that is not in an excluded slot.

    Excludes are matched by basename only — that's enough for our layout
    and avoids surprises if the script is ever run from a different cwd.
    """
    excluded_files = set(exclude_files)
    excluded_dirs = set(exclude_dirs)
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        if path.name in excluded_files:
            continue
        if any(part in excluded_dirs for part in path.relative_to(src).parts):
            continue
        yield path


def _write(dest: Path, content: str | bytes) -> None:
    """Write ``content`` to ``dest``, creating parents as needed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        dest.write_text(content, encoding="utf-8")
    else:
        dest.write_bytes(content)


# ---------------------------------------------------------------------------
# Per-file dispatch
# ---------------------------------------------------------------------------


def _process_integration_file(
    src: Path, dest: Path, *, strip_license: bool, strip_pragma: bool
) -> None:
    if src.name == "manifest.json":
        _write(dest, transform_manifest(src.read_text(encoding="utf-8")))
        return
    if src.suffix == ".py":
        transformed = transform_python(
            src.read_text(encoding="utf-8"),
            strip_license=strip_license,
            strip_pragma=strip_pragma,
        )
        _write(dest, transformed)
        return
    if src.suffix in (".yaml", ".yml"):
        transformed = transform_yaml(
            src.read_text(encoding="utf-8"),
            strip_license=strip_license,
        )
        _write(dest, transformed)
        return
    # Everything else (icons.json, strings.json) is copied verbatim — we
    # may add transforms later, but for now the custom and core versions
    # are intended to match.
    shutil.copy2(src, dest)


def _process_test_file(
    src: Path, dest: Path, *, strip_license: bool, strip_pragma: bool
) -> None:
    if src.suffix == ".py":
        transformed = transform_python(
            src.read_text(encoding="utf-8"),
            strip_license=strip_license,
            strip_pragma=strip_pragma,
        )
        _write(dest, transformed)
        return
    # Snapshots (*.ambr) and other fixtures: verbatim copy, but route
    # `tests/snapshots/` into `dist/.../snapshots/` so the layout
    # matches HA core.
    rel = src.relative_to(SOURCE_TESTS)
    if rel.parts and rel.parts[0] == "snapshots":
        dest = DEST_SNAPSHOTS / Path(*rel.parts[1:])
    _write(dest, src.read_bytes())


# ---------------------------------------------------------------------------
# Top-level sync
# ---------------------------------------------------------------------------


def sync(
    *,
    clean: bool,
    strip_license: bool,
    strip_pragma: bool,
) -> None:
    """Build the dist/ tree from the current custom HACS sources."""
    if clean and DIST_ROOT.exists():
        shutil.rmtree(DIST_ROOT)

    integration_count = 0
    for src in _iter_files(
        SOURCE_INTEGRATION,
        exclude_files=EXCLUDE_INTEGRATION_FILES,
        exclude_dirs=EXCLUDE_INTEGRATION_DIRS,
    ):
        rel = src.relative_to(SOURCE_INTEGRATION)
        dest = DEST_INTEGRATION / rel
        _process_integration_file(
            src, dest, strip_license=strip_license, strip_pragma=strip_pragma
        )
        integration_count += 1

    test_count = 0
    for src in _iter_files(
        SOURCE_TESTS,
        exclude_files=EXCLUDE_TEST_FILES,
        exclude_dirs=EXCLUDE_TEST_DIRS,
    ):
        rel = src.relative_to(SOURCE_TESTS)
        dest = DEST_TESTS / rel
        _process_test_file(
            src, dest, strip_license=strip_license, strip_pragma=strip_pragma
        )
        test_count += 1

    print(f"  integration files written: {integration_count}")
    print(f"  test files written:        {test_count}")
    print(f"  output:                    {DIST_ROOT}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.sync_to_core",
        description="Generate a core-publishable mirror of the custom HACS integration.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=True,
        help="Wipe dist/ before writing (default: on).",
    )
    parser.add_argument(
        "--no-clean",
        dest="clean",
        action="store_false",
        help="Keep existing dist/ contents and overwrite in place.",
    )
    parser.add_argument(
        "--strip-license",
        dest="strip_license",
        action="store_true",
        default=DEFAULT_STRIP_LICENSE,
        help="Drop the leading copyright/license comment block (default: on — core does not use them).",
    )
    parser.add_argument(
        "--keep-license",
        dest="strip_license",
        action="store_false",
        help="Preserve the per-file copyright/license header.",
    )
    parser.add_argument(
        "--strip-pragma",
        dest="strip_pragma",
        action="store_true",
        default=DEFAULT_STRIP_PRAGMA,
        help='Drop "# pragma: no cover" trailing comments (default: off).',
    )
    parser.add_argument(
        "--keep-pragma",
        dest="strip_pragma",
        action="store_false",
        help='Preserve "# pragma: no cover" markers.',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    print("syncing custom HACS sources to dist/ for core …")
    print(
        f"  clean={args.clean}  "
        f"strip_license={args.strip_license}  "
        f"strip_pragma={args.strip_pragma}"
    )
    sync(
        clean=args.clean,
        strip_license=args.strip_license,
        strip_pragma=args.strip_pragma,
    )
    print("done.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI dispatch
    sys.exit(main())
