#!/usr/bin/env bash
# Fail-closed trusted-M1 pre-tag readiness gate. It validates the exact planned
# source on the trusted runner before the existing serialized tag job can publish
# an immutable candidate. Readiness is offline-only and has no Beta/Stable or
# qualification authority.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"
CACHE_COMMAND="$SCRIPT_DIR/qualification-swift-cache.sh"
LEASE_COMMAND="$SCRIPT_DIR/qualification-lease-command.sh"

EVIDENCE=""
SOURCE_REPOSITORY="$REPO_ROOT"
SOURCE_SHA=""
LANE="${OMI_READINESS_LANE:-local}"
SHA_RE='^[0-9a-f]{40}$'
RETAINED_RUNS="${OMI_QUALIFICATION_RETAINED_RUNS:-3}"
RETENTION_AGE_SECONDS="${OMI_QUALIFICATION_RETENTION_AGE_SECONDS:-1209600}"
LEASE_ROOT="${OMI_QUALIFICATION_LEASE_ROOT:-${TMPDIR:-/tmp}/omi-desktop-qualification}"
CACHE_LEASE_ID=""
CACHE_LEASE_TOKEN=""
READINESS_LEASE_ID=""
READINESS_LEASE_TOKEN=""
WORKTREE=""
AGENT_DIR=""
HARNESS_EVIDENCE=""
READINESS_COMPLETE=0
READINESS_CLEANUP_OK=0
STARTED_AT=""
START_SEC=0

usage() {
  cat <<'USAGE'
Fail-closed trusted-M1 pre-tag readiness gate.

Usage:
  pre-tag-readiness.sh [--evidence PATH] [--source-repository PATH] <source-sha>

Options:
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
      [[ -z "$SOURCE_SHA" ]] || { echo "unexpected extra argument: $1" >&2; exit 2; }
      SOURCE_SHA="$1"
      shift
      ;;
  esac
done

[[ -n "$SOURCE_SHA" ]] || { echo "pre-tag-readiness: <source-sha> is required" >&2; usage >&2; exit 2; }
[[ "$(uname -s)" == Darwin ]] || { echo "pre-tag-readiness: requires macOS (trusted self-hosted M1)" >&2; exit 1; }
[[ "$SOURCE_SHA" =~ $SHA_RE ]] || { echo "pre-tag-readiness: source-sha must be 40 lowercase hex: $SOURCE_SHA" >&2; exit 1; }
git -C "$SOURCE_REPOSITORY" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "pre-tag-readiness: --source-repository is not a git repo: $SOURCE_REPOSITORY" >&2
  exit 1
}
[[ -x "$CACHE_COMMAND" && -x "$LEASE_COMMAND" ]] || {
  echo "pre-tag-readiness: cache or authenticated qualification lease command is unavailable" >&2
  exit 1
}

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_SEC=$(date +%s)

emit_evidence() {
  local passed="$1" duration_s="$2" err="${3:-}"
  python3 - "$EVIDENCE" "$passed" "$SOURCE_SHA" "$LANE" "$duration_s" "$STARTED_AT" "$HARNESS_EVIDENCE" "$err" <<'PY'
import json
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
    "harness_evidence": Path(harness_ev).name if harness_ev else None,
}
if err:
    evidence["error"] = err
target = Path(out_path) if out_path else None
if target:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    target.chmod(0o600)
else:
    print(json.dumps(evidence, indent=2, sort_keys=True))
PY
}

json_capability_field() {
  local field="$1" payload="$2" value
  if value="$(printf '%s' "$payload" | python3 -c '
import json
import sys
value = json.load(sys.stdin).get(sys.argv[1])
if not isinstance(value, str) or not value:
    raise SystemExit(1)
print(value)
' "$field" 2>/dev/null)"; then
    printf '%s\n' "$value"
    return 0
  fi
  echo "pre-tag-readiness: capability omitted valid $field" >&2
  return 1
}

