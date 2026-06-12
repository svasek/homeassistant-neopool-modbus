"""Static configuration for the sync script.

Tweak the constants here when the layout, integration name, or strip
rules change — the rest of the script stays the same.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

DOMAIN = "neopool"

# Snapshot of the ruff config from home-assistant/core@dev/pyproject.toml
# — used to lint the generated dist/ tree exactly the way core's CI would.
# Keeps the custom repo's lighter ruff config (in the root pyproject.toml)
# untouched.
RUFF_DIST_CONFIG = Path(__file__).resolve().parent / "ruff_dist.toml"

SOURCE_INTEGRATION = REPO_ROOT / "custom_components" / DOMAIN
SOURCE_TESTS = REPO_ROOT / "tests"

# Mirrors the Home Assistant core repo layout so a `diff -r dist/neopool
# <core>/homeassistant/components/neopool` works directly.
DIST_ROOT = REPO_ROOT / "dist" / DOMAIN
DEST_INTEGRATION = DIST_ROOT / "homeassistant" / "components" / DOMAIN
DEST_TESTS = DIST_ROOT / "tests" / "components" / DOMAIN
DEST_SNAPSHOTS = DEST_TESTS / "snapshots"

# ---------------------------------------------------------------------------
# Files & directories that stay HACS-only
# ---------------------------------------------------------------------------

# Integration files NOT to copy into core.
EXCLUDE_INTEGRATION_FILES: frozenset[str] = frozenset(
    {
        "migration.py",  # cross-domain (vistapool→neopool) + v1→v4 history
    }
)

EXCLUDE_INTEGRATION_DIRS: frozenset[str] = frozenset(
    {
        "brand",  # HACS UI logos; core uses the central brands repo
        "translations",  # core regenerates from strings.json via Lokalise
        "__pycache__",
    }
)

# Test files NOT to copy into core.
EXCLUDE_TEST_FILES: frozenset[str] = frozenset(
    {
        "test_migration.py",  # custom-only; matches the stripped migration.py
        "test_init_custom.py",  # vistapool/v1/legacy migration scenarios
        "test_config_flow_custom.py",  # vistapool import + v1 duplicate abort
    }
)

EXCLUDE_TEST_DIRS: frozenset[str] = frozenset({"__pycache__"})

# ---------------------------------------------------------------------------
# Path & import rewrites
# ---------------------------------------------------------------------------

# Plain string replacements applied to every Python file copied to dist.
# Order matters — longer matches first, so the more specific replacement
# does not get partially eaten by a later one.
PYTHON_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    # patch("custom_components.neopool…")  →  patch("homeassistant.components.neopool…")
    ('"custom_components.neopool', '"homeassistant.components.neopool'),
    ("'custom_components.neopool", "'homeassistant.components.neopool"),
    # `from custom_components.neopool…`  /  `import custom_components.neopool…`
    ("from custom_components.neopool", "from homeassistant.components.neopool"),
    ("import custom_components.neopool", "import homeassistant.components.neopool"),
    # phacc → core test helpers. The order matters: the explicit `.common`
    # alias would match the generic rule too, but listing it first is just
    # belt-and-braces — both forms produce the same final string.
    #
    #   phacc.common      → tests.common
    #   phacc.components  → tests.components
    #   phacc.typing      → tests.typing
    #   phacc.syrupy      → tests.syrupy
    ("pytest_homeassistant_custom_component", "tests"),
)

# ---------------------------------------------------------------------------
# Manifest transform
# ---------------------------------------------------------------------------

# HACS-only top-level keys to drop from manifest.json.
MANIFEST_DROP_KEYS: frozenset[str] = frozenset({"version", "issue_tracker"})

# ---------------------------------------------------------------------------
# Optional strippers (toggled via CLI flags)
# ---------------------------------------------------------------------------

# Default behaviour: strip license headers (core does not use them) and
# keep `# pragma: no cover` markers (some core integrations do use them).
DEFAULT_STRIP_LICENSE = True
DEFAULT_STRIP_PRAGMA = False

# License header detection: the first non-empty line starts with this
# prefix, and the contiguous comment block that follows is the header.
LICENSE_HEADER_PREFIX = "# Copyright"
