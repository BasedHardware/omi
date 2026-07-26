#!/usr/bin/env bash
# Qualify a macOS desktop candidate by rebuilding the tag and running T2 core E2E.
#
# Usage:
#   ./scripts/qualify-desktop-beta.sh v11.0.0+11000-macos
#   ./scripts/qualify-desktop-beta.sh --keep-stack v11.0.0+11000-macos
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"
KEYVALUE_PY="$SCRIPT_DIR/release-keyvalue.py"
STAGE_HELPER="$SCRIPT_DIR/qualification-stage.sh"
LEASE_COMMAND="$SCRIPT_DIR/qualification-lease-command.sh"
# shellcheck source=qualification-stage.sh
source "$STAGE_HELPER"

KEEP_STACK=0
AUTOMATIC=0
SIGNED_SMOKE_RESULT=""
CANDIDATE_GATE_RESULT=""
GITHUB_ACTIONS_ARTIFACT=0
RELEASE_TAG=""

usage() {
  cat <<'USAGE'
Qualify a macOS desktop candidate (rebuild tag + T2 core E2E).

Usage:
  qualify-desktop-beta.sh [--keep-stack] [--automatic] [--github-actions-artifact] \
    [--signed-smoke-result PATH --candidate-gate-result PATH] <vX.Y.Z+BUILD-macos>

Options:
  --keep-stack   Leave the recorded qualification lease for safe later reclamation
  --automatic    Run richer automatic gates and require this to remain the newest candidate
  --signed-smoke-result PATH  Codemagic signed-artifact smoke evidence (required with --automatic)
  --candidate-gate-result PATH  Digest-bound candidate gate evidence (required with --automatic)
  --github-actions-artifact  Leave trusted evidence publication to the workflow artifact
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-stack)
      KEEP_STACK=1
      shift
      ;;
    --automatic)
      AUTOMATIC=1
      shift
      ;;
    --signed-smoke-result)
      [[ $# -ge 2 && -n "${2:-}" && "${2:-}" != -* ]] || { echo "--signed-smoke-result requires a path" >&2; exit 2; }
      SIGNED_SMOKE_RESULT="$2"
      shift 2
      ;;
    --candidate-gate-result)
      [[ $# -ge 2 && -n "${2:-}" && "${2:-}" != -* ]] || { echo "--candidate-gate-result requires a path" >&2; exit 2; }
      CANDIDATE_GATE_RESULT="$2"
      shift 2
      ;;
    --github-actions-artifact)
      GITHUB_ACTIONS_ARTIFACT=1
      shift
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
      if [[ -n "$RELEASE_TAG" ]]; then
        echo "unexpected extra argument: $1" >&2
        usage >&2
        exit 2
      fi
      RELEASE_TAG="$1"
      shift
      ;;
  esac
done

if [[ -z "$RELEASE_TAG" ]]; then
  usage >&2
  exit 2
fi
if [[ "$AUTOMATIC" -eq 1 ]]; then
  [[ -f "$SIGNED_SMOKE_RESULT" ]] || { echo "automatic qualification requires --signed-smoke-result" >&2; exit 2; }
  [[ -f "$CANDIDATE_GATE_RESULT" ]] || { echo "automatic qualification requires --candidate-gate-result" >&2; exit 2; }
  python3 - "$RELEASE_TAG" "$SIGNED_SMOKE_RESULT" "$CANDIDATE_GATE_RESULT" <<'PY'
import json
import sys

release_tag, smoke_path, gate_path = sys.argv[1:]
smoke = json.load(open(smoke_path, encoding="utf-8"))
gate = json.load(open(gate_path, encoding="utf-8"))
if smoke.get("ok") is not True or smoke.get("release_tag") != release_tag:
    raise SystemExit("automatic qualification requires passing signed-smoke evidence for the release tag")
if gate.get("passed") is not True or gate.get("release_tag") != release_tag:
    raise SystemExit("automatic qualification requires passing candidate-gate evidence for the release tag")
PY
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "qualify-desktop-beta.sh requires macOS" >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "qualify-desktop-beta.sh requires gh CLI" >&2
  exit 1
fi

VERSION="${RELEASE_TAG#v}"
VERSION="${VERSION%-macos}"
BUNDLE="omi-qualification-${VERSION}"
WORKTREE=""
LAUNCH_LOG=""
LAUNCH_SIGNAL_FILE=""
DESKTOP_LAUNCH_PID=""
DESKTOP_LAUNCH_TOKEN=""
DESKTOP_LAUNCH_RECORD=""
DESKTOP_LAUNCH_REQUESTED=0
QUALIFICATION_CLEANUP_DONE=0
QUALIFICATION_CLEANUP_STATUS="not-acquired"
QUALIFICATION_SUCCESS=0
QUALIFICATION_LEASE_ID=""
QUALIFICATION_LEASE_TOKEN=""
QUALIFICATION_CACHE_LEASE_ID=""
QUALIFICATION_CACHE_LEASE_TOKEN=""
QUALIFICATION_CACHE_LEASE_RELEASED=0
QUALIFICATION_LEASE_ROOT="${OMI_QUALIFICATION_LEASE_ROOT:-${TMPDIR:-/tmp}/omi-desktop-qualification}"
QUALIFICATION_RETAINED_RUNS="${OMI_QUALIFICATION_RETAINED_RUNS:-3}"
QUALIFICATION_RETENTION_AGE_SECONDS="${OMI_QUALIFICATION_RETENTION_AGE_SECONDS:-1209600}"
QUALIFICATION_CLEANUP_CONTEXT="${OMI_QUALIFICATION_CLEANUP_CONTEXT:-}"
QUALIFICATION_LOG_DIR=""
QUALIFICATION_STAGE=""
QUALIFICATION_TIMINGS_FILE="${OMI_QUALIFICATION_TIMINGS_FILE:-}"
FAULT_PREFLIGHT_REPORT="${OMI_QUALIFICATION_FAULT_PREFLIGHT_REPORT:-}"
ACTIVE_PHASE=""
ACTIVE_PHASE_CLASS=""
ACTIVE_PHASE_STARTED_NS=""
# Cold, from-scratch rebuild of the exact tag compiles ~1190 SwiftPM modules
# (FluidAudio, MarkdownUI, Firebase, ONNX, …) before the named bundle is even
# packaged/signed/launched. On a self-hosted M1 that first cold build alone runs
# ~65 min and, with packaging + install, dispatches the desktop launch at ~75 min
# — past the old 3600s budget, so every fresh tag timed out at [~1139/1190]
# compiling and left no reusable .build for the warm retry, stalling Beta
# (v0.12.99–v0.12.113 all failed, self-hosted lane, `not dispatched within 3600s`).
# 5400s (90 min) covers the observed cold path with headroom while staying within
# the self-hosted job cap; warm same-SHA retry/prewarm still completes in a
# fraction of this. Overridable per runner via OMI_QUALIFY_PREPARE_WAIT_SECS.
DESKTOP_PREPARE_WAIT_SECS="${OMI_QUALIFY_PREPARE_WAIT_SECS:-5400}"
BRIDGE_WAIT_SECS=900

QUALIFICATION_STAGE="$(qualification_stage_create)"
trap 'qualification_stage_remove "$QUALIFICATION_STAGE"' EXIT
QUALIFICATION_TIMINGS_FILE="${QUALIFICATION_TIMINGS_FILE:-$QUALIFICATION_STAGE/phase-timings.json}"
FAULT_PREFLIGHT_REPORT="${FAULT_PREFLIGHT_REPORT:-$QUALIFICATION_STAGE/fault-listener-preflight.json}"

timing_now_ns() {
  python3 -c 'import time; print(time.time_ns())'
}

initialize_phase_timings() {
  umask 077
  python3 - "$QUALIFICATION_TIMINGS_FILE" "$RELEASE_TAG" <<'PY'
import json
import sys
from pathlib import Path

path, release_tag = sys.argv[1:]
target = Path(path)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({
    "schema_version": 1,
    "target_seconds": 1200,
    "release_tag": release_tag,
    "phases": [],
}, sort_keys=True) + "\n", encoding="utf-8")
target.chmod(0o600)
PY
}

phase_begin() {
  [[ -z "$ACTIVE_PHASE" ]] || { echo "qualification timing phase already active: $ACTIVE_PHASE" >&2; return 1; }
  ACTIVE_PHASE="$1"
  ACTIVE_PHASE_CLASS="$2"
  ACTIVE_PHASE_STARTED_NS="$(timing_now_ns)"
}

phase_end() {
  local status="${1:-passed}" ended_ns duration_ms
  [[ -n "$ACTIVE_PHASE" && -n "$ACTIVE_PHASE_STARTED_NS" ]] || return 0
  ended_ns="$(timing_now_ns)"
  duration_ms=$(( (ended_ns - ACTIVE_PHASE_STARTED_NS) / 1000000 ))
  python3 - "$QUALIFICATION_TIMINGS_FILE" "$ACTIVE_PHASE" "$ACTIVE_PHASE_CLASS" "$status" "$ACTIVE_PHASE_STARTED_NS" "$ended_ns" "$duration_ms" <<'PY'
import json
import sys
from pathlib import Path

path, name, classification, status, started_ns, ended_ns, duration_ms = sys.argv[1:]
target = Path(path)
payload = json.loads(target.read_text(encoding="utf-8"))
payload["phases"].append({
    "name": name,
    "classification": classification,
    "status": status,
    "started_unix_ns": int(started_ns),
    "ended_unix_ns": int(ended_ns),
    "duration_ms": int(duration_ms),
})
payload["elapsed_ms"] = sum(int(phase["duration_ms"]) for phase in payload["phases"])
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  echo "qualification phase: $ACTIVE_PHASE classification=$ACTIVE_PHASE_CLASS status=$status duration_ms=$duration_ms"
  ACTIVE_PHASE=""
  ACTIVE_PHASE_CLASS=""
  ACTIVE_PHASE_STARTED_NS=""
}

initialize_phase_timings
phase_begin "candidate-and-lease-preflight" "immutable-artifact-security"
RELEASE_FILE="$QUALIFICATION_STAGE/release.json"
gh release view "$RELEASE_TAG" --repo BasedHardware/omi --json tagName,isDraft,isPrerelease,publishedAt,assets,body \
  > "$RELEASE_FILE"

python3 "$KEYVALUE_PY" preflight-release "$RELEASE_FILE" "$RELEASE_TAG"

SHA=$(git -C "$REPO_ROOT" rev-list -n1 "$RELEASE_TAG")
RUN_SCOPE="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-attempt}-${BASHPID:-$$}"
RUN_SCOPE="${RUN_SCOPE//[^A-Za-z0-9]/-}"
QUALIFICATION_LEASE_ID="qualification-${SHA:0:12}-${RUN_SCOPE:0:32}"
QUALIFICATION_CACHE_LEASE_ID="cache-${SHA:0:12}-${RUN_SCOPE:0:32}"

qualification_cache_field() {
  local field="$1" cache_json="$2" value
  if value="$(printf '%s' "$cache_json" | python3 -c '
import json
import sys

field = sys.argv[1]
value = json.loads(sys.stdin.read()).get(field)
if not isinstance(value, str) or not value:
    raise SystemExit(1)
print(value)
' "$field" 2>/dev/null)"; then
    printf '%s\n' "$value"
    return 0
  fi
  echo "qualification failed: Swift cache lease returned no valid ${field}" >&2
  return 1
}

CACHE_JSON="$(
  "$SCRIPT_DIR/qualification-swift-cache.sh" prepare \
    "$SHA" "$REPO_ROOT" "$QUALIFICATION_CACHE_LEASE_ID" "$$"
)"
WORKTREE="$(qualification_cache_field source "$CACHE_JSON")"
QUALIFICATION_CACHE_LEASE_TOKEN="$(qualification_cache_field token "$CACHE_JSON")"

