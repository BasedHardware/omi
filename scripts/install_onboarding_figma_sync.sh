#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT_REPO=${SCRIPT_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}
WATCH_REPO=${WATCH_REPO:-$SCRIPT_REPO}
STATE_DIR=${STATE_DIR:-"$HOME/Library/Application Support/OMIOnboardingSync"}
EXPORT_REPO=${EXPORT_REPO:-"$STATE_DIR/export-worktree"}
PLIST_PATH=${PLIST_PATH:-"$HOME/Library/LaunchAgents/com.omi.onboarding-figma-sync.plist"}
CODEX_BIN=${CODEX_BIN:-$(command -v codex || true)}
NODE_BIN=${NODE_BIN:-$(command -v node || true)}

if [[ -z "$CODEX_BIN" || ! -x "$CODEX_BIN" ]]; then
  echo "codex binary not found in PATH; install it or set CODEX_BIN" >&2
  exit 1
fi

if [[ -z "$NODE_BIN" || ! -x "$NODE_BIN" ]]; then
  echo "node binary not found in PATH; install it or set NODE_BIN" >&2
  exit 1
fi

mkdir -p "$STATE_DIR" "$HOME/Library/LaunchAgents"

if [[ ! -e "$EXPORT_REPO" ]]; then
  git -C "$WATCH_REPO" worktree add "$EXPORT_REPO" HEAD
fi

cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.omi.onboarding-figma-sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>$SCRIPT_REPO/scripts/run_onboarding_figma_sync.sh</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>SOURCE_REPO</key>
    <string>$WATCH_REPO</string>
    <key>EXPORT_REPO</key>
    <string>$EXPORT_REPO</string>
    <key>STATE_DIR</key>
    <string>$STATE_DIR</string>
    <key>CODEX_BIN</key>
    <string>$CODEX_BIN</string>
    <key>NODE_BIN_DIR</key>
    <string>$(dirname "$NODE_BIN")</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>WatchPaths</key>
  <array>
    <string>$WATCH_REPO/desktop/Desktop/Sources</string>
    <string>$WATCH_REPO/desktop/Desktop/Resources</string>
  </array>
  <key>StandardOutPath</key>
  <string>$STATE_DIR/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>$STATE_DIR/launchd.err.log</string>
</dict>
</plist>
EOF

plutil -lint "$PLIST_PATH" >/dev/null
launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl kickstart -k "gui/$(id -u)/com.omi.onboarding-figma-sync"

echo "Installed onboarding Figma sync."
echo "Script repo: $SCRIPT_REPO"
echo "Watch repo: $WATCH_REPO"
echo "Export worktree: $EXPORT_REPO"
echo "LaunchAgent: $PLIST_PATH"
