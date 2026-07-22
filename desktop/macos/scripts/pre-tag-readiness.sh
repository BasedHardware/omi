#!/usr/bin/env bash
# Fail-closed trusted-M1 pre-tag readiness gate.
#
# Validates the EXACT planned desktop release source on the trusted self-hosted
# M1 BEFORE an immutable version tag is created. This is readiness, not
# qualification: it checks the source + bounded OFFLINE backend stack only — no
# app launch, no E2E flows, no signed artifacts, no Beta/Stable pointer
# authority, no production interaction, no new secrets/environments/IAM.
#
# It never trusts caller claims about the source:
#   - the requested SHA is independently resolved and reachability-checked
#     against origin/main;
#   - the exact-SHA persistent checkout (from qualification-swift-cache) is
#     re-verified to HEAD == requested SHA;
#   - the harness readiness manifest is re-checked for passed + provider_mode
#     offline + git_sha == requested SHA;
#   - passed evidence is emitted only after every bounded check succeeds.
#
# The tag-creation job consumes the emitted evidence and re-verifies it against
# the SHA it is about to tag (verify-pre-tag-readiness.py), so a tag is never
# created on caller-asserted success.
#
# Usage:
#   pre-tag-readiness.sh [--keep-stack] [--evidence PATH] [--source-repository PATH] <source-sha>
#
# OMI_READINESS_LANE selects the manifest lane recorded in evidence (default:
# local; the CI workflow sets ci).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"

KEEP_STACK=0
EVIDENCE=""
SOURCE_REPOSITORY="$REPO_ROOT"
SOURCE_SHA=""
LANE="${OMI_READINESS_LANE:-local}"
SHA_RE='^[0-9a-f]{40}$'

usage() {
  cat <<'USAGE'
Fail-closed trusted-M1 pre-tag readiness gate.

Usage:
  pre-tag-readiness.sh [--keep-stack] [--evidence PATH] \
    [--source-repository PATH] <source-sha>

Options:
  --keep-stack               Leave the offline dev-harness stack running on exit
  --evidence PATH            Write readiness evidence JSON to PATH (default stdout)
  --source-repository PATH   Git repo to resolve/clone the exact source from
                             (default: this checkout)
  <source-sha>               40-hex source commit to validate (must be on origin/main)

Environment:
  OMI_READINESS_LANE         Manifest lane recorded in evidence (local|ci)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-stack)
      KEEP_STACK=1
      shift
      ;;
    --evidence)
      [[ $# -ge 2 && -n "${2:-}" && "${2:-}" != -* ]] || { echo "--evidence requires a path" >&2; exit 2; }
      EVIDENCE="$2"
      shift 2
      ;;
    --source-repository)
      [[ $# -ge 2 && -n "${2:-}" && "${2:-}" != -* ]] || { echo "--source-repository requires a path" >&2; exit 2; }
      SOURCE_REPOSITORY="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$SOURCE_SHA" ]]; then
        echo "unexpected extra argument: $1" >&2
        usage >&2
        exit 2
      fi
      SOURCE_SHA="$1"
      shift
      ;;
  esac
done

if [[ -z "$SOURCE_SHA" ]]; then
  echo "pre-tag-readiness: <source-sha> is required" >&2
  usage >&2
  exit 2
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "pre-tag-readiness: requires macOS (trusted self-hosted M1)" >&2
  exit 1
fi

if ! [[ "$SOURCE_SHA" =~ $SHA_RE ]]; then
  echo "pre-tag-readiness: source-sha must be 40 lowercase hex: $SOURCE_SHA" >&2
  exit 1
fi

git -C "$SOURCE_REPOSITORY" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "pre-tag-readiness: --source-repository is not a git repo: $SOURCE_REPOSITORY" >&2
  exit 1
}

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_SEC=$(date +%s)
GATE_OK=0
HARNESS_EVIDENCE=""

# Deterministic fail-closed evidence. On any abort (set -e) the EXIT trap still
# emits passed=false evidence so the tag job and operators get structured
# diagnostics instead of a bare exit code.
emit_evidence() {
  local passed="$1"
  local duration_s="$2"
  local err="${3:-}"
  python3 - "$EVIDENCE" "$passed" "$SOURCE_SHA" "$LANE" "$duration_s" "$STARTED_AT" "$HARNESS_EVIDENCE" "$err" <<'PY'
import json
import os
import sys
from pathlib import Path

out_path, passed, source_sha, lane, duration_s, started_at, harness_ev, err = sys.argv[1:9]
evidence = {
    "kind": "omi-desktop-pre-tag-readiness-v1",
    "passed": passed == "true",
    "source_sha": source_sha,
    "lane": lane,
    "provider_mode": "offline" if passed == "true" else None,
    "started_at": started_at,
    "duration_s": float(duration_s) if duration_s.isdigit() else 0.0,
    "checks": {
        "source_resolved_from_origin": passed == "true",
        "exact_sha_checkout_verified": passed == "true",
        "swift_cache_prepared": passed == "true",
        "self_check": passed == "true",
        "offline_stack_ready": passed == "true",
    },
    "harness_evidence": harness_ev or None,
}
if err:
    evidence["error"] = err
if out_path:
    Path(out_path).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
else:
    print(json.dumps(evidence, indent=2, sort_keys=True))
PY
}

