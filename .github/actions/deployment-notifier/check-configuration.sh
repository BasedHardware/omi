#!/usr/bin/env bash

set -euo pipefail

if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "enabled=true" >> "$GITHUB_OUTPUT"
  exit 0
fi

echo "enabled=false" >> "$GITHUB_OUTPUT"
{
  echo "### Telegram deployment notification"
  echo ""
  echo "Skipped: Telegram bot token or chat ID is not configured."
} >> "$GITHUB_STEP_SUMMARY"
