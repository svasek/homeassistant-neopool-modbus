# Agent Instructions

## General

- **Unrelated changes:** Do not modify files unrelated to the current task without asking first.
- **Destructive actions:** Always ask for approval before performing destructive or hard-to-reverse actions (e.g. `git push --force`, `git reset --hard`, deleting branches/files, dropping tables).

## Project Overview

This is a Home Assistant custom integration for NeoPool/VistaPool pool controllers connected via Modbus TCP. It lives under `custom_components/neopool/` and follows the standard HA integration pattern.

## Development Commands

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run a single test file
pytest tests/test_sensor.py

# Run tests with coverage
pytest --cov=custom_components/vistapool --cov-report=term-missing tests/

# Type checking (must be 0 errors)
basedpyright

# Linting
ruff check

# Formatting check
ruff format --check

# Auto-fix formatting
ruff format
```

## Architecture

### Data Flow

```
Config Flow → ConfigEntry → NeoPoolCoordinator → NeoPoolModbusClient
                                    ↓
                         Platform entities subscribe
                         (sensor, switch, number, select, button, light, binary_sensor)
```

- **`modbus.py`** (`NeoPoolModbusClient`): Low-level Modbus TCP communication via `pymodbus`. Reads/writes registers, decodes raw register values into structured dicts.
- **`coordinator.py`** (`NeoPoolCoordinator`): `DataUpdateCoordinator` subclass. Polls `NeoPoolModbusClient` on `scan_interval`, distributes data to all platform entities. Also handles winter mode (suspends polling) and follow-up refresh after writes.
- **`const.py`**: Central definition file (~1200 lines). All entity definitions (keys, register addresses, device classes, units, options) live here as data structures. Adding a new entity usually means only editing `const.py`.
- **`entity.py`**: Base `NeoPoolEntity` — shared `unique_id`, `device_info`, `available` logic.
- **Platform files** (`sensor.py`, `switch.py`, etc.): Thin wrappers that read from `coordinator.data` using keys defined in `const.py`.

### Key Patterns

- Entity definitions in `const.py` are data-driven; platform files iterate over them to create entities. New entities rarely require changes outside `const.py`.
- `coordinator.data` is a flat `dict[str, Any]` keyed by the entity keys defined in `const.py`.
- Capability detection (hydrolysis, pH, Redox, chlorine, etc.) sets `CAPABILITY_KEYS` in coordinator data; entities check these to decide whether to register/show.
- `modbus_compat.py` abstracts pymodbus API differences between versions.
- `migration.py` handles config entry version upgrades (imported and re-exported from `__init__.py` for HA to discover).

## Branch Naming

Follow [Conventional Branch](https://conventional-branch.github.io/) format: `<type>/<description>`

- Lowercase alphanumerics and hyphens only (dots allowed in release versions)
- No consecutive, leading, or trailing hyphens or dots
- Include ticket/issue number when applicable

| prefix     | when to use                                 |
| ---------- | ------------------------------------------- |
| `feature/` | new feature (alias: `feat/`)                |
| `bugfix/`  | bug fix (alias: `fix/`)                     |
| `hotfix/`  | urgent fix                                  |
| `release/` | release preparation (e.g. `release/v1.2.0`) |
| `chore/`   | non-code tasks (deps, docs, config)         |

Examples: `feat/add-login-page`, `fix/header-bug`, `feature/issue-123-new-login`

## Git Commits

### Approval

- **Never commit automatically.** Always wait for my explicit approval before running `git commit`.
- **Tests:** If the project has tests, run them before proposing a commit. Verify that all tests pass and that code coverage has not decreased.

### Commit Message Format

Always use the format: `<type>(<scope>): <gitmoji> <description>`

**Rules:**

- `scope` is optional but use it when the change is clearly scoped to a module
  (e.g. `sensor`, `binary_sensor`, `button`, `light`, `number`, `select`, `switch`, `modbus`, `config`, `coordinator`, `entity`, `diagnostics`, `helpers`)
- `description`: lowercase, imperative mood ("add", not "added"), no period at end

**Pick the type and gitmoji that best reflect the nature of the change:**

| type       | gitmoji | when to use                                        |
| ---------- | ------- | -------------------------------------------------- |
| `feat`     | ✨      | new user-facing feature                            |
| `feat!`    | 💥      | breaking change                                    |
| `fix`      | 🐛      | bug fix                                            |
| `fix`      | 🩹      | minor / non-critical fix (style, typo, off-by-one) |
| `fix`      | 🚑️      | critical hotfix                                    |
| `fix`      | 🔒️      | security / privacy fix                             |
| `docs`     | 📝      | add or update documentation or comments            |
| `style`    | 🎨      | code structure / formatting (no logic change)      |
| `style`    | 💄      | UI or style files                                  |
| `refactor` | ♻️      | refactor without behaviour change                  |
| `test`     | ✅      | add, update, or fix tests                          |
| `test`     | 🧪      | add a failing test                                 |
| `perf`     | ⚡️      | performance improvement                            |
| `chore`    | 🔧      | config or tooling update                           |
| `chore`    | 🏷️      | add or update types / labels                       |
| `chore`    | 🔖      | release or version tag                             |
| `chore`    | ⬆️      | upgrade dependency                                 |
| `chore`    | ⬇️      | downgrade dependency                               |
| `chore`    | 🌱      | add or update seed / fixture files                 |
| `ci`       | 👷      | add or update CI build system                      |
| `ci`       | 💚      | fix CI build                                       |
| `revert`   | ⏪️      | revert a previous commit                           |

**Commit message body:**

Add a blank line after the subject line, then a bullet list covering:

- what changed (one bullet per logical change, imperative style)
- why it was changed (motivation, context)
- relevant technical detail if non-obvious

Keep bullets concise (one line each). If the commit resolves a GitHub issue, end the body with `Resolves #<issue-number>`.

