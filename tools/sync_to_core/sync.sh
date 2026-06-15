#!/usr/bin/env bash
# End-to-end sync wrapper: from custom HACS sources to a core fork.
#
# Runs the 6-step recipe documented in tools/README.md:
#   1. python -m tools.sync_to_core              (regenerate dist/)
#   2. rsync dist/ → <core>/homeassistant/components/neopool/
#                  → <core>/tests/components/neopool/
#   3. npx prettier --write on the three integration JSONs
#   4. (optional) python -m script.gen_requirements_all
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
#                              [--regen-requirements]
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
REGEN_REQUIREMENTS=0
DRY_RUN=0

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

End-to-end sync from custom HACS sources to a HA core fork.

Options:
  --core-repo PATH       Path to the HA core fork checkout (default:
                         \$HA_CORE_REPO env var, then
                         ~/work/_git_repos_/home-assistant--core).
  --regen-requirements   Also run \`python -m script.gen_requirements_all\`
                         in the core fork. Slow; only needed when the
                         integration's library version pin changed.
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
        --regen-requirements)
            REGEN_REQUIREMENTS=1
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

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

log "custom repo: ${CUSTOM_REPO}"
log "core repo:   ${CORE_REPO}"
if [[ ${DRY_RUN} -eq 1 ]]; then
    log "DRY RUN — commands will be printed, not executed"
fi
echo

# Step 1: Generate dist/ from custom sources.
log "step 1/6: regenerate dist/ from custom sources"
run python -m tools.sync_to_core

# Step 2: rsync the dist subtrees into the core fork. We deliberately
# copy the integration and tests trees as two separate rsyncs so we can
# use --delete on each (catching renamed/removed files) without ever
# pointing rsync at a parent the core fork might share with other
# integrations. quality_scale.yaml lives only in the dist tree and gets
# copied as part of the integration subtree.
log "step 2/6: rsync dist subtrees into core fork"
run rsync -av --delete \
    "${CUSTOM_REPO}/dist/neopool/homeassistant/components/neopool/" \
    "${CORE_REPO}/homeassistant/components/neopool/"
run rsync -av --delete \
    "${CUSTOM_REPO}/dist/neopool/tests/components/neopool/" \
    "${CORE_REPO}/tests/components/neopool/"

# Step 3: prettier --write on the three integration JSONs. Run from
# inside the core fork so the plugin in <core>/node_modules is found.
log "step 3/6: prettier --write on the integration JSONs"
run env -C "${CORE_REPO}" npx --no-install prettier --write \
    homeassistant/components/neopool/manifest.json \
    homeassistant/components/neopool/strings.json \
    homeassistant/components/neopool/icons.json

# Step 4: optionally regenerate requirements_all.txt. Only needed when
# the library version pin changed, because the file is large and slow
# to regenerate (~30s).
if [[ ${REGEN_REQUIREMENTS} -eq 1 ]]; then
    log "step 4/6: regenerate requirements_all.txt"
    run env -C "${CORE_REPO}" python -m script.gen_requirements_all
else
    log "step 4/6: skip gen_requirements_all (use --regen-requirements to enable)"
fi

# Step 5: regenerate CODEOWNERS + mypy.ini. hassfest's --action=generate
# pass detects integration-level changes and rewrites the matching
# entries in those two files; without it, core CI's hassfest job will
# fail with "General errors: ... not up to date".
log "step 5/6: hassfest --action=generate (CODEOWNERS, mypy.ini)"
run env -C "${CORE_REPO}" python -m script.hassfest --action=generate

# Step 6: human-side reminder of what's left to do.
echo
log "step 6/6: done — next, in ${CORE_REPO}:"
log "  • git status            (review what changed)"
log "  • git add -A && git commit --amend --no-edit"
log "  • git push --force-with-lease"
echo
log "(if --regen-requirements was off but the lib pin moved, re-run with it)"
