# Tools

Helper scripts for repository maintenance.

## `sync_to_core`

Generates a core-publishable mirror of the custom HACS integration under
`dist/neopool/`, transforming imports and stripping HACS-specific files
so the result can be diffed against the Home Assistant core repo.

`dist/` is gitignored — the script never touches the real core checkout.
After it runs you can copy `dist/neopool/homeassistant/components/neopool/`
and `dist/neopool/tests/components/neopool/` into your core fork manually
and inspect the diff in git.

### Usage

```bash
python -m tools.sync_to_core
```

Output layout:

```
dist/
├── neopool/                            # ← copy this into a core checkout
│   ├── homeassistant/components/neopool/   # production code
│   └── tests/components/neopool/           # tests + snapshots
├── ruff.toml                           # core ruff config snapshot (helper)
└── .ruff_cache/                        # ruff cache (helper)
```

`dist/neopool/` contains exactly what's meant to land in a core
checkout — the lint helpers (`ruff.toml`, `.ruff_cache`) sit one level
above so they don't pollute the produced subtree.

### Options

| flag                       | default | effect                                                                |
| -------------------------- | ------- | --------------------------------------------------------------------- |
| `--clean`                  | on      | wipe `dist/` before writing                                           |
| `--no-clean`               | —       | overwrite existing files in place                                     |
| `--strip-license`          | on      | drop the per-file `# Copyright … Apache 2.0` header (core convention) |
| `--keep-license`           | —       | preserve the license header                                           |
| `--strip-pragma`           | off     | drop `# pragma: no cover` trailing comments                           |
| `--keep-pragma`            | —       | preserve `# pragma: no cover` markers                                 |
| `--escape-translations`    | off     | emit `\uXXXX` escapes in `translations/en.json` (Lokalise style)      |
| `--no-escape-translations` | —       | keep raw UTF-8 in `translations/en.json` (default)                    |
| `--format`                 | on      | run `ruff check --fix` + `ruff format` over `dist/` after sync        |
| `--no-format`              | —       | skip the ruff pass                                                    |

### What gets transformed

- **Imports & `patch()` strings:** `custom_components.neopool` →
  `homeassistant.components.neopool` everywhere.
- **Test imports:** `from pytest_homeassistant_custom_component`
  → `from tests` (covers `.common`, `.components.diagnostics`,
  `.typing`, `.syrupy`).
- **`manifest.json`:** drops `version` and `issue_tracker` (HACS-only),
  re-emits keys alphabetically (matches `hassfest`).
- **`strings.json` and `translations/en.json`:** strip the vistapool /
  migration UI key paths (`config.step.import_from_vistapool`,
  `config.abort.migration_complete`, etc.) so the generated tree has
  no HACS-only translations. Other locales (`cs.json`, `de.json`, …)
  are skipped via an allow-list — only `en.json` reaches dist.
- **`# CUSTOM-ONLY START` … `# CUSTOM-ONLY END` blocks:** removed
  wholesale — used in custom sources to fence sections that don't apply
  to core (legacy data→options migration, vistapool offer/abort,
  `async_step_import_from_vistapool`).
- **`from .migration import …` blocks:** stripped automatically based
  on `EXCLUDE_INTEGRATION_FILES` — adding a new HACS-only module to
  that list also makes its imports disappear.
- **License header (optional, on by default):** the leading
  `# Copyright …` comment block plus its trailing blank line is removed.
- **`# pragma: no cover` (optional, off by default):** the trailing
  comment is stripped while the code on that line is preserved.
- **Final `ruff` pass:** `ruff check --fix --unsafe-fixes` then `ruff
  format` is run over `dist/` using a snapshot of HA core's ruff config
  (`tools/sync_to_core/ruff_dist.toml`, copied into `dist/neopool/` as
  `ruff.toml`). The result lints clean under core's CI rules without
  changing the custom repo's own (lighter) ruff config.

### What stays HACS-only

- `custom_components/neopool/migration.py` — cross-domain
  (vistapool→neopool) and v1→v4 history; not relevant to a fresh
  core integration.
- `custom_components/neopool/brand/` — HACS UI logos; core uses the
  central brands repository.
- `custom_components/neopool/translations/<lang>.json` for every locale
  except `en.json` — the others come from Lokalise after merge. This is
  an allow-list, so adding a new translation file in custom doesn't
  silently leak into core.
- `tests/test_migration.py` — paired with `migration.py`.
- `tests/test_init_custom.py` — v1→v4 migration + legacy data→options
  test scenarios that have no core counterpart.
- `tests/test_config_flow_custom.py` — vistapool import flow + v1
  duplicate abort test scenarios.

These paths are excluded by `tools/sync_to_core/config.py`.

### Updating the core ruff snapshot

`tools/sync_to_core/ruff_dist.toml` is a snapshot of the
`[tool.ruff*]` sections from `home-assistant/core@dev/pyproject.toml`,
saved 2026-06-12. To refresh:

1. Diff against the live core pyproject.
2. Copy the `[tool.ruff*]` sections verbatim, dropping the `tool.`
   prefix (the file is loaded as a stand-alone `ruff.toml`).
3. Update the snapshot date in the file's header comment.
4. Re-run `python -m tools.sync_to_core` and verify `ruff check
   (core config):  clean`.