early_cleanup() {
  local exit_code=$?
  trap - EXIT
  if [[ "$KEEP_STACK" -eq 0 && -n "$QUALIFICATION_LEASE_TOKEN" && -d "$WORKTREE" ]]; then
    "$LEASE_COMMAND" release \
      "$WORKTREE" "$QUALIFICATION_LEASE_ID" "$QUALIFICATION_LEASE_TOKEN" \
      "$QUALIFICATION_RETAINED_RUNS" "$QUALIFICATION_RETENTION_AGE_SECONDS" || exit_code=1
  fi
  if [[ "$KEEP_STACK" -eq 0 && -n "$QUALIFICATION_CACHE_LEASE_TOKEN" && "$QUALIFICATION_CACHE_LEASE_RELEASED" -eq 0 ]]; then
    "$SCRIPT_DIR/qualification-swift-cache.sh" release \
      "$SHA" "$QUALIFICATION_CACHE_LEASE_ID" "$$" "$QUALIFICATION_CACHE_LEASE_TOKEN" || exit_code=1
  fi
  qualification_stage_remove "$QUALIFICATION_STAGE" || true
  exit "$exit_code"
}
trap early_cleanup EXIT

QUALIFICATION_PORT_OFFSET="${OMI_QUALIFICATION_PORT_OFFSET:-}"
if [[ -z "$QUALIFICATION_PORT_OFFSET" ]]; then
  QUALIFICATION_PORT_OFFSET="$(python3 - "$SHA" "$QUALIFICATION_LEASE_ID" <<'PY'
