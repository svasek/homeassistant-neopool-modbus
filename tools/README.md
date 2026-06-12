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
dist/neopool/
├── homeassistant/components/neopool/   # production code
└── tests/components/neopool/           # tests + snapshots
```

### Options

| flag                  | default | effect                                                              |
| --------------------- | ------- | ------------------------------------------------------------------- |
| `--clean`             | on      | wipe `dist/` before writing                                         |
| `--no-clean`          | —       | overwrite existing files in place                                   |
| `--strip-license`     | on      | drop the per-file `# Copyright … Apache 2.0` header (core convention) |
| `--keep-license`      | —       | preserve the license header                                         |
| `--strip-pragma`      | off     | drop `# pragma: no cover` trailing comments                         |
| `--keep-pragma`       | —       | preserve `# pragma: no cover` markers                               |

### What gets transformed

- **Imports & `patch()` strings:** `custom_components.neopool` →
  `homeassistant.components.neopool` everywhere.
- **Test imports:** `from pytest_homeassistant_custom_component.common`
  → `from tests.common`.
- **`manifest.json`:** drops `version` and `issue_tracker` (HACS-only),
  re-emits keys alphabetically (matches `hassfest`).
- **`# CUSTOM-ONLY START` … `# CUSTOM-ONLY END` blocks:** removed
  wholesale — used in custom sources to fence sections that don't apply
  to core (vistapool import flow, v1 migration scenarios, legacy
  data→options migration).
- **License header (optional, on by default):** the leading
  `# Copyright …` comment block plus its trailing blank line is removed.
- **`# pragma: no cover` (optional, off by default):** the trailing
  comment is stripped while the code on that line is preserved.

### What stays HACS-only

- `custom_components/neopool/migration.py` — cross-domain
  (vistapool→neopool) and v1→v4 history; not relevant to a fresh
  core integration.
- `custom_components/neopool/brand/` — HACS UI logos; core uses the
  central brands repository.
- `custom_components/neopool/translations/` — core regenerates these
  from `strings.json` via Lokalise.
- `tests/test_migration.py` — paired with `migration.py`.

These paths are excluded by `tools/sync_to_core/config.py`.
