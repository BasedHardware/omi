#!/usr/bin/env bash
# Prove the offline M1 qualification lease/listener lifecycle without launching
# a desktop app, reading release credentials, or mutating a release channel.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LEASE_COMMAND="$SCRIPT_DIR/qualification-lease-command.sh"
KEYVALUE_PY="$SCRIPT_DIR/release-keyvalue.py"
FAULT_INJECTOR="$SCRIPT_DIR/omi-fault-inject.sh"

OFFLINE=0
FAST=0
RESULT_PATH=""
RELEASE_TAG=""
LEASE_ID=""
LEASE_TOKEN=""
LEASE_ACQUIRED=0
LEASE_RELEASE_ATTEMPTED=0
CLEANUP_STATUS="not-acquired"
FAILURE_REASON=""
COMPLETED_BOUNDARIES=""
FAULT_REPORT=""

usage() {
  cat <<'USAGE'
Usage:
  qualification-local-proof.sh --offline [--fast] --result PATH <vX.Y.Z+BUILD-macos>

Options:
  --offline      Required: prohibit network/release authority and exercise only local lifecycle boundaries
  --fast         Deterministic CI pre-dispatch mode; never launches the desktop UI or full user-flow suite
  --result PATH  Write the redacted proof result JSON here
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --offline)
      OFFLINE=1
      shift
      ;;
    --fast)
      FAST=1
      shift
      ;;
    --result)
      [[ $# -ge 2 && -n "${2:-}" && "${2:-}" != -* ]] || { echo "--result requires a path" >&2; exit 2; }
      RESULT_PATH="$2"
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
      [[ -z "$RELEASE_TAG" ]] || { echo "unexpected extra argument: $1" >&2; exit 2; }
      RELEASE_TAG="$1"
      shift
      ;;
  esac
done

[[ "$OFFLINE" -eq 1 ]] || { echo "qualification local proof requires explicit --offline mode" >&2; exit 2; }
[[ -n "$RESULT_PATH" ]] || { echo "qualification local proof requires --result" >&2; exit 2; }
[[ -n "$RELEASE_TAG" ]] || { echo "qualification local proof requires a release tag" >&2; exit 2; }
[[ "$(uname -s)" == Darwin ]] || { echo "qualification local proof requires macOS" >&2; exit 1; }

RESULT_PATH="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$RESULT_PATH")"
FAULT_REPORT="${RESULT_PATH%.json}-fault-listener.json"
mkdir -p "$(dirname "$RESULT_PATH")"

append_boundary() {
  if [[ -n "$COMPLETED_BOUNDARIES" ]]; then
    COMPLETED_BOUNDARIES+=","
  fi
  COMPLETED_BOUNDARIES+="$1"
}

write_result() {
  local status="$1" reason="${2:-}" source_sha="${3:-}" mode="offline"
  [[ "$FAST" -eq 0 ]] || mode="offline-fast"
  umask 077
  python3 - "$RESULT_PATH" "$status" "$reason" "$mode" "$RELEASE_TAG" "$source_sha" "$CLEANUP_STATUS" "$COMPLETED_BOUNDARIES" "$FAULT_REPORT" <<'PY'
import json
import sys
from pathlib import Path

path, status, reason, mode, release_tag, source_sha, cleanup_status, boundaries, fault_report = sys.argv[1:]
fault_path = Path(fault_report)
fault_result = None
if fault_path.is_file():
    observed = json.loads(fault_path.read_text(encoding="utf-8"))
    fault_result = {
        key: observed.get(key)
        for key in ("schema_version", "gate", "classification", "status", "port", "failure_reason")
    }
payload = {
    "schema_version": 1,
    "proof": "local-qualification-lifecycle",
    "mode": mode,
    "release_tag": release_tag,
    "source_sha": source_sha or None,
    "status": status,
    "failure_reason": reason or None,
    "cleanup_status": cleanup_status,
    "completed_boundaries": [item for item in boundaries.split(",") if item],
    "fault_listener_result": fault_result,
}
target = Path(path)
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
target.chmod(0o600)
PY
}

release_owned_lease() {
  if [[ "$LEASE_ACQUIRED" -eq 0 ]]; then
    return 0
  fi
  if [[ "$LEASE_RELEASE_ATTEMPTED" -eq 1 ]]; then
    return 1
  fi
  LEASE_RELEASE_ATTEMPTED=1
  if "$LEASE_COMMAND" release "$REPO_ROOT" "$LEASE_ID" "$LEASE_TOKEN" 3 1209600; then
    LEASE_ACQUIRED=0
    CLEANUP_STATUS="released"
    append_boundary "cleanup-finalization"
    return 0
  fi
  CLEANUP_STATUS="release-failed"
  return 1
}

finalize() {
  local exit_code=$?
  trap - EXIT INT TERM HUP
  if [[ "$LEASE_ACQUIRED" -eq 1 ]] && ! release_owned_lease; then
    [[ -n "$FAILURE_REASON" ]] || FAILURE_REASON="cleanup-finalization-failed"
    [[ "$exit_code" -ne 0 ]] || exit_code=1
  fi
  if [[ "$exit_code" -eq 0 ]]; then
    write_result passed "" "${SOURCE_SHA:-}"
  else
    [[ -n "$FAILURE_REASON" ]] || FAILURE_REASON="local-proof-failed"
    write_result failed "$FAILURE_REASON" "${SOURCE_SHA:-}"
  fi
  exit "$exit_code"
}
trap finalize EXIT
trap 'FAILURE_REASON="interrupted"; exit 130' INT
trap 'FAILURE_REASON="terminated"; exit 143' TERM
trap 'FAILURE_REASON="hangup"; exit 129' HUP

python3 "$KEYVALUE_PY" validate-tag "$RELEASE_TAG" >/dev/null
SOURCE_SHA="$(git -C "$REPO_ROOT" rev-parse "refs/tags/${RELEASE_TAG}^{commit}")" || {
  FAILURE_REASON="release-tag-not-local"
  exit 1
}
if [[ "$SOURCE_SHA" != "$(git -C "$REPO_ROOT" rev-parse 'HEAD^{commit}')" ]]; then
  FAILURE_REASON="checkout-does-not-match-release-tag"
  echo "qualification local proof requires HEAD to match $RELEASE_TAG" >&2
  exit 1
fi
append_boundary "release-tag-validation"

RUN_SCOPE="${BASHPID:-$$}"
LEASE_ID="qualification-proof-${SOURCE_SHA:0:12}-${RUN_SCOPE}"
PORT_OFFSET="$(python3 - "$SOURCE_SHA" "$LEASE_ID" <<'PY'
import hashlib
import sys
print(1000 + (int(hashlib.sha256(": ".join(sys.argv[1:]).encode()).hexdigest()[:8], 16) % 2000))
PY
)"
FAULT_PORT="$((47777 + PORT_OFFSET + 2))"
if (( FAULT_PORT > 65535 )); then
  FAILURE_REASON="invalid-fault-port"
  exit 1