import sys
import hashlib
print(1000 + (int(hashlib.sha256(": ".join(sys.argv[1:]).encode()).hexdigest()[:8], 16) % 2000))
PY
)"
fi
if ! [[ "$QUALIFICATION_PORT_OFFSET" =~ ^[0-9]+$ ]]; then
  echo "OMI_QUALIFICATION_PORT_OFFSET must be a non-negative integer" >&2
  exit 2
fi
export OMI_QUALIFICATION_LEASE_ROOT="$QUALIFICATION_LEASE_ROOT"
export OMI_LOCAL_STATE_ROOT="$QUALIFICATION_LEASE_ROOT/state"
export OMI_LOCAL_INSTANCE="$QUALIFICATION_LEASE_ID"
export OMI_HARNESS_PORT_OFFSET="$QUALIFICATION_PORT_OFFSET"
export OMI_AUTOMATION_PORT="$((47777 + QUALIFICATION_PORT_OFFSET))"
if (( OMI_AUTOMATION_PORT > 65535 )); then
  echo "OMI_QUALIFICATION_PORT_OFFSET makes OMI_AUTOMATION_PORT invalid: $OMI_AUTOMATION_PORT" >&2
  exit 2
fi

# Provision the tag-pinned backend venv so the hermetic stack resolves the
# locked Python dependencies. The ephemeral Codemagic Mac has no backend venv
# and no global python3 with backend deps, so this must succeed there — but a
# freshly installed uv may not carry the exact pinned patch
# (python-build-standalone lags), so fall back to the pinned minor version and
# still sync the exact platform lock. Machines without uv keep the legacy
# global-python3 resolution.
provision_backend_venv() {
  local worktree="$1"
  local backend="$worktree/backend"
  [[ -f "$backend/.python-version" ]] || { echo "no backend/.python-version; skipping venv provisioning"; return 0; }
  local pinned minor lock
  pinned="$(tr -d '[:space:]' < "$backend/.python-version")"
  minor="${pinned%.*}"
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64 | Darwin-aarch64) lock="pylock.macos.toml" ;;
    Darwin-x86_64 | Darwin-amd64) lock="pylock.macos-x86_64.toml" ;;
    *) lock="pylock.toml" ;;
  esac
  # Preferred path: exact-patch parity with CI via the shared script.
  if (cd "$worktree" && make setup-backend); then
    return 0
  fi
  echo "make setup-backend failed (likely exact patch $pinned unavailable to this uv); falling back to minor $minor"
  [[ -f "$backend/$lock" ]] || { echo "no $lock for this platform; cannot provision backend venv" >&2; return 1; }
  (
    cd "$backend"
    uv venv --allow-existing --python "$minor" .venv
    uv pip sync "$lock" --python .venv/bin/python
  )
}

