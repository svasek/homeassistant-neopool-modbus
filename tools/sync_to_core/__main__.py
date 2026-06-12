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
import subprocess
import sys

from .config import (
    DEFAULT_ESCAPE_TRANSLATIONS,
    DEFAULT_STRIP_LICENSE,
    DEFAULT_STRIP_PRAGMA,
    DEST_INTEGRATION,
    DEST_SNAPSHOTS,
    DEST_TESTS,
    DIST_PARENT,
    DIST_ROOT,
    EXCLUDE_INTEGRATION_DIRS,
    EXCLUDE_INTEGRATION_FILES,
    EXCLUDE_TEST_DIRS,
    EXCLUDE_TEST_FILES,
    INCLUDE_TRANSLATION_FILES,
    RUFF_DIST_CONFIG,
    SOURCE_INTEGRATION,
    SOURCE_TESTS,
)
from .json_strip import (
    format_strings_style,
    strip_strings_json,
    strip_translations_en_json,
)
from .manifest import transform_manifest
from .transformers import transform_python, transform_yaml

# ---------------------------------------------------------------------------
# Walk helpers
# ---------------------------------------------------------------------------


def _iter_files(
    src: Path,
    *,
    exclude_files: Iterable[str],
    exclude_dirs: Iterable[str],
    include_translation_files: Iterable[str] | None = None,
) -> Iterable[Path]:
    """Yield every file under ``src`` that is not in an excluded slot.

    Excludes are matched by basename only — that's enough for our layout
    and avoids surprises if the script is ever run from a different cwd.

    ``include_translation_files`` is an allow-list applied to anything
    inside a ``translations/`` directory: only the listed basenames pass
    through, every other locale is silently skipped. Default ``None``
    means no filtering of the translations subtree.
    """
    excluded_files = set(exclude_files)
    excluded_dirs = set(exclude_dirs)
    translation_allow = (
        set(include_translation_files)
        if include_translation_files is not None
        else None
    )
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        if path.name in excluded_files:
            continue
        rel_parts = path.relative_to(src).parts
        if any(part in excluded_dirs for part in rel_parts):
            continue
        if (
            translation_allow is not None
            and "translations" in rel_parts
            and path.name not in translation_allow
        ):
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
    src: Path,
    dest: Path,
    *,
    strip_license: bool,
    strip_pragma: bool,
    escape_translations: bool,
) -> None:
    if src.name == "manifest.json":
        _write(dest, transform_manifest(src.read_text(encoding="utf-8")))
        return
    # Both files carry the vistapool / migration UI strings — strip
    # them, then re-emit each in its own core formatting convention:
    # `strings.json` is human-edited (2-indent, raw Unicode, trailing
    # newline) while `translations/en.json` is a Lokalise build artefact
    # (4-indent, ASCII-escaped, no trailing newline).
    if src.name == "strings.json":
        _write(dest, strip_strings_json(src.read_text(encoding="utf-8")))
        return
    if src.parent.name == "translations" and src.suffix == ".json":
        _write(
            dest,
            strip_translations_en_json(
                src.read_text(encoding="utf-8"),
                escape_non_ascii=escape_translations,
            ),
        )
        return
    # Other JSON files in the integration root (`icons.json`, future
    # `quality_scale.yaml` siblings) — no key stripping needed, but
    # reformat anyway so an ad-hoc edit (mixed indent, IDE-reordered
    # keys) gets normalised to the core convention here. Cheap defence
    # against the source drifting silently.
    if src.suffix == ".json":
        _write(dest, format_strings_style(src.read_text(encoding="utf-8")))
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
    # Everything else (icons.json, services.yaml were already routed
    # above) is copied verbatim — we may add transforms later, but for
    # now the custom and core versions are intended to match.
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
    escape_translations: bool,
) -> None:
    """Build the dist/ tree from the current custom HACS sources."""
    if clean and DIST_ROOT.exists():
        shutil.rmtree(DIST_ROOT)

    integration_count = 0
    for src in _iter_files(
        SOURCE_INTEGRATION,
        exclude_files=EXCLUDE_INTEGRATION_FILES,
        exclude_dirs=EXCLUDE_INTEGRATION_DIRS,
        # Allow-list inside translations/: only en.json reaches dist;
        # any other locale (cs, de, …) is dropped. Lokalise rebuilds
        # those after the integration lands in core.
        include_translation_files=INCLUDE_TRANSLATION_FILES,
    ):
        rel = src.relative_to(SOURCE_INTEGRATION)
        dest = DEST_INTEGRATION / rel
        _process_integration_file(
            src,
            dest,
            strip_license=strip_license,
            strip_pragma=strip_pragma,
            escape_translations=escape_translations,
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


def _run_ruff_format(*, quiet: bool) -> None:
    """Run ``ruff format`` and ``ruff check --fix`` over the dist tree.

    The strippers are deliberately whitespace-naive — runs of blank
    lines, dangling separators around removed imports, etc. — so we
    delegate the final formatting to ruff. We also run ``ruff check
    --fix`` to drop imports that became unused once their only call
    site was stripped (e.g. ``CONF_HOST`` after the legacy data→options
    block disappears) and to re-sort the import block.

    Both passes run with ``ruff_dist.toml`` (a snapshot of HA core's
    ruff config) copied to ``dist/ruff.toml`` next to the produced
    ``dist/neopool/`` subtree — discovered automatically by ruff's
    parent-directory walk. The ruff cache also lives next to the
    config (``dist/.ruff_cache``) so neither the helper file nor its
    cache pollute the core-shaped output.

    A final non-fixing ``ruff check`` is run with output visible so any
    remaining violations surface as actionable feedback rather than
    silently passing through.

    If ruff isn't installed we just skip; the dist tree is still valid
    Python, just less tidy.
    """
    if not DIST_ROOT.exists():
        return
    # Drop the snapshot config one level above the produced subtree so
    # `dist/neopool/` contains only what's meant for a core checkout.
    DIST_PARENT.mkdir(parents=True, exist_ok=True)
    dist_config = DIST_PARENT / "ruff.toml"
    shutil.copyfile(RUFF_DIST_CONFIG, dist_config)
    cache_dir = DIST_PARENT / ".ruff_cache"

    stdout = subprocess.DEVNULL if quiet else None
    stderr = subprocess.DEVNULL if quiet else None
    cache_arg = ["--cache-dir", str(cache_dir)]
    try:
        # `--fix --unsafe-fixes` lets us drop F401 unused imports too —
        # safe here because the source is fully built before formatting.
        # `--exit-zero` so a still-failing rule (e.g. genuine logic
        # error in the source) does not abort the format pass below.
        subprocess.run(
            [
                "ruff",
                "check",
                *cache_arg,
                "--fix",
                "--unsafe-fixes",
                "--exit-zero",
                str(DIST_ROOT),
            ],
            check=True,
            stdout=stdout,
            stderr=stderr,
        )
        subprocess.run(
            ["ruff", "format", *cache_arg, str(DIST_ROOT)],
            check=True,
            stdout=stdout,
            stderr=stderr,
        )
        # Final lint pass: surfaces anything --fix couldn't auto-resolve
        # so the user sees what's left to clean up. Always visible.
        result = subprocess.run(
            ["ruff", "check", *cache_arg, str(DIST_ROOT)],
            check=False,
        )
        if result.returncode == 0:
            print("  ruff check (core config):  clean")
        else:
            print(f"  ruff check (core config):  {result.returncode} issues remain")
    except FileNotFoundError:
        print("  (ruff not on PATH — skipping format pass)")
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        print(f"  (ruff exited with {exc.returncode} — see output above)")


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
    parser.add_argument(
        "--escape-translations",
        dest="escape_translations",
        action="store_true",
        default=DEFAULT_ESCAPE_TRANSLATIONS,
        help=(
            "Emit `\\uXXXX` escapes for non-ASCII characters in "
            "translations/en.json (Lokalise serialisation style). "
            "Default: off — keep raw UTF-8 for editor / grep readability."
        ),
    )
    parser.add_argument(
        "--no-escape-translations",
        dest="escape_translations",
        action="store_false",
        help="Keep raw UTF-8 in translations/en.json (default).",
    )
    parser.add_argument(
        "--format",
        dest="format_dist",
        action="store_true",
        default=True,
        help="Run `ruff format` over dist/ after sync (default: on).",
    )
    parser.add_argument(
        "--no-format",
        dest="format_dist",
        action="store_false",
        help="Skip the ruff format pass.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    print("syncing custom HACS sources to dist/ for core …")
    print(
        f"  clean={args.clean}  "
        f"strip_license={args.strip_license}  "
        f"strip_pragma={args.strip_pragma}  "
        f"escape_translations={args.escape_translations}  "
        f"format={args.format_dist}"
    )
    sync(
        clean=args.clean,
        strip_license=args.strip_license,
        strip_pragma=args.strip_pragma,
        escape_translations=args.escape_translations,
    )
    if args.format_dist:
        _run_ruff_format(quiet=True)
    print("done.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI dispatch
    sys.exit(main())
