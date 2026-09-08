#!/usr/bin/env bash
# discovery-skip: needs a running app's automation token — run it directly against a live app
set -euo pipefail

PORT="${1:-${OMI_AUTOMATION_PORT:-47777}}"
MAX_MOUNT_MS="${OMI_MAX_MOUNT_MS:-1000}"
BASE="http://127.0.0.1:${PORT}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/automation-token-path.sh
source "$SCRIPT_DIR/../scripts/automation-token-path.sh"
TOKEN_FILE="$(omi_automation_token_file "$PORT")"

if [[ ! -s "$TOKEN_FILE" ]]; then
  echo "FAIL: automation token is unavailable for port $PORT" >&2
  exit 1
fi
TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"

navigate() {
  local target="$1"
  curl -fsS -X POST "$BASE/navigate" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    --data "{\"target\":\"$target\",\"activateApp\":false,\"waitForVisibility\":false}" >/dev/null
}

visible_route() {
  curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/state" \
    | python3 -c 'import json, sys; print((json.load(sys.stdin).get("result") or {}).get("visibleChatFirstRoute", ""))'
}

measure_mount() {
  local target="$1"
  local expected="$2"
  local started_ms
  started_ms="$(python3 -c 'import time; print(round(time.perf_counter() * 1000))')"
  navigate "$target"

  while true; do
    local current_ms elapsed_ms observed
    observed="$(visible_route)"
    current_ms="$(python3 -c 'import time; print(round(time.perf_counter() * 1000))')"
    elapsed_ms=$((current_ms - started_ms))
    if [[ "$observed" == "$expected" ]]; then
      echo "PASS: $target mounted as $expected in ${elapsed_ms}ms"
      return 0
    fi
    if (( elapsed_ms > MAX_MOUNT_MS )); then
      echo "FAIL: $target did not mount as $expected within ${MAX_MOUNT_MS}ms (last: ${observed:-none})" >&2
      return 1
    fi
    sleep 0.05
  done
}

measure_mount chat chat
measure_mount memories memories
measure_mount tasks tasks
measure_mount apps more.apps
measure_mount settings more.settings
measure_mount chat chat

echo "PASS: typed navigation acknowledgement and independently observed mounts meet the ${MAX_MOUNT_MS}ms budget"