owned_agent_directory_is_real() {
  local component candidate
  [[ -n "$WORKTREE" && -n "$AGENT_DIR" && "$AGENT_DIR" == "$WORKTREE/desktop/macos/agent" ]] || {
    echo "pre-tag-readiness: agent dependency path is outside the owned exact source" >&2
    return 1
  }
  candidate="$WORKTREE"
  [[ -d "$candidate" && ! -L "$candidate" ]] || {
    echo "pre-tag-readiness: owned exact source root is not a real directory" >&2
    return 1
  }
  for component in desktop macos agent; do
    candidate="$candidate/$component"
    [[ -d "$candidate" && ! -L "$candidate" ]] || {
      echo "pre-tag-readiness: owned agent dependency ancestor is missing or symlinked: $component" >&2
      return 1
    }
  done
}

release_owned_capabilities() {
  local failed=0
  if [[ -n "$AGENT_DIR" ]]; then
    if ! owned_agent_directory_is_real; then
      failed=1
    elif [[ -e "$AGENT_DIR/node_modules" || -L "$AGENT_DIR/node_modules" ]]; then
      # npm ci may leave a partial ignored tree when it fails. The cache lease is
      # still held here, so remove this run's exact-source residue before either
      # capability can be released. rm -r on a symlink unlinks the symlink rather
      # than following it.
      rm -rf -- "$AGENT_DIR/node_modules" || failed=1
    fi
  fi
  if [[ -n "$READINESS_LEASE_TOKEN" && -n "$WORKTREE" ]]; then
    "$LEASE_COMMAND" release \
      "$WORKTREE" "$READINESS_LEASE_ID" "$READINESS_LEASE_TOKEN" \
      "$RETAINED_RUNS" "$RETENTION_AGE_SECONDS" || failed=1
  fi
  if [[ -n "$CACHE_LEASE_TOKEN" ]]; then
    "$CACHE_COMMAND" release \
      "$SOURCE_SHA" "$CACHE_LEASE_ID" "$$" "$CACHE_LEASE_TOKEN" || failed=1
  fi
  return "$failed"
}

finalize() {
  local rc=$? duration_s
  trap - EXIT
  if ! release_owned_capabilities; then
    rc=1
  else
    READINESS_CLEANUP_OK=1
  fi
  duration_s=$(( $(date +%s) - START_SEC ))
  # Once the readiness harness completed, a refused authenticated release is a
  # distinct terminal condition. Keep the receipt non-passing and make that
  # ownership-cleanup failure explicit rather than misclassifying it as a
  # pre-readiness abort.
  if [[ "$READINESS_COMPLETE" -eq 1 && "$READINESS_CLEANUP_OK" -ne 1 ]]; then
    emit_evidence false "$duration_s" "pre-tag-readiness authenticated cleanup failed"
    exit 1
  fi
  if [[ "$rc" -eq 0 && "$READINESS_COMPLETE" -eq 1 ]]; then
    emit_evidence true "$duration_s"
    echo "pre-tag-readiness: passed for $SOURCE_SHA (lane=$LANE, evidence: ${EVIDENCE:-stdout})" >&2
    exit 0
  fi
  emit_evidence false "$duration_s" "pre-tag-readiness aborted before readiness and authenticated cleanup completed (rc=$rc)"
  exit "$rc"
}
trap finalize EXIT

# Resolve independently from origin/main; no caller-provided identity is trusted.
git -C "$SOURCE_REPOSITORY" fetch --quiet --no-tags origin +refs/heads/main:refs/remotes/origin/main
git -C "$SOURCE_REPOSITORY" rev-parse --verify --quiet "${SOURCE_SHA}^{commit}" >/dev/null
git -C "$SOURCE_REPOSITORY" merge-base --is-ancestor "$SOURCE_SHA" origin/main || {
  echo "pre-tag-readiness: source SHA $SOURCE_SHA is not reachable from origin/main" >&2
  exit 1
}

# Bound cache and runner ownership to one source/run/pid-derived capability set.
RUN_SCOPE="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-attempt}-${BASHPID:-$$}"
RUN_SCOPE="${RUN_SCOPE//[^A-Za-z0-9]/-}"
CACHE_LEASE_ID="cache-readiness-${SOURCE_SHA:0:12}-${RUN_SCOPE:0:32}"
READINESS_LEASE_ID="readiness-${SOURCE_SHA:0:12}-${RUN_SCOPE:0:32}"
PORT_OFFSET="$(python3 - "$SOURCE_SHA" "$READINESS_LEASE_ID" <<'PY'
import hashlib
import sys
print(1000 + (int(hashlib.sha256(":".join(sys.argv[1:]).encode()).hexdigest()[:8], 16) % 2000))
PY
)"