on_abort() {
  local rc=$?
  if [[ "$GATE_OK" -eq 0 ]]; then
    local duration_s=$(( $(date +%s) - START_SEC ))
    emit_evidence false "$duration_s" "pre-tag-readiness aborted before completing all checks (rc=$rc)"
  fi
}
trap on_abort EXIT

# 1. Independently resolve the requested SHA from origin and confirm it is on
#    main. Never trust the caller's claim that this is the planned source.
git -C "$SOURCE_REPOSITORY" fetch --quiet --force origin main
git -C "$SOURCE_REPOSITORY" rev-parse --verify --quiet "${SOURCE_SHA}^{commit}" >/dev/null || {
  echo "pre-tag-readiness: source SHA $SOURCE_SHA does not resolve to a commit in $SOURCE_REPOSITORY" >&2
  exit 1
}
git -C "$SOURCE_REPOSITORY" merge-base --is-ancestor "$SOURCE_SHA" origin/main || {
  echo "pre-tag-readiness: source SHA $SOURCE_SHA is not reachable from origin/main" >&2
  exit 1
}

# 2. Prepare the exact-SHA Swift cache + persistent exact-source checkout. This
#    exercises the persisted checkout lifecycle (clean clone + detach + clean)
#    outside the Actions checkout and validates Package.swift/Package.resolved.
WORKTREE="$(bash "$SCRIPT_DIR/qualification-swift-cache.sh" prepare "$SOURCE_SHA" "$SOURCE_REPOSITORY")"

# 3. Re-verify the persistent checkout HEAD matches the requested SHA exactly.
CHECKOUT_SHA="$(git -C "$WORKTREE" rev-parse HEAD)"
if [[ "$CHECKOUT_SHA" != "$SOURCE_SHA" ]]; then
  echo "pre-tag-readiness: persistent checkout HEAD $CHECKOUT_SHA != requested $SOURCE_SHA" >&2
  exit 1
fi

# 4. Run source + offline-stack readiness in the exact-source checkout. The
#    harness enforces provider_mode=offline (no production interaction) and
#    probes Firebase Auth/Firestore, Redis, Typesense, backend and Rust desktop
#    backend. Fails closed on any check.
KEEP_FLAG=()
[[ "$KEEP_STACK" -eq 1 ]] && KEEP_FLAG=(--keep-stack)
(
  cd "$WORKTREE/desktop/macos"
  OMI_READINESS_LANE="$LANE" ./scripts/desktop-core-harness.sh --readiness "${KEEP_FLAG[@]}"
)

# 5. Locate and validate the harness readiness manifest. Re-check passed,
#    provider_mode and git_sha against the requested source — the tag job will
#    do this again, but the gate never emits success it did not observe.
HARNESS_ROOT="$WORKTREE/desktop/macos/.harness/desktop-core"
HARNESS_DIR="$(ls -td "$HARNESS_ROOT"/*-readiness 2>/dev/null | head -1)"
if [[ -z "$HARNESS_DIR" || ! -f "$HARNESS_DIR/manifest.json" ]]; then
  echo "pre-tag-readiness: no readiness manifest produced under $HARNESS_ROOT" >&2
  exit 1
fi
HARNESS_EVIDENCE="$HARNESS_DIR/manifest.json"

python3 - "$HARNESS_EVIDENCE" "$SOURCE_SHA" <<'PY'
import json
import sys
from pathlib import Path

manifest_path, requested_sha = sys.argv[1], sys.argv[2]
m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
if m.get("tier") != "readiness":
    raise SystemExit(f"readiness manifest tier must be 'readiness', got {m.get('tier')!r}")
if m.get("passed") is not True:
    raise SystemExit(f"readiness manifest did not pass: {m.get('passed')!r}")
if m.get("provider_mode") != "offline":
    raise SystemExit(f"readiness manifest provider_mode must be 'offline', got {m.get('provider_mode')!r}")
if m.get("git_sha") != requested_sha:
    raise SystemExit(f"readiness manifest git_sha {m.get('git_sha')!r} != requested {requested_sha!r}")
PY

DURATION=$(( $(date +%s) - START_SEC ))
GATE_OK=1
trap - EXIT
emit_evidence true "$DURATION"
echo "pre-tag-readiness: passed for $SOURCE_SHA (lane=$LANE, evidence: ${EVIDENCE:-stdout})" >&2
