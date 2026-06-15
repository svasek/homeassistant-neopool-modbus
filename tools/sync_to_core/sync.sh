#!/usr/bin/env bash
# End-to-end sync wrapper: from custom HACS sources to a core fork.
#
# Runs the 6-step recipe documented in tools/README.md:
#   1. python -m tools.sync_to_core              (regenerate dist/)
#   2. rsync dist/ → <core>/homeassistant/components/neopool/
#                  → <core>/tests/components/neopool/
#   3. npx prettier --write on the three integration JSONs
#   4. update requirements_all.txt in-place if the manifest's
#      `requirements` list changed (auto-detected, no flag needed)
#   5. python -m script.hassfest --action=generate
#   6. print "now: review, amend, force-push" reminder
#
# The Python-side `python -m tools.sync_to_core` only knows about the
# custom repo and dist/. Steps 2-5 happen inside the core fork, which
# this script must locate via --core-repo, the HA_CORE_REPO env var, or
# the default fallback below.
#
# Usage:
#   tools/sync_to_core/sync.sh [--core-repo PATH]
#                              [--dry-run]
#                              [-h|--help]

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults & argument parsing
# ---------------------------------------------------------------------------

# Resolve the custom repo root from this script's location: the file
# lives at <repo>/tools/sync_to_core/sync.sh, so two `..` jumps land at
# the repo root regardless of where the caller invoked it from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CUSTOM_REPO="$(cd "${SCRIPT_DIR}/../.." && pwd)"

CORE_REPO="${HA_CORE_REPO:-${HOME}/work/_git_repos_/home-assistant--core}"
DRY_RUN=0

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

End-to-end sync from custom HACS sources to a HA core fork.

Options:
  --core-repo PATH       Path to the HA core fork checkout (default:
                         \$HA_CORE_REPO env var, then
                         ~/work/_git_repos_/home-assistant--core).
  --dry-run              Print every command that would run without
                         executing anything.
  -h, --help             Show this help and exit.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --core-repo)
            CORE_REPO="$2"
            shift 2
            ;;
        --core-repo=*)
            CORE_REPO="${1#--core-repo=}"
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "[sync_to_core] error: unknown argument '$1'" >&2
            usage >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if [[ ! -d "${CORE_REPO}" ]]; then
    echo "[sync_to_core] error: core repo not found at '${CORE_REPO}'" >&2
    echo "[sync_to_core] pass --core-repo PATH or set HA_CORE_REPO" >&2
    exit 1
fi
if [[ ! -f "${CORE_REPO}/.prettierrc.js" ]]; then
    echo "[sync_to_core] error: '${CORE_REPO}' does not look like a HA core checkout (no .prettierrc.js)" >&2
    exit 1
fi

# Resolve the Python interpreter to use *inside* the core fork. Hassfest
# imports `homeassistant.*` and other dev deps that only exist in the
# core fork's virtualenv, so a system `python3` is not enough. Try
# `<core>/.venv/bin/python` first; fall back to `python3` and hope the
# user has activated the venv themselves.
if [[ -x "${CORE_REPO}/.venv/bin/python" ]]; then
    CORE_PYTHON="${CORE_REPO}/.venv/bin/python"
else
    CORE_PYTHON="python3"
fi

# Same logic for the custom side: step 1 imports `tools.sync_to_core`,
# which needs the custom repo's dev deps (pymodbus etc.) that live in
# its own .venv.
if [[ -x "${CUSTOM_REPO}/.venv/bin/python" ]]; then
    CUSTOM_PYTHON="${CUSTOM_REPO}/.venv/bin/python"
else
    CUSTOM_PYTHON="python3"
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Print a command before running it (or instead of it, in --dry-run).
# Quoting via printf '%q' makes the printout copy-pasteable.
run() {
    local quoted=()
    for arg in "$@"; do
        quoted+=("$(printf '%q' "${arg}")")
    done
    echo "[sync_to_core] $ ${quoted[*]}"
    if [[ ${DRY_RUN} -eq 0 ]]; then
        "$@"
    fi
}

log() {
    echo "[sync_to_core] $*"
}

# Read a manifest's `requirements` array as a newline-separated list.
# Empty / missing manifest yields nothing. Used to detect a lib pin
# change between pre-rsync and post-rsync state of the core manifest.
read_requirements() {
    local manifest="$1"
    if [[ ! -f "${manifest}" ]]; then
        return 0
    fi
    python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))
for r in m.get('requirements', []):
    print(r)
" "${manifest}"
}

# Replace the pinned version of a single `name==version` requirement
# in-place inside the given file. Matches both bare `name==X` and
# `name[extras]==X` forms; updates only the version after the LAST `==`
# on the line (so `name==X==Y` weirdness, which we don't expect, would
# be left alone). Echoes 1 if the file was modified, 0 if no match was
# found (caller decides whether that's an error).
replace_pin_in_file() {
    local file="$1"
    local new_req="$2"  # e.g. "neopool-modbus==2.1.1"
    local pkg="${new_req%%==*}"

    if ! grep -qE "^${pkg}(\[[^]]+\])?==" "${file}"; then
        return 1
    fi
    if [[ ${DRY_RUN} -eq 1 ]]; then
        log "would update ${pkg} pin in $(basename "${file}") to ${new_req}"
        return 0
    fi
    # macOS sed needs `-i ''` for in-place; -E enables extended regex.
    sed -i.bak -E "s|^${pkg}(\[[^]]+\])?==.*$|${new_req}|" "${file}"
    rm -f "${file}.bak"
    return 0
}

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