if command -v uv >/dev/null 2>&1; then
  provision_backend_venv "$WORKTREE"
else
  echo "uv not found; qualification lease requires the backend virtualenv" >&2
fi

qualification_lease_field() {
  local field="$1" lease_json="$2" value
  if value="$(printf '%s' "$lease_json" | python3 -c '
import json
import sys

field = sys.argv[1]
value = json.loads(sys.stdin.read()).get(field)
if not isinstance(value, str) or not value:
    raise SystemExit(1)
print(value)
' "$field" 2>/dev/null)"; then
    printf '%s\n' "$value"
    return 0
  fi
  echo "qualification failed: lease acquisition returned no valid ${field}" >&2
  return 1
}

LEASE_JSON="$("$LEASE_COMMAND" acquire "$WORKTREE" "$QUALIFICATION_LEASE_ID" "$$" "$QUALIFICATION_PORT_OFFSET" "$QUALIFICATION_RETAINED_RUNS")"
QUALIFICATION_LEASE_TOKEN="$(qualification_lease_field token "$LEASE_JSON")"
QUALIFICATION_LOG_DIR="$(qualification_lease_field log_dir "$LEASE_JSON")"
# This capability is distinct from the lease token. It is passed only to the
# launched named app and binds the detached LaunchServices process to this run.
DESKTOP_LAUNCH_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
DESKTOP_LAUNCH_RECORD="$QUALIFICATION_LOG_DIR/desktop-app.json"
LAUNCH_SIGNAL_FILE="$QUALIFICATION_LOG_DIR/desktop-launch.signal"
if [[ -n "$QUALIFICATION_CLEANUP_CONTEXT" ]]; then
  umask 077
  python3 - "$QUALIFICATION_CLEANUP_CONTEXT" "$QUALIFICATION_LEASE_ID" "$QUALIFICATION_LEASE_TOKEN" "$WORKTREE" "$QUALIFICATION_RETAINED_RUNS" "$QUALIFICATION_RETENTION_AGE_SECONDS" "$SHA" "$QUALIFICATION_CACHE_LEASE_ID" "$$" "$QUALIFICATION_CACHE_LEASE_TOKEN" <<'PY'
import json
import sys
from pathlib import Path

(
    path, lease_id, token, worktree, retained_runs, retention_age,
    cache_source_sha, cache_lease_id, cache_owner_pid, cache_token,
) = map(str, sys.argv[1:])
target = Path(path)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({
    "lease_id": lease_id,
    "token": token,
    "worktree": worktree,
    "retained_runs": int(retained_runs),
    "retention_age_seconds": int(retention_age),
    "cache_source_sha": cache_source_sha,
    "cache_lease_id": cache_lease_id,
    "cache_owner_pid": int(cache_owner_pid),
    "cache_token": cache_token,
}, sort_keys=True) + "\n", encoding="utf-8")
target.chmod(0o600)
PY
fi
LAUNCH_LOG="$QUALIFICATION_LOG_DIR/desktop-launch.log"
phase_end passed

resolve_automation_port() {
  (
    cd "$WORKTREE"
    # shellcheck source=../../scripts/dev-instance.sh
    source "$WORKTREE/scripts/dev-instance.sh"
    printf '%s\n' "$AUTOMATION_PORT"
  )
}

AUTOMATION_PORT="$(resolve_automation_port)"

derive_bundle_id() {
  local app_name="$1"
  # shellcheck source=app-config.sh
  source "$REPO_ROOT/desktop/macos/scripts/app-config.sh"
  derive_omi_app_config "$app_name"
  printf '%s\n' "$BUNDLE_ID"
}

