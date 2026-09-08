#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/check-configuration.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

run_case() {
  local name="$1"
  local bot_token="$2"
  local chat_id="$3"
  local expected_enabled="$4"
  local expected_summary="$5"
  local output="$TMP_DIR/$name-output"
  local summary="$TMP_DIR/$name-summary"

  GITHUB_OUTPUT="$output" \
    GITHUB_STEP_SUMMARY="$summary" \
    TELEGRAM_BOT_TOKEN="$bot_token" \
    TELEGRAM_CHAT_ID="$chat_id" \
    bash "$SCRIPT"

  grep -Fxq "enabled=$expected_enabled" "$output"
  if [[ -n "$expected_summary" ]]; then
    grep -Fxq "$expected_summary" "$summary"
  elif [[ -s "$summary" ]]; then
    echo "expected no summary for configured Telegram notification" >&2
    return 1
  fi
}

run_case "missing-both" "" "" "false" "Skipped: Telegram bot token or chat ID is not configured."
run_case "missing-chat" "bot-token" "" "false" "Skipped: Telegram bot token or chat ID is not configured."
run_case "configured" "bot-token" "chat-id" "true" ""