fi

export OMI_LOCAL_STATE_ROOT="${OMI_QUALIFICATION_LEASE_ROOT:-${TMPDIR:-/tmp}/omi-desktop-qualification}/state"
export OMI_LOCAL_INSTANCE="$LEASE_ID"
export OMI_HARNESS_PORT_OFFSET="$PORT_OFFSET"

ACQUIRE_ERROR="$(mktemp "${TMPDIR:-/tmp}/omi-qualification-local-proof-acquire.XXXXXX")"
if ! LEASE_JSON="$("$LEASE_COMMAND" acquire "$REPO_ROOT" "$LEASE_ID" "$$" "$PORT_OFFSET" 3 2>"$ACQUIRE_ERROR")"; then
  if grep -Fq "lineage is unproven" "$ACQUIRE_ERROR"; then
    FAILURE_REASON="unproven-stale-listener"
  else
    FAILURE_REASON="lease-acquisition-failed"
  fi
  cat "$ACQUIRE_ERROR" >&2
  rm -f "$ACQUIRE_ERROR"
  exit 1
fi
rm -f "$ACQUIRE_ERROR"
LEASE_TOKEN="$(printf '%s' "$LEASE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
LEASE_ACQUIRED=1
CLEANUP_STATUS="pending"
append_boundary "lease-provenance-acquisition"

if ! OMI_FAULT_STATE_DIR="${OMI_LOCAL_STATE_ROOT}/${LEASE_ID}/fault" \
  OMI_FAULT_OWNERSHIP_TOKEN="$LEASE_TOKEN" \
  "$FAULT_INJECTOR" start error --port "$FAULT_PORT" >/dev/null; then
  FAILURE_REASON="fault-listener-start-failed"
  exit 1
fi
append_boundary "disposable-fault-listener-start"

if ! "$LEASE_COMMAND" preflight-fault-cleanup "$REPO_ROOT" "$LEASE_ID" "$LEASE_TOKEN" "$FAULT_REPORT"; then
  FAILURE_REASON="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("failure_reason") or "fault-listener-preflight-failed")' "$FAULT_REPORT")"
  exit 1
fi
append_boundary "runner-hygiene-preflight"

if ! release_owned_lease; then
  FAILURE_REASON="cleanup-finalization-failed"
  exit 1
fi

echo "qualification local proof passed: $RESULT_PATH"
