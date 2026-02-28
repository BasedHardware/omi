#!/bin/bash
#
# macOS Development Script (Quick Mode)
# Preserves TCC permissions and runs from build directory.
# Use dev-macos.sh for full reset of permissions.
#
# Usage: ./dev-macos-quick.sh [options]
#
# Options:
#   --clean       Force clean build (removes build cache)
#   --debug       Build in debug mode (default: release)
#   --no-run      Build only, don't run the app
#   --help        Show this help message
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

# Defaults
CLEAN=false
BUILD_MODE="release"
RUN_APP=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN=true
            shift
            ;;
        --debug)
            BUILD_MODE="debug"
            shift
            ;;
        --no-run)
            RUN_APP=false
            shift
            ;;
        --help)
            head -17 "$0" | tail -15
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

cd "$APP_DIR"

# Kill any existing Omi process first (before build to avoid file locks)
echo "Stopping any running Omi instance..."
pkill -f "Omi.app/Contents/MacOS/Omi" 2>/dev/null || true
sleep 0.5

# Clean build if requested
if [ "$CLEAN" = true ]; then
    echo "Cleaning Flutter build..."
    flutter clean
    echo "Cleaning Xcode DerivedData..."
    rm -rf ~/Library/Developer/Xcode/DerivedData/Runner-*
    echo "Cleaning Xcode ModuleCache..."
    rm -rf ~/Library/Developer/Xcode/DerivedData/ModuleCache.noindex/*
    echo "Clean complete."
fi

# Build the app
echo "Building macOS app ($BUILD_MODE with flavor prod)..."
if [ "$BUILD_MODE" = "release" ]; then
    flutter build macos --flavor prod --release
else
    flutter build macos --flavor prod --debug
fi

echo "Build complete."

# Run the app
if [ "$RUN_APP" = true ]; then
    if [ "$BUILD_MODE" = "release" ]; then
        APP_PATH="build/macos/Build/Products/Release-prod/Omi.app"
    else
        APP_PATH="build/macos/Build/Products/Debug-prod/Omi.app"
    fi

    # Run from build directory (preserves TCC permissions)
    echo "Launching app from build directory..."
    xattr -cr "$APP_PATH"
    open "$APP_PATH" || "$APP_PATH/Contents/MacOS/Omi" &
fi

echo "Done!"
