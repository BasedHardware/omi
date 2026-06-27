#!/usr/bin/env bash

set -euo pipefail

PLIST_PATH=${PLIST_PATH:-"$HOME/Library/LaunchAgents/com.omi.onboarding-figma-sync.plist"}

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH"

echo "Uninstalled onboarding Figma sync LaunchAgent."
