#!/bin/bash
# Build, launch, then auto-rebuild on Swift file changes.
# Usage: ./watch.sh [APP_NAME]
#   APP_NAME defaults to "Nooto"
#
# Uses run.sh for the initial build+launch (backend, auth, app bundle).
# Then watches Swift source files and does fast incremental rebuilds.

set -euo pipefail

APP_NAME="${1:-Nooto}"
DESKTOP_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCES_DIR="$DESKTOP_DIR/Desktop/Sources"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ts() { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }

# --- Initial build & launch via run.sh ---
ts "Initial build via run.sh..."
OMI_SKIP_TUNNEL=1 OMI_APP_NAME="$APP_NAME" "$DESKTOP_DIR/run.sh"

# --- Watch for changes ---
echo ""
ts "${GREEN}Watching for changes...${NC} (save a .swift file to rebuild)"
echo ""

fswatch -r -l 1 --include '\.swift$' --exclude '.*' "$SOURCES_DIR" | while read -r FILE; do
    RELATIVE="${FILE#$SOURCES_DIR/}"
    ts "${YELLOW}Changed:${NC} $RELATIVE"

    # Kill running app
    pkill -f "$APP_NAME.app/Contents/MacOS" 2>/dev/null || true
    sleep 0.3

    # Incremental build
    ts "Building..."
    BUILD_START=$(date +%s)
    if xcrun swift build -c debug --package-path "$DESKTOP_DIR/Desktop" 2>&1 | tail -3; then
        BUILD_END=$(date +%s)
        ts "${GREEN}Built${NC} in $((BUILD_END - BUILD_START))s"
    else
        ts "${RED}Build failed${NC}"
        continue
    fi

    # Update binary in app bundle
    BINARY="$DESKTOP_DIR/Desktop/.build/debug/Omi Computer"
    APP_BUNDLE="/Applications/$APP_NAME.app"

    if [ -f "$BINARY" ] && [ -d "$APP_BUNDLE" ]; then
        cp "$BINARY" "$APP_BUNDLE/Contents/MacOS/Omi Computer"

        # Re-sign
        IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | sed 's/.*"\(.*\)".*/\1/')
        if [ -n "$IDENTITY" ]; then
            codesign --force --sign "$IDENTITY" --entitlements "$DESKTOP_DIR/Desktop/Omi-local.entitlements" --options runtime "$APP_BUNDLE" 2>/dev/null
        fi

        open "$APP_BUNDLE"
        ts "${GREEN}Relaunched $APP_NAME${NC}"
    else
        ts "${RED}Binary or app bundle not found${NC}"
    fi
done