```
feat(modbus): ✨ add notification-based polling optimisation

- replace interval polling with Modbus event notifications
- reduce unnecessary register reads when no state change occurred
- add configurable debounce threshold for notification batching
- improves responsiveness and reduces Modbus bus load

Resolves #97
```

**Examples from this project:**

```
feat(button): ✨ add backwash button and logic for automatic filtration valve
fix(coordinator): 🐛 mark entities unavailable on Modbus communication error
fix: 🩹 update step value for redox setpoint
refactor: ♻️ use data-driven option gating for cover sensor entities
chore: 🏷️ update model and manufacturer details for VistaPool
chore(deps): ⬆️ bump codecov/codecov-action from 5 to 6
```

### Shell Execution

Multi-line commit messages in bash/zsh: use multiple `-m` flags (one per paragraph) or heredoc (`git commit -F - <<'EOF' ... EOF`). A single `-m` with newlines inside quotes does NOT work reliably.

## Pull Requests

- PR description must be in **English** and **Markdown** format (ready for copy & paste into GitHub).
- **PR title** must follow the same commit message format: `<type>(<scope>): <gitmoji> <description>`.
- **PR body** should use emoji to visually categorize sections and bullet points.

## Code Quality

### Type Checking

- This project uses **basedpyright** with `typeCheckingMode: basic` (see `pyrightconfig.json`).
- Run `basedpyright` before committing and ensure **0 errors**.
- CI enforces type checking via `.github/workflows/typecheck.yml`.

### Linting & Formatting

- Use **ruff** for both linting and formatting.
- Run `ruff check` and `ruff format --check` before committing.
- CI enforces ruff checks on every PR.

### Pre-commit Checklist

Before proposing a commit, verify:

1. `basedpyright` - 0 errors
2. `ruff check` - all checks passed
3. `ruff format --check` - all files formatted
4. `pytest` - all tests pass, coverage not decreased (100% coverage if applicable)
