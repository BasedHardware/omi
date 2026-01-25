#!/bin/bash
#
# macOS Development Script
# Usage: ./dev-macos.sh [options]
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
            head -15 "$0" | tail -13
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

# Re-register app with LaunchServices to ensure URL schemes are recognized
echo "Registering app with LaunchServices..."
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
if [ "$BUILD_MODE" = "release" ]; then
    APP_PATH="build/macos/Build/Products/Release-prod/Omi.app"
else
    APP_PATH="build/macos/Build/Products/Debug-prod/Omi.app"
fi

# Unregister all known stale Omi locations that could hijack URL schemes
echo "Clearing stale LaunchServices registrations..."
# Current build path
$LSREGISTER -u "$APP_PATH" 2>/dev/null || true
# Applications folder
$LSREGISTER -u "/Applications/Omi.app" 2>/dev/null || true
# Xcode DerivedData locations
for stale_app in ~/Library/Developer/Xcode/DerivedData/Runner-*/Build/Products/*/Omi.app; do
    $LSREGISTER -u "$stale_app" 2>/dev/null || true
done
# Local DerivedData
for stale_app in "$APP_DIR"/macos/DerivedData/Build/Products/*/Omi.app; do
    $LSREGISTER -u "$stale_app" 2>/dev/null || true
done
# Old DMG mount points (unmounted volumes leave stale registrations)
$LSREGISTER -dump 2>/dev/null | grep -o '/Volumes/[^)]*Omi.app' | while read -r stale_app; do
    $LSREGISTER -u "$stale_app" 2>/dev/null || true
done
# Trash (apps in trash can still be registered for URL schemes)
$LSREGISTER -dump 2>/dev/null | grep -o '/Users/[^)]*\.Trash/[^)]*Omi[^)]*\.app' | while read -r stale_app; do
    $LSREGISTER -u "$stale_app" 2>/dev/null || true
done

# Register the new build
$LSREGISTER -f "$APP_PATH"
echo "LaunchServices registration complete."

# Run the app
if [ "$RUN_APP" = true ]; then
    # Kill any existing Omi process first
    echo "Stopping any running Omi instance..."
    pkill -f "Omi.app/Contents/MacOS/Omi" 2>/dev/null || true
    sleep 0.5

    # Copy app to /Applications (required for screen recording permissions)
    echo "Copying app to /Applications..."
    rm -rf /Applications/Omi.app
    if [ "$BUILD_MODE" = "release" ]; then
        cp -R build/macos/Build/Products/Release-prod/Omi.app /Applications/
    else
        cp -R build/macos/Build/Products/Debug-prod/Omi.app /Applications/
    fi

    # Re-register the /Applications version with LaunchServices
    $LSREGISTER -f /Applications/Omi.app

    echo "Launching app from /Applications..."
    open /Applications/Omi.app
fi

echo "Done!"