CACHE_JSON="$(
  "$CACHE_COMMAND" prepare \
    "$SOURCE_SHA" "$SOURCE_REPOSITORY" "$CACHE_LEASE_ID" "$$"
)"
WORKTREE="$(json_capability_field source "$CACHE_JSON")"
CACHE_LEASE_TOKEN="$(json_capability_field token "$CACHE_JSON")"
test "$(git -C "$WORKTREE" rev-parse HEAD)" = "$SOURCE_SHA"

LEASE_JSON="$(
  "$LEASE_COMMAND" acquire \
    "$WORKTREE" "$READINESS_LEASE_ID" "$$" "$PORT_OFFSET" "$RETAINED_RUNS"
)"
READINESS_LEASE_TOKEN="$(json_capability_field token "$LEASE_JSON")"

# The harness sees only this lease's state, instance, ports, and authenticated
# ownership token; it cannot infer authority over unrelated runner processes.
export OMI_QUALIFICATION_LEASE_ROOT="$LEASE_ROOT"
export OMI_LOCAL_STATE_ROOT="$LEASE_ROOT/state"
export OMI_LOCAL_INSTANCE="$READINESS_LEASE_ID"
export OMI_HARNESS_PORT_OFFSET="$PORT_OFFSET"
export OMI_HARNESS_OWNERSHIP_TOKEN="$READINESS_LEASE_TOKEN"

# The cached exact-source worktree deliberately excludes ignored dependency
# trees. The readiness self-check executes a focused Vitest contract, so install
# its lockfile-pinned dependencies only after both cache and host leases are
# acquired. This prevents an incidental runner checkout from deciding readiness.
AGENT_DIR="$WORKTREE/desktop/macos/agent"
owned_agent_directory_is_real || exit 1
[[ -f "$AGENT_DIR/package.json" && -f "$AGENT_DIR/package-lock.json" ]] || {
  echo "pre-tag-readiness: exact source is missing the agent npm manifests" >&2
  exit 1
}
(
  cd "$AGENT_DIR"
  env -u NODE_ENV -u NPM_CONFIG_OMIT -u npm_config_omit -u NPM_CONFIG_PRODUCTION -u npm_config_production \
    npm ci --include=dev --no-fund --no-audit
)
[[ -x "$AGENT_DIR/node_modules/.bin/vitest" ]] || {
  echo "pre-tag-readiness: lockfile-pinned agent Vitest dependency is unavailable" >&2
  exit 1
}
(
  cd "$WORKTREE/desktop/macos"
  OMI_READINESS_LANE="$LANE" ./scripts/desktop-core-harness.sh --readiness
)

HARNESS_ROOT="$WORKTREE/desktop/macos/.harness/desktop-core"
HARNESS_DIR="$(ls -td "$HARNESS_ROOT"/*-readiness 2>/dev/null | head -1)"
[[ -n "$HARNESS_DIR" && -f "$HARNESS_DIR/manifest.json" ]] || {
  echo "pre-tag-readiness: no readiness manifest produced under $HARNESS_ROOT" >&2
  exit 1
}
HARNESS_EVIDENCE="$HARNESS_DIR/manifest.json"
python3 - "$HARNESS_EVIDENCE" "$SOURCE_SHA" <<'PY'
import json
import sys
from pathlib import Path

manifest_path, requested_sha = sys.argv[1:]
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
if manifest.get("tier") != "readiness":
    raise SystemExit(f"readiness manifest tier must be 'readiness', got {manifest.get('tier')!r}")
if manifest.get("passed") is not True:
    raise SystemExit(f"readiness manifest did not pass: {manifest.get('passed')!r}")
if manifest.get("provider_mode") != "offline":
    raise SystemExit(f"readiness manifest provider_mode must be 'offline', got {manifest.get('provider_mode')!r}")
if manifest.get("git_sha") != requested_sha:
    raise SystemExit(f"readiness manifest git_sha {manifest.get('git_sha')!r} != requested {requested_sha!r}")
PY

# The EXIT trap authenticates and completes both release operations before it can
# emit a passing receipt. A refused foreign listener is retained/quarantined by
# the lease authority and necessarily produces only failed readiness evidence.
READINESS_COMPLETE=1