record_owned_qualification_desktop() {
  local bundle_id app_path executable_path
  bundle_id="$(derive_bundle_id "$BUNDLE")"
  app_path="/Applications/${BUNDLE}.app"
  executable_path="$app_path/Contents/MacOS/Omi Computer"
  umask 077
  python3 - "$DESKTOP_LAUNCH_RECORD" "$LAUNCH_SIGNAL_FILE" "$DESKTOP_LAUNCH_TOKEN" "$BUNDLE" "$bundle_id" "$app_path" "$executable_path" "$AUTOMATION_PORT" <<'PY'
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

record_path, signal_path, token, bundle, bundle_id, app_path, executable_path, port = sys.argv[1:]
signal = Path(signal_path)
if not signal.is_file() or signal.stat().st_uid != os.getuid() or stat.S_IMODE(signal.stat().st_mode) != 0o600:
    raise SystemExit("qualification launch signal is missing or not owner-only")
fields = {}
for line in signal.read_text(encoding="utf-8").splitlines():
    if "=" not in line:
        raise SystemExit("qualification launch signal is malformed")
    key, value = line.split("=", 1)
    if key in fields:
        raise SystemExit("qualification launch signal has duplicate fields")
    fields[key] = value
expected_signal = {
    "schema_version": "1", "bundle_id": bundle_id, "app_path": app_path,
    "executable_path": executable_path, "launch_token": token,
}
if any(fields.get(key) != value for key, value in expected_signal.items()):
    raise SystemExit("qualification launch signal does not bind this run")
if fields.get("launch_transport") not in {"open", "direct"}:
    raise SystemExit("qualification launch signal has unknown transport")
proc = subprocess.run(["ps", "-axo", "pid=,lstart=,command="], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
matches = []
for line in proc.stdout.splitlines():
    parts = line.split(None, 6)
    if len(parts) != 7 or not parts[0].isdigit():
        continue
    pid, started, command = int(parts[0]), " ".join(parts[1:6]), parts[6]
    if executable_path in command and f"--omi-launch-token={token}" in command:
        matches.append((pid, started, command))
if len(matches) != 1:
    raise SystemExit(f"qualification launch ownership is ambiguous (matching processes={len(matches)})")
pid, started, command = matches[0]
payload = {
    "schema_version": 1,
    "launch_token": token,
    "bundle": bundle,
    "bundle_id": bundle_id,
    "app_path": app_path,
    "executable_path": executable_path,
    "automation_port": int(port),
    "launch_transport": fields["launch_transport"],
    "launch_pid": pid,
    "process_start": started,
    "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
}
target = Path(record_path)
target.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
target.chmod(0o600)
PY
}

validated_qualification_desktop_pid() {
  local bundle_id
  [[ -n "$DESKTOP_LAUNCH_RECORD" && -f "$DESKTOP_LAUNCH_RECORD" ]] || return 1
  bundle_id="$(derive_bundle_id "$BUNDLE")"
  python3 - "$DESKTOP_LAUNCH_RECORD" "$DESKTOP_LAUNCH_TOKEN" "$BUNDLE" "$bundle_id" "$AUTOMATION_PORT" <<'PY'
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

path, token, bundle, bundle_id, port = sys.argv[1:]
target = Path(path)
if target.stat().st_uid != os.getuid() or stat.S_IMODE(target.stat().st_mode) != 0o600:
    raise SystemExit("qualification app record is not owner-only")
payload = json.loads(target.read_text(encoding="utf-8"))
expected = {
    "schema_version": 1,
    "launch_token": token,
    "bundle": bundle,
    "bundle_id": bundle_id,
    "app_path": f"/Applications/{bundle}.app",
    "executable_path": f"/Applications/{bundle}.app/Contents/MacOS/Omi Computer",
    "automation_port": int(port),
}
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit("qualification app record does not bind this run")
if payload.get("launch_transport") not in {"open", "direct"}:
    raise SystemExit("qualification app record has unknown transport")
if not isinstance(payload.get("launch_pid"), int) or payload["launch_pid"] <= 0 or not isinstance(payload.get("process_start"), str) or not isinstance(payload.get("command_sha256"), str):
    raise SystemExit("qualification app record has no launch metadata")
pid = str(payload["launch_pid"])
proc = subprocess.run(["ps", "-p", pid, "-o", "lstart=,command="], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
line = proc.stdout.strip()
if not line:
    raise SystemExit(3)
parts = line.split(None, 5)
if len(parts) != 6:
    raise SystemExit("qualification process metadata cannot be parsed")
started, command = " ".join(parts[:5]), parts[5]
if started != payload["process_start"] or payload["executable_path"] not in command or f"--omi-launch-token={token}" not in command or hashlib.sha256(command.encode()).hexdigest() != payload["command_sha256"]:
    raise SystemExit("qualification process no longer matches launch provenance")
print(pid)
PY
}

automation_port_is_bound() {
  lsof -nP -iTCP:"$AUTOMATION_PORT" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_automation_port_release() {
  for _ in $(seq 1 50); do
    if ! automation_port_is_bound; then
      return 0
    fi
    sleep 0.1
  done
  echo "qualification automation port remains bound after owned app cleanup: $AUTOMATION_PORT" >&2
  return 1
}

stop_recorded_qualification_desktop() {
  local pid status
  set +e
  pid="$(validated_qualification_desktop_pid)"
  status=$?
  set -e
  if [[ "$status" -eq 3 ]]; then
    return 0
  fi
  if [[ "$status" -ne 0 || ! "$pid" =~ ^[1-9][0-9]*$ ]]; then
    echo "qualification failed: refusing unproven qualification app cleanup" >&2
    return 1
  fi
  kill -TERM "$pid" 2>/dev/null || return 1
  for _ in $(seq 1 50); do
    set +e
    validated_qualification_desktop_pid >/dev/null
    status=$?
    set -e
    [[ "$status" -eq 3 ]] && return 0
    if [[ "$status" -ne 0 ]]; then
      echo "qualification failed: qualification app ownership changed during TERM cleanup" >&2
      return 1
    fi
    sleep 0.1
  done
  # Escalate only after fresh provenance validation of this exact owned process.
  pid="$(validated_qualification_desktop_pid)" || {
    echo "qualification failed: qualification app ownership changed before KILL cleanup" >&2
    return 1
  }
  kill -KILL "$pid" 2>/dev/null || return 1
  for _ in $(seq 1 50); do
    set +e
    validated_qualification_desktop_pid >/dev/null
    status=$?
    set -e
    [[ "$status" -eq 3 ]] && return 0
    if [[ "$status" -ne 0 ]]; then
      echo "qualification failed: qualification app ownership changed during KILL cleanup" >&2
      return 1
    fi
    sleep 0.1
  done
  echo "qualification failed: owned qualification app did not stop; preserving lease evidence" >&2
  return 1
}

terminate_qualification_desktop() {
  if ! stop_recorded_qualification_desktop; then
    return 1
  fi
  wait_for_automation_port_release
}

wait_for_desktop_launch() {
  local signal_file="$1"
  local deadline=$((SECONDS + DESKTOP_PREPARE_WAIT_SECS))
  while (( SECONDS < deadline )); do
    if [[ -f "$signal_file" ]]; then
      echo "desktop launch dispatched after bounded preparation"
      return 0
    fi
    if [[ -n "$DESKTOP_LAUNCH_PID" ]] && ! kill -0 "$DESKTOP_LAUNCH_PID" 2>/dev/null; then
      echo "qualification failed: desktop launch process exited during preparation" >&2
      return 1
    fi
    sleep 5
  done
  echo "qualification failed: desktop launch not dispatched within ${DESKTOP_PREPARE_WAIT_SECS}s" >&2
  return 1
}

wait_for_bridge() {
  local port="$1"
  local expected_bundle_id
  expected_bundle_id="$(derive_bundle_id "$BUNDLE")"
  local deadline=$((SECONDS + BRIDGE_WAIT_SECS))
  while (( SECONDS < deadline )); do
    if python3 - "$port" "$expected_bundle_id" <<'PY'
import json
import sys
import urllib.error
import urllib.request

port, expected_bundle_id = sys.argv[1:]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("ok") and payload.get("bundleIdentifier") == expected_bundle_id:
        raise SystemExit(0)
except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
    pass
raise SystemExit(1)
PY
    then
      echo "automation bridge healthy on port $port"
      return 0
    fi
    if [[ -n "$DESKTOP_LAUNCH_PID" ]] && ! kill -0 "$DESKTOP_LAUNCH_PID" 2>/dev/null; then
      echo "qualification failed: desktop launch process exited before bridge became healthy" >&2
      return 1
    fi
    sleep 5
  done
  echo "qualification failed: automation bridge not healthy within ${BRIDGE_WAIT_SECS}s (port $port)" >&2
  return 1
}

run_qualification_cleanup() {
  if [[ "$QUALIFICATION_CLEANUP_DONE" -eq 1 ]]; then
    [[ "$QUALIFICATION_CLEANUP_STATUS" == released || "$QUALIFICATION_CLEANUP_STATUS" == retained ]]
    return
  fi
  QUALIFICATION_CLEANUP_DONE=1
  if [[ "$DESKTOP_LAUNCH_REQUESTED" -eq 1 ]]; then
    if ! terminate_qualification_desktop "$BUNDLE"; then
      QUALIFICATION_CLEANUP_STATUS="app-cleanup-failed"
      return 1
    fi
  fi
  if [[ "$KEEP_STACK" -eq 0 && -n "$QUALIFICATION_LEASE_TOKEN" && -d "$WORKTREE" ]]; then
    if ! "$LEASE_COMMAND" release "$WORKTREE" "$QUALIFICATION_LEASE_ID" "$QUALIFICATION_LEASE_TOKEN" "$QUALIFICATION_RETAINED_RUNS" "$QUALIFICATION_RETENTION_AGE_SECONDS"; then
      QUALIFICATION_CLEANUP_STATUS="release-failed"
      return 1
    fi
    if ! "$SCRIPT_DIR/qualification-swift-cache.sh" release \
      "$SHA" "$QUALIFICATION_CACHE_LEASE_ID" "$$" "$QUALIFICATION_CACHE_LEASE_TOKEN"; then
      QUALIFICATION_CLEANUP_STATUS="cache-release-failed"
      return 1
    fi
    QUALIFICATION_CACHE_LEASE_RELEASED=1
    QUALIFICATION_CLEANUP_STATUS="released"
  elif [[ "$KEEP_STACK" -eq 1 && -n "$QUALIFICATION_LEASE_TOKEN" ]]; then
    echo "qualification stack retained under lease $QUALIFICATION_LEASE_ID for safe later reclamation"
    QUALIFICATION_CLEANUP_STATUS="retained"
  fi
}

cleanup() {
  local exit_code=$?
  if [[ -n "$ACTIVE_PHASE" ]]; then
    phase_end failed
  fi
  if [[ "$QUALIFICATION_CLEANUP_DONE" -eq 0 ]]; then
    phase_begin "final-cleanup" "runner-hygiene-cleanup"
    if ! run_qualification_cleanup; then
      phase_end failed
      echo "qualification cleanup failed; preserving qualification lease and preventing success evidence" >&2
      [[ "$exit_code" -ne 0 ]] || exit_code=1
    else
      phase_end passed
    fi
  fi
  if [[ -n "$QUALIFICATION_LOG_DIR" ]]; then
    python3 - "$QUALIFICATION_LOG_DIR/cleanup.json" "$QUALIFICATION_LEASE_ID" "$QUALIFICATION_CLEANUP_STATUS" "$exit_code" <<'PY'
import json
import sys
from pathlib import Path
path, lease_id, status, exit_code = sys.argv[1:]
Path(path).write_text(json.dumps({"lease_id": lease_id, "cleanup_status": status, "exit_code": int(exit_code)}, sort_keys=True) + "\n", encoding="utf-8")
PY
  fi
  qualification_stage_remove "$QUALIFICATION_STAGE" || true
  exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [[ "$AUTOMATIC" -eq 1 ]]; then
  FAULT_PREFLIGHT_PORT="$((AUTOMATION_PORT + 2))"
  if (( FAULT_PREFLIGHT_PORT > 65535 )); then
    echo "qualification failed: fault-listener preflight port is invalid: $FAULT_PREFLIGHT_PORT" >&2
    exit 2
  fi
  phase_begin "fault-listener-preflight" "runner-hygiene-cleanup"
  if ! OMI_FAULT_STATE_DIR="$QUALIFICATION_LEASE_ROOT/state/$QUALIFICATION_LEASE_ID/fault" \
    OMI_FAULT_OWNERSHIP_TOKEN="$QUALIFICATION_LEASE_TOKEN" \
    "$WORKTREE/desktop/macos/scripts/omi-fault-inject.sh" start error --port "$FAULT_PREFLIGHT_PORT" >/dev/null; then
    python3 - "$FAULT_PREFLIGHT_REPORT" "$QUALIFICATION_LEASE_ID" "$FAULT_PREFLIGHT_PORT" <<'PY'
import json
import sys
from pathlib import Path

path, lease_id, port = sys.argv[1:]
target = Path(path)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({
    "schema_version": 1,
    "gate": "fault-listener-provenance-cleanup",
    "classification": "runner-hygiene-cleanup",
    "lease_id": lease_id,
    "status": "failed",
    "port": int(port),
    "failure_reason": "listener-start-prerequisite-unmet",
}, sort_keys=True) + "\n", encoding="utf-8")
target.chmod(0o600)
PY
    phase_end failed
    echo "qualification failed: host prerequisite could not start the disposable fault listener on port $FAULT_PREFLIGHT_PORT" >&2
    exit 1
  fi
  if ! "$LEASE_COMMAND" preflight-fault-cleanup "$WORKTREE" "$QUALIFICATION_LEASE_ID" "$QUALIFICATION_LEASE_TOKEN" "$FAULT_PREFLIGHT_REPORT"; then
    phase_end failed
    failure_reason="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("failure_reason", "host-prerequisite-unmet"))' "$FAULT_PREFLIGHT_REPORT")"
    echo "qualification failed: fault-listener host prerequisite was not established ($failure_reason); listener retained" >&2
    exit 1
  fi
  phase_end passed
fi

phase_begin "desktop-preparation" "runner-hygiene-cleanup"
"$SCRIPT_DIR/prepare-qualification-profile.sh" "$BUNDLE"
rm -f "$LAUNCH_SIGNAL_FILE"

DESKTOP_LAUNCH_REQUESTED=1
(
  cd "$WORKTREE"
  OMI_HARNESS_OWNERSHIP_TOKEN="$QUALIFICATION_LEASE_TOKEN" PROVIDER_MODE=offline make dev-up
  OMI_DESKTOP_LAUNCH_SIGNAL_FILE="$LAUNCH_SIGNAL_FILE" \
    OMI_DESKTOP_LAUNCH_TOKEN="$DESKTOP_LAUNCH_TOKEN" \
    OMI_SKIP_SETTINGS_SEED=1 \
    make desktop-run-local DESKTOP_APP_NAME="$BUNDLE" DESKTOP_USER=alice
) >"$LAUNCH_LOG" 2>&1 &
DESKTOP_LAUNCH_PID=$!

if ! wait_for_desktop_launch "$LAUNCH_SIGNAL_FILE"; then
  phase_end failed
  echo "--- last 80 lines of $LAUNCH_LOG ---" >&2
  tail -n 80 "$LAUNCH_LOG" >&2 || true
  exit 1
fi
phase_end passed

# The bridge gets its complete post-launch readiness allowance; cold Rust,
# agent-runtime, SwiftPM, packaging, and signing work consumed only the separate
# bounded preparation phase above.
SECONDS=0

phase_begin "automation-bridge-readiness" "user-visible-behavioral-fault"
if ! wait_for_bridge "$AUTOMATION_PORT"; then
  phase_end failed
  echo "--- last 80 lines of $LAUNCH_LOG ---" >&2
  tail -n 80 "$LAUNCH_LOG" >&2 || true
  exit 1
fi
if ! record_owned_qualification_desktop; then
  phase_end failed
  echo "qualification failed: could not establish owner-only desktop launch provenance" >&2
  exit 1
fi
phase_end passed

if [[ "$AUTOMATIC" -eq 1 ]]; then
  phase_begin "static-self-check" "immutable-artifact-security"
  if ! (
    cd "$WORKTREE/desktop/macos"
    ./scripts/desktop-core-harness.sh --self-check --skip-backend-contracts
  ); then
    phase_end failed
    exit 1
  fi
  phase_end passed
fi

phase_begin "tier-2-user-flows" "user-visible-behavioral-fault"
if ! (
  cd "$WORKTREE/desktop/macos"
  ./scripts/desktop-core-harness.sh --tier 2 --bundle "$BUNDLE" --port "$AUTOMATION_PORT" --keep-stack
); then
  phase_end failed
  exit 1
fi

EVIDENCE=$(ls -td "$WORKTREE/desktop/macos/.harness/desktop-core"/* 2>/dev/null | head -1)
if [[ -z "$EVIDENCE" || ! -f "$EVIDENCE/manifest.json" ]]; then
  phase_end failed
  echo "qualification failed: missing harness evidence" >&2
  exit 1
fi

if ! python3 "$KEYVALUE_PY" check-manifest "$EVIDENCE/manifest.json"; then
  phase_end failed
  echo "qualification failed: tier 2 harness did not pass; evidence: $EVIDENCE" >&2
  exit 1
fi
phase_end passed

FAULT_EVIDENCE=""
if [[ "$AUTOMATIC" -eq 1 ]]; then
  phase_begin "fault-user-flow" "user-visible-behavioral-fault"
  if ! (
    cd "$WORKTREE/desktop/macos"
    OMI_FAULT_PORT="$((AUTOMATION_PORT + 2))" \
      OMI_FAULT_STATE_DIR="$QUALIFICATION_LEASE_ROOT/state/$QUALIFICATION_LEASE_ID/fault" \
      OMI_FAULT_OWNERSHIP_TOKEN="$QUALIFICATION_LEASE_TOKEN" \
      ./scripts/desktop-core-harness.sh --fault-suite --port "$((AUTOMATION_PORT + 1))"
  ); then
    phase_end failed
    exit 1
  fi
  FAULT_EVIDENCE=$(ls -td "$WORKTREE/desktop/macos/.harness/desktop-core"/*-fault 2>/dev/null | head -1)
  if [[ -z "$FAULT_EVIDENCE" || ! -f "$FAULT_EVIDENCE/manifest.json" ]]; then
    phase_end failed
    echo "automatic qualification failed: missing fault-suite evidence" >&2
    exit 1
  fi
  if ! python3 "$KEYVALUE_PY" check-fault-manifest "$FAULT_EVIDENCE/manifest.json"; then
    phase_end failed
    echo "automatic qualification failed: fault-suite manifest did not pass" >&2
    exit 1
  fi
  phase_end passed
fi

# Cleanup is a qualification gate, not best-effort EXIT housekeeping. Do this
# before any trusted workflow artifact or release evidence can claim success.
phase_begin "final-cleanup" "runner-hygiene-cleanup"
if ! run_qualification_cleanup; then
  phase_end failed
  echo "qualification cleanup failed; preserving qualification lease and preventing success evidence" >&2
  exit 1
fi
phase_end passed

if [[ "$GITHUB_ACTIONS_ARTIFACT" -eq 1 ]]; then
  QUALIFICATION_SUCCESS=1
  echo "Qualified $RELEASE_TAG for beta; trusted workflow will publish immutable Actions evidence."
  exit 0
fi

STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EVIDENCE_FILE="$QUALIFICATION_STAGE/qualification-evidence.json"
cp "$EVIDENCE/manifest.json" "$EVIDENCE_FILE"

if [[ "$AUTOMATIC" -eq 1 ]]; then
  git -C "$REPO_ROOT" fetch origin --tags --force
  LATEST_TAG=$(git -C "$REPO_ROOT" for-each-ref --count=1 --sort=-v:refname \
    --format='%(refname:strip=2)' 'refs/tags/v*-macos')
  if [[ "$LATEST_TAG" != "$RELEASE_TAG" ]]; then
    echo "automatic qualification stopped: newer candidate exists ($LATEST_TAG)" >&2
    exit 1
  fi
  python3 - "$EVIDENCE_FILE" "$SIGNED_SMOKE_RESULT" "$CANDIDATE_GATE_RESULT" "$FAULT_EVIDENCE/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

evidence_path, smoke_path, gate_path, fault_path = map(Path, sys.argv[1:5])
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
evidence["qualification_mode"] = "automatic"
evidence["signed_artifact_smoke"] = json.loads(smoke_path.read_text(encoding="utf-8"))
evidence["candidate_gate"] = json.loads(gate_path.read_text(encoding="utf-8"))
evidence["fault_suite"] = json.loads(fault_path.read_text(encoding="utf-8"))
evidence["automatic_gates"] = ["signed-artifact", "static-self-check", "tier-2", "fault-suite"]
evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
fi

# Qualification evidence is factual, immutable history. Its content digest is
# part of the asset identity and uploads never clobber an earlier observation.
EVIDENCE_SHA=$(shasum -a 256 "$EVIDENCE_FILE" | awk '{print $1}')
ASSET="qualification-evidence-${VERSION}-${EVIDENCE_SHA}.json"
ASSET_FILE="$QUALIFICATION_STAGE/$ASSET"
mv "$EVIDENCE_FILE" "$ASSET_FILE"

BODY_FILE="$QUALIFICATION_STAGE/release-body.md"
gh release view "$RELEASE_TAG" --repo BasedHardware/omi --json body --jq .body > "$BODY_FILE"

python3 "$KEYVALUE_PY" update-qualified-beta "$BODY_FILE" "$STAMP" "$SHA" "$ASSET"

gh release upload "$RELEASE_TAG" "$ASSET_FILE" --repo BasedHardware/omi
gh release edit "$RELEASE_TAG" --repo BasedHardware/omi --notes-file "$BODY_FILE"

QUALIFICATION_SUCCESS=1
echo "Qualified $RELEASE_TAG for beta at $SHA (evidence asset: $ASSET, automation port: $AUTOMATION_PORT)"
