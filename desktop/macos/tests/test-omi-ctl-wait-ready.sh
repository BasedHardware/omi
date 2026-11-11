#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OMI_CTL="$SCRIPT_DIR/../scripts/omi-ctl"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-ctl-wait-ready.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

mkdir -p "$TMP_ROOT/bin"
printf 'test-token\n' > "$TMP_ROOT/token"

cat > "$TMP_ROOT/bin/curl" <<'SH'
#!/usr/bin/env bash
cat "${OMI_CTL_STATE_FIXTURE:?}"
SH
chmod +x "$TMP_ROOT/bin/curl"

run_wait_ready() {
  PATH="$TMP_ROOT/bin:$PATH" \
    OMI_AUTOMATION_TOKEN_FILE="$TMP_ROOT/token" \
    OMI_CTL_STATE_FIXTURE="$1" \
    "$OMI_CTL" wait-ready 1
}

write_state() {
  local path="$1"
  local signed_in="$2"
  local restoring="$3"
  local onboarded="$4"
  local stale="$5"
  python3 - "$path" "$signed_in" "$restoring" "$onboarded" "$stale" <<'PY'
import json
import sys

path, signed_in, restoring, onboarded, stale = sys.argv[1:]
json.dump({"ok": True, "result": {
    "appState": "main",
    "isSignedIn": signed_in == "true",
    "isRestoringAuth": restoring == "true",
    "hasCompletedOnboarding": onboarded == "true",
    "snapshotStale": stale == "true",
}}, open(path, "w", encoding="utf-8"))
PY
}

for case in signed-out restoring owner-not-ready stale-snapshot; do
  fixture="$TMP_ROOT/$case.json"
  case "$case" in
    signed-out) write_state "$fixture" false false true false ;;
    restoring) write_state "$fixture" true true true false ;;
    owner-not-ready) write_state "$fixture" true false false false ;;
    stale-snapshot) write_state "$fixture" true false true true ;;
  esac
  if run_wait_ready "$fixture" >/dev/null 2>&1; then
    echo "FAIL: wait-ready accepted $case main snapshot" >&2
    exit 1
  fi
done

ready="$TMP_ROOT/ready.json"
write_state "$ready" true false true false
run_wait_ready "$ready" >/dev/null
echo "omi-ctl authenticated semantic readiness tests passed"