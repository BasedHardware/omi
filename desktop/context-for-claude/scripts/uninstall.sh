#!/bin/bash
#
# Removes Context for Claude from this machine.
#
# Usage:
#   scripts/uninstall.sh                remove /Applications/Context for Claude.app and the login item
#   scripts/uninstall.sh --dev          remove the developer build instead (Context for Claude Dev.app)
#   scripts/uninstall.sh --purge-data   also delete ~/Library/Application Support/ContextForClaude
#
# Captured transcripts and screen frames survive by default — deleting them is explicit, because
# they are not recoverable.
#
# SAFETY: identical guard to build.sh. This script never touches /Applications/Omi.app,
# /Applications/Omi Beta.app, or any com.omi.computer-macos* bundle, and never kills their
# processes.

set -euo pipefail

export PATH="/bin:/usr/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The captured data lives under one directory for both kinds of install, so --dev does not move it.
DATA_DIR="$HOME/Library/Application Support/ContextForClaude"
PURGE_DATA=0
IDENTITY_KIND="release"

log()  { printf '\033[1m[context]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[context]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[context]\033[0m %s\n' "$*" >&2; exit 1; }

assert_not_production() {
    local what="$1" value="$2"
    local matched=0
    shopt -s nocasematch
    if [[ "$value" == *"/Applications/Omi.app"* ]] \
        || [[ "$value" == *"/Applications/Omi Beta.app"* ]] \
        || [[ "$value" == "Omi" ]] || [[ "$value" == "Omi.app" ]] \
        || [[ "$value" == "Omi Beta" ]] || [[ "$value" == "Omi Beta.app" ]] \
        || [[ "$value" == *"Omi Computer"* ]] \
        || [[ "$value" == *"com.omi.computer-macos"* ]]; then
        matched=1
    fi
    shopt -u nocasematch
    if [[ "$matched" -eq 1 ]]; then
        die "refusing to continue: $what resolves to a production Omi target ('$value'). This script only ever touches Context for Claude."
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --purge-data) PURGE_DATA=1 ;;
        --dev)        IDENTITY_KIND="development" ;;
        -h|--help)
            sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) die "unknown flag: $1 (see --help)" ;;
    esac
    shift
done

# Which install to remove. build-identity.sh is the single owner of both identity sets, so this
# script cannot drift from what build.sh actually produced.
IDENTITY_ASSIGNMENTS="$("$SCRIPT_DIR/build-identity.sh" --kind "$IDENTITY_KIND")" \
    || die "could not resolve the $IDENTITY_KIND identity"
eval "$IDENTITY_ASSIGNMENTS"

APP_NAME="$CFC_APP_NAME"
BUNDLE_ID="$CFC_BUNDLE_ID"
MCP_SERVER_NAME="$CFC_MCP_SERVER_NAME"
INSTALL_PATH="/Applications/$APP_NAME.app"

assert_not_production "APP_NAME" "$APP_NAME"
assert_not_production "APP_NAME bundle" "$APP_NAME.app"
assert_not_production "BUNDLE_ID" "$BUNDLE_ID"
assert_not_production "install path" "$INSTALL_PATH"
assert_not_production "data directory" "$DATA_DIR"
[[ "$(basename "$INSTALL_PATH")" == "$APP_NAME.app" ]] \
    || die "install path basename must be $APP_NAME.app, got $(basename "$INSTALL_PATH")"

log "removing the $IDENTITY_KIND install: $APP_NAME ($BUNDLE_ID)"

# Quit a running Context for Claude, matched on its exact executable path and re-checked per pid.
RUNNING_EXEC="$INSTALL_PATH/Contents/MacOS/$APP_NAME"
assert_not_production "quit target" "$RUNNING_EXEC"
while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    cmd="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    [[ -n "$cmd" ]] || continue
    assert_not_production "process to quit (pid $pid)" "$cmd"
    [[ "$cmd" == "$RUNNING_EXEC"* ]] || continue
    log "quitting running $APP_NAME (pid $pid)"
    kill "$pid" 2>/dev/null || true
done < <(pgrep -f "^$RUNNING_EXEC" 2>/dev/null || true)

# Legacy login item, if one was ever created under that exact name. The modern SMAppService
# background item disappears with the bundle; macOS prunes it on the next login.
osascript -e "tell application \"System Events\" to delete (every login item whose name is \"$APP_NAME\")" \
    >/dev/null 2>&1 || true
log "cleared any '$APP_NAME' login item"

if [[ -d "$INSTALL_PATH" ]]; then
    assert_not_production "removal target" "$INSTALL_PATH"
    log "removing $INSTALL_PATH"
    rm -rf "$INSTALL_PATH"
else
    log "$INSTALL_PATH is not installed"
fi

# The updater's leftovers, removed whether or not --purge-data was asked for, because none of this is
# the user's: it is a staged download and two launchd jobs whose only purpose was to replace a bundle
# that no longer exists. Sparkle submits those jobs to install an update *after* quitting the app, so
# an uninstall performed mid-update would otherwise leave a helper behind whose job is to put the app
# back. Both labels are Sparkle's own convention, derived from the bundle identifier.
for label in "$BUNDLE_ID-sparkle-updater" "$BUNDLE_ID-sparkle-progress"; do
    assert_not_production "launchd job" "$label"
    launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
done
SPARKLE_CACHE="$HOME/Library/Caches/$BUNDLE_ID"
assert_not_production "cache directory" "$SPARKLE_CACHE"
if [[ -d "$SPARKLE_CACHE" ]]; then
    log "removing cached downloads at $SPARKLE_CACHE"
    rm -rf "$SPARKLE_CACHE"
fi

if [[ "$PURGE_DATA" -eq 1 ]]; then
    if [[ -d "$DATA_DIR" ]]; then
        assert_not_production "removal target" "$DATA_DIR"
        log "deleting captured data at $DATA_DIR"
        rm -rf "$DATA_DIR"
    else
        log "no captured data at $DATA_DIR"
    fi
    defaults delete "$BUNDLE_ID" >/dev/null 2>&1 || true
else
    log "kept captured data at $DATA_DIR (re-run with --purge-data to delete it)"
fi

# The Claude Code skill, unlike the config entries, is a directory this app created and owns every
# byte of — so removing it here is safe in a way that editing the user's config would not be. Left
# behind, it would describe an app that is no longer installed.
SKILL_DIR="$HOME/.claude/skills/$MCP_SERVER_NAME"
assert_not_production "skill directory" "$SKILL_DIR"
if [[ -d "$SKILL_DIR" ]]; then
    log "removing the Claude Code skill at $SKILL_DIR"
    rm -rf "$SKILL_DIR"
fi

echo
log "one manual step is left — this script does not edit your Claude config:"
echo "  claude mcp remove $MCP_SERVER_NAME"
echo "  and delete the \"$MCP_SERVER_NAME\" entry under mcpServers in:"
echo "    ~/Library/Application Support/Claude/claude_desktop_config.json"
