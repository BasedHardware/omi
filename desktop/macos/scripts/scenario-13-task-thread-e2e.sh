#!/bin/bash
# Deterministic named-bundle proof for the task-backed thread slice of scenario 13.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="${OMI_APP_NAME:?Set OMI_APP_NAME to the running named bundle (omi-*)}"
case "$APP_NAME" in
  omi-*) ;;
  *) echo "scenario-13: refusing non-test app name '$APP_NAME'" >&2; exit 1 ;;
esac

BUNDLE_ID="com.omi.${APP_NAME}"
CAPTURE_ROOT="${OMI_AUTOMATION_CAPTURE_ROOT:-${TMPDIR:-/tmp}/omi-harness}"
EVIDENCE_DIR="${OMI_SCENARIO_EVIDENCE_DIR:-$CAPTURE_ROOT/scenario-13-task-thread}"
mkdir -p "$EVIDENCE_DIR"

ctl() {
  "$ROOT/scripts/omi-ctl" "$@"
}

capture_window() {
  local output="$1"
  local token_file="${OMI_AUTOMATION_TOKEN_FILE:-${TMPDIR:-/tmp}/omi-automation-${OMI_AUTOMATION_PORT:-47777}.token}"
  local token="${OMI_AUTOMATION_TOKEN:-}"
  [ -n "$token" ] || token="$(tr -d '\r\n' < "$token_file")"
  local body
  body="$(jq -nc --arg path "$output" '{path:$path,target:"task_thread"}')"
  for _ in 1 2 3; do
    if curl -fsS \
      -H "Authorization: Bearer $token" \
      -X POST "http://127.0.0.1:${OMI_AUTOMATION_PORT:-47777}/visual/export" \
      -d "$body" >/dev/null 2>&1 \
      && [ "$(stat -f %z "$output" 2>/dev/null || echo 0)" -gt 20000 ]; then
      return
    fi
    sleep 0.5
  done
  if command -v agent-swift >/dev/null 2>&1; then
    if agent-swift connect --bundle-id "$BUNDLE_ID" >/dev/null 2>&1 \
      && agent-swift screenshot "$output" >/dev/null 2>&1; then
      return
    fi
  fi
  screencapture -x "$output"
}

ctl state >"$EVIDENCE_DIR/app-state.json"

# Exercise the production app→kernel continuity RPCs against a persistent
# SQLite kernel before rendering the deterministic UI layer. The probe migrates
# a legacy task session, writes cited v1/v2, exports/imports a checkpoint across
# a real close/reopen, replays v2 idempotently, and evaluates external send via
# the control-tool boundary.
(cd "$ROOT/agent" && npm run build >/dev/null)
kernel_proof="$(cd "$ROOT/agent" && node scripts/scenario-13-kernel.mjs "$EVIDENCE_DIR/kernel.sqlite")"
printf '%s\n' "$kernel_proof" >"$EVIDENCE_DIR/kernel-continuity.json"
jq -e '
  .ok == true and
  .migratedTaskMappings == 1 and
  .copiedTurns == 1 and
  .conversationTurnsAfterRestart == 1 and
  .queuedDeliveriesAfterRestart >= 2 and
  .firstVersion == 1 and
  .secondVersion == 2 and
  .replayVersion == 2 and
  (.versions | map(.version) == [1, 2]) and
  (.versions | all(.cited == true)) and
  .externalSendDecision == "dispatch_required"
' <<<"$kernel_proof" >/dev/null

first="$(ctl action task_thread_scenario_13 task=first settleMs=250)"
printf '%s\n' "$first" >"$EVIDENCE_DIR/first-task.json"
first_workstream="$(jq -er '.result.detail.workstream_id' <<<"$first")"
first_session="$(jq -er '.result.detail.kernel_session_id' <<<"$first")"
jq -e '
  .ok == true and
  .result.detail.active_task_id == "scenario-13-task-draft" and
  .result.detail.kernel_surface == "workstream" and
  .result.detail.runtime_bridge == "live_app_kernel" and
  .result.detail.artifact_versions == "v2,v1" and
  .result.detail.cited_v2 == "true" and
  .result.detail.external_send_decision == "dispatch_required"
' <<<"$first" >/dev/null
capture_window "$EVIDENCE_DIR/first-task.png"

second="$(ctl action task_thread_scenario_13 task=second resume=true settleMs=250)"
printf '%s\n' "$second" >"$EVIDENCE_DIR/second-task.json"
second_workstream="$(jq -er '.result.detail.workstream_id' <<<"$second")"
jq -e '.result.detail.active_task_id == "scenario-13-task-review"' <<<"$second" >/dev/null
test "$first_workstream" = "$second_workstream"
test "$(jq -er '.result.detail.kernel_session_id' <<<"$second")" = "$first_session"
capture_window "$EVIDENCE_DIR/second-task.png"

send_decision="$(jq -r '.result.detail.external_send_decision' <<<"$first")"
test "$send_decision" = "dispatch_required"
printf '%s\n' "$send_decision" >"$EVIDENCE_DIR/external-send-without-grant.txt"

# Restart only the explicitly named test bundle and prove the same workstream is
# reprojected while the selected Task remains merely UI scope.
osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null 2>&1 || true
for _ in $(seq 1 40); do
  if ! pgrep -f "/Applications/${APP_NAME}.app/Contents/MacOS/" >/dev/null; then break; fi
  sleep 0.25
done
open -b "$BUNDLE_ID" --args \
  "--automation-port=${OMI_AUTOMATION_PORT:-47777}" \
  "--automation-capture-root=$CAPTURE_ROOT"
for _ in $(seq 1 80); do
  if ctl health >/dev/null 2>&1; then break; fi
  sleep 0.25
done
ctl state >"$EVIDENCE_DIR/app-state-after-restart.json"
resumed="$(ctl action task_thread_scenario_13 task=second resume=true settleMs=1000)"
printf '%s\n' "$resumed" >"$EVIDENCE_DIR/resumed-task.json"
resumed_workstream="$(jq -er '.result.detail.workstream_id' <<<"$resumed")"
test "$resumed_workstream" = "$first_workstream"
test "$(jq -er '.result.detail.kernel_session_id' <<<"$resumed")" = "$first_session"
jq -e '
  .result.detail.active_task_id == "scenario-13-task-review" and
  .result.detail.runtime_bridge == "live_app_kernel" and
  .result.detail.artifact_versions == "v2,v1" and
  .result.detail.cited_v2 == "true"
' <<<"$resumed" >/dev/null
capture_window "$EVIDENCE_DIR/resumed-task.png"

printf 'scenario-13 task thread passed: workstream=%s evidence=%s\n' "$first_workstream" "$EVIDENCE_DIR"