log "custom repo: ${CUSTOM_REPO}"
log "core repo:   ${CORE_REPO}"
log "core python: ${CORE_PYTHON}"
if [[ ${DRY_RUN} -eq 1 ]]; then
    log "DRY RUN — commands will be printed, not executed"
fi
echo

# Step 1: Generate dist/ from custom sources.
log "step 1/6: regenerate dist/ from custom sources"
run env -C "${CUSTOM_REPO}" "${CUSTOM_PYTHON}" -m tools.sync_to_core

# Capture the requirements pin from before rsync (the current state of
# core's manifest) and the new state (the freshly-generated dist
# manifest). This works in --dry-run too: rsync wouldn't have updated
# the core manifest, but step 1 always regenerates dist/, so AFTER is
# accurate regardless.
CORE_MANIFEST="${CORE_REPO}/homeassistant/components/neopool/manifest.json"
DIST_MANIFEST="${CUSTOM_REPO}/dist/neopool/homeassistant/components/neopool/manifest.json"
BEFORE_REQS="$(read_requirements "${CORE_MANIFEST}" || true)"
AFTER_REQS="$(read_requirements "${DIST_MANIFEST}" || true)"

# Step 2: rsync the dist subtrees into the core fork. The custom HACS
# tree intentionally lacks `quality_scale.yaml` (HACS doesn't read it),
# but core needs it — the file was authored once in the core fork and
# must survive every sync. We therefore exclude it from rsync's
# `--delete` pass via `--exclude`. Same logic for any future
# core-only siblings: add them to the exclude list.
#
# `--checksum` (-c) makes rsync compare file content rather than
# size+mtime. Slower but accurate when the dist regeneration produces
# byte-different output that happens to share the previous file's size
# (e.g. a same-length version bump from `1.0.0` to `1.0.1`).
log "step 2/6: rsync dist subtrees into core fork"
run rsync -avc --delete \
    --exclude=quality_scale.yaml \
    "${CUSTOM_REPO}/dist/neopool/homeassistant/components/neopool/" \
    "${CORE_REPO}/homeassistant/components/neopool/"
run rsync -avc --delete \
    "${CUSTOM_REPO}/dist/neopool/tests/components/neopool/" \
    "${CORE_REPO}/tests/components/neopool/"

# Step 3: prettier --write on the three integration JSONs. Run from
# inside the core fork so the plugin in <core>/node_modules is found.
log "step 3/6: prettier --write on the integration JSONs"
run env -C "${CORE_REPO}" npx --no-install prettier --write \
    homeassistant/components/neopool/manifest.json \
    homeassistant/components/neopool/strings.json \
    homeassistant/components/neopool/icons.json

# Step 4: in-place update requirements_all.txt when the manifest's
# `requirements` array changed. We do not regenerate the whole file
# (slow + needs core's full venv); we just rewrite the matching pin
# lines so they match `gen_requirements_all`'s output verbatim.
#
# An added requirement (a brand-new package not yet in
# requirements_all.txt) cannot be patched in-place: we'd also need to
# emit the `# homeassistant.components.X` comment header in the right
# alphabetical slot, which is exactly what `gen_requirements_all`
# does. Fail loudly with instructions in that case.
REQ_ALL_FILE="${CORE_REPO}/requirements_all.txt"
if [[ "${BEFORE_REQS}" == "${AFTER_REQS}" ]]; then
    log "step 4/6: requirements unchanged, skipping requirements_all.txt"
else
    log "step 4/6: requirements changed, patching requirements_all.txt"
    log "  before: $(echo "${BEFORE_REQS}" | tr '\n' ' ' | sed 's/ $//')"
    log "  after:  $(echo "${AFTER_REQS}" | tr '\n' ' ' | sed 's/ $//')"
    while IFS= read -r req; do
        [[ -z "${req}" ]] && continue
        # Only rewrite if the line for the package already exists.
        # Adding a new package needs gen_requirements_all (alphabetic
        # placement + comment header).
        if ! replace_pin_in_file "${REQ_ALL_FILE}" "${req}"; then
            log "ERROR: '${req%%==*}' not found in requirements_all.txt"
            log "  this is likely a brand-new dependency — run manually:"
            log "    cd ${CORE_REPO} && python -m script.gen_requirements_all"
            exit 1
        fi
    done <<< "${AFTER_REQS}"
fi

# Step 5: regenerate CODEOWNERS + mypy.ini. hassfest's --action=generate
# pass detects integration-level changes and rewrites the matching
# entries in those two files; without it, core CI's hassfest job will
# fail with "General errors: ... not up to date".
log "step 5/6: hassfest --action=generate (CODEOWNERS, mypy.ini)"
run env -C "${CORE_REPO}" "${CORE_PYTHON}" -m script.hassfest --action=generate

# Step 6: human-side reminder of what's left to do.
echo
log "step 6/6: done — next, in ${CORE_REPO}:"
log "  • git status            (review what changed)"
log "  • git add -A && git commit --amend --no-edit"
log "  • git push --force-with-lease"
