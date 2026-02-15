#!/bin/bash
set -e

# Sync script for FocusMonitor files between omi-computer-swift and omi Flutter app
#
# Source of truth:
#   - Flutter app (omi/app/macos/Runner/FocusMonitor/) has latest crash fixes and features
#   - Swift app (omi-computer-swift/Desktop/Sources/) has notification foreground fix
#
# This script syncs files bidirectionally based on which repo has the latest fixes.

SWIFT_APP="/Users/matthewdi/omi-computer-swift/Desktop/Sources"
FLUTTER_APP="/Users/matthewdi/omi/app/macos/Runner/FocusMonitor"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== FocusMonitor File Sync ===${NC}"
echo ""
echo "Swift app:   $SWIFT_APP"
echo "Flutter app: $FLUTTER_APP"
echo ""

# Files to sync FROM Flutter TO Swift (Flutter has latest)
FLUTTER_TO_SWIFT=(
    "GlowBorderView.swift"        # Red distraction mode + macOS 13 fallback
    "GlowOverlayController.swift" # Crash fix (orderOut vs close) + color mode
    "GlowOverlayWindow.swift"     # animationBehavior crash fix
    "ScreenCaptureService.swift"  # Async ScreenCaptureKit + fallback
    "GeminiService.swift"         # onDistraction callback for red glow
    "FocusModels.swift"           # Models (new file for Swift)
)

# Files to sync FROM Swift TO Flutter (Swift has latest)
SWIFT_TO_FLUTTER=(
    "NotificationService.swift"   # Foreground notification delegate fix
)

# Files that are identical (no sync needed)
IDENTICAL=(
    "Logger.swift"
)

show_status() {
    echo -e "${YELLOW}=== File Status ===${NC}"
    echo ""

    echo -e "${GREEN}Flutter → Swift (Flutter has latest):${NC}"
    for file in "${FLUTTER_TO_SWIFT[@]}"; do
        if [ -f "$FLUTTER_APP/$file" ]; then
            if [ -f "$SWIFT_APP/$file" ]; then
                if diff -q "$FLUTTER_APP/$file" "$SWIFT_APP/$file" > /dev/null 2>&1; then
                    echo "  ✓ $file (identical)"
                else
                    echo "  ⚠ $file (differs)"
                fi
            else
                echo "  + $file (new file)"
            fi
        else
            echo "  ✗ $file (not in Flutter)"
        fi
    done
    echo ""

    echo -e "${GREEN}Swift → Flutter (Swift has latest):${NC}"
    for file in "${SWIFT_TO_FLUTTER[@]}"; do
        if [ -f "$SWIFT_APP/$file" ]; then
            if [ -f "$FLUTTER_APP/$file" ]; then
                if diff -q "$SWIFT_APP/$file" "$FLUTTER_APP/$file" > /dev/null 2>&1; then
                    echo "  ✓ $file (identical)"
                else
                    echo "  ⚠ $file (differs)"
                fi
            else
                echo "  + $file (new file)"
            fi
        else
            echo "  ✗ $file (not in Swift)"
        fi
    done
    echo ""

    echo -e "${GREEN}Identical (no sync needed):${NC}"
    for file in "${IDENTICAL[@]}"; do
        echo "  ✓ $file"
    done
    echo ""
}

show_diff() {
    local file=$1
    echo -e "${YELLOW}=== Diff for $file ===${NC}"

    if [ -f "$FLUTTER_APP/$file" ] && [ -f "$SWIFT_APP/$file" ]; then
        diff "$FLUTTER_APP/$file" "$SWIFT_APP/$file" || true
    elif [ -f "$FLUTTER_APP/$file" ]; then
        echo "File only exists in Flutter app"
    elif [ -f "$SWIFT_APP/$file" ]; then
        echo "File only exists in Swift app"
    else
        echo "File not found in either location"
    fi
    echo ""
}

sync_flutter_to_swift() {
    echo -e "${YELLOW}=== Syncing Flutter → Swift ===${NC}"

    for file in "${FLUTTER_TO_SWIFT[@]}"; do
        if [ -f "$FLUTTER_APP/$file" ]; then
            echo "Copying $file..."
            cp "$FLUTTER_APP/$file" "$SWIFT_APP/$file"
            echo -e "  ${GREEN}✓${NC} $file"
        else
            echo -e "  ${RED}✗${NC} $file (not found in Flutter)"
        fi
    done
    echo ""
}

sync_swift_to_flutter() {
    echo -e "${YELLOW}=== Syncing Swift → Flutter ===${NC}"

    for file in "${SWIFT_TO_FLUTTER[@]}"; do
        if [ -f "$SWIFT_APP/$file" ]; then
            echo "Copying $file..."
            cp "$SWIFT_APP/$file" "$FLUTTER_APP/$file"
            echo -e "  ${GREEN}✓${NC} $file"
        else
            echo -e "  ${RED}✗${NC} $file (not found in Swift)"
        fi
    done
    echo ""
}

sync_all() {
    sync_flutter_to_swift
    sync_swift_to_flutter
    echo -e "${GREEN}=== Sync Complete ===${NC}"
}

show_help() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  status    Show sync status of all files"
    echo "  diff      Show diffs for all files"
    echo "  diff FILE Show diff for specific file"
    echo "  flutter   Sync Flutter → Swift only"
    echo "  swift     Sync Swift → Flutter only"
    echo "  all       Sync all files (both directions)"
    echo "  help      Show this help"
    echo ""
    echo "Files synced Flutter → Swift:"
    for file in "${FLUTTER_TO_SWIFT[@]}"; do
        echo "  - $file"
    done
    echo ""
    echo "Files synced Swift → Flutter:"
    for file in "${SWIFT_TO_FLUTTER[@]}"; do
        echo "  - $file"
    done
}

case "${1:-status}" in
    status)
        show_status
        ;;
    diff)
        if [ -n "$2" ]; then
            show_diff "$2"
        else
            for file in "${FLUTTER_TO_SWIFT[@]}"; do
                show_diff "$file"
            done
            for file in "${SWIFT_TO_FLUTTER[@]}"; do
                show_diff "$file"
            done
        fi
        ;;
    flutter)
        sync_flutter_to_swift
        ;;
    swift)
        sync_swift_to_flutter
        ;;
    all)
        sync_all
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
