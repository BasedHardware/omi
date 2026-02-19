#!/bin/bash
#
# macOS Development Script
# Usage: ./dev-macos.sh [options]
#
# Options:
#   --clean       Force clean build (removes build cache)
#   --debug       Build in debug mode (default: release)
#   --no-run      Build only, don't run the app
#   --no-backend  Don't start the local Python backend
#   --help        Show this help message
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$(dirname "$APP_DIR")/backend"
BACKEND_PORT=8001
BACKEND_PID=""

# Cleanup function to stop backend on exit
cleanup() {
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Defaults
CLEAN=false
BUILD_MODE="release"
RUN_APP=true
RUN_BACKEND=true

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
        --no-backend)
            RUN_BACKEND=false
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

# Start Python backend if requested
if [ "$RUN_BACKEND" = true ]; then
    echo "Killing any existing backend on port $BACKEND_PORT..."
    lsof -ti:$BACKEND_PORT | xargs kill -9 2>/dev/null || true

    echo "Starting Python backend on port $BACKEND_PORT..."
    cd "$BACKEND_DIR"
    if [ ! -d "venv" ]; then
        echo "Creating Python virtual environment..."
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
    else
        source venv/bin/activate
    fi
    uvicorn main:app --reload --env-file .env --port $BACKEND_PORT &
    BACKEND_PID=$!
    cd "$APP_DIR"

    # Wait for backend to be ready
    echo "Waiting for backend to start..."
    for i in {1..30}; do
        if curl -s "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
            echo "Backend is ready!"
            break
        fi
        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "Backend failed to start"
            exit 1
        fi
        sleep 0.5
    done

    # Update .dev.env to point to local backend
    echo "Configuring app to use local backend (localhost:$BACKEND_PORT)..."
    cat > "$APP_DIR/.dev.env" << EOF
API_BASE_URL=http://localhost:$BACKEND_PORT/
USE_WEB_AUTH=true
USE_AUTH_CUSTOM_TOKEN=true
EOF

    # Regenerate env files
    echo "Regenerating env files..."
    rm -f "$APP_DIR/lib/env/dev_env.g.dart"
    flutter pub run build_runner build --delete-conflicting-outputs > /dev/null 2>&1
fi

# Set up Custom.xcconfig for local development signing
CUSTOM_XCCONFIG="$APP_DIR/macos/Runner/Configs/Custom.xcconfig"
if [ ! -f "$CUSTOM_XCCONFIG" ] || ! grep -q "^APP_BUNDLE_IDENTIFIER=" "$CUSTOM_XCCONFIG" 2>/dev/null; then
    echo "Setting up Custom.xcconfig for local development..."

    # Try to detect development team from existing certificates
    DEV_TEAM=$(security find-identity -v -p codesigning 2>/dev/null | grep "Apple Development" | head -1 | sed -n 's/.*(\([A-Z0-9]*\)).*/\1/p')
    if [ -z "$DEV_TEAM" ]; then
        DEV_TEAM="S6DP5HF77G"  # Default team ID
    fi

    cat > "$CUSTOM_XCCONFIG" << EOF
// This is a generated file; do not edit or check into version control.
APP_BUNDLE_IDENTIFIER=com.omi.computer-macos

// Local development signing
DEVELOPMENT_TEAM=$DEV_TEAM
CODE_SIGN_STYLE=Automatic
CODE_SIGN_IDENTITY=Apple Development
EOF
    echo "Created Custom.xcconfig with development team: $DEV_TEAM"
fi

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

# Clean up conflicting Swift app (OMI-COMPUTER.app) that shares the same bundle ID
# This causes screen capture permission issues because macOS gets confused
echo "Checking for conflicting OMI-COMPUTER.app builds..."
CONFLICTING_BUNDLE_ID="com.omi.computer-macos"
OMI_REPO_ROOT="$(dirname "$APP_DIR")"

# Find and remove any OMI-COMPUTER.app builds with the conflicting bundle ID
for swift_app in "$OMI_REPO_ROOT"/build/OMI-COMPUTER.app "$OMI_REPO_ROOT"/OMI-COMPUTER.app /Applications/OMI-COMPUTER.app ~/Desktop/OMI-COMPUTER.app; do
    if [ -d "$swift_app" ]; then
        echo "Found conflicting app: $swift_app"
        $LSREGISTER -u "$swift_app" 2>/dev/null || true
        echo "Removing $swift_app to resolve bundle ID conflict..."
        rm -rf "$swift_app"
    fi
done

# Also check LaunchServices database for any registered OMI-COMPUTER apps
$LSREGISTER -dump 2>/dev/null | grep -o '[^"[:space:]]*OMI-COMPUTER[^"[:space:]]*\.app' | sort -u | while read -r stale_app; do
    if [ -n "$stale_app" ]; then
        echo "Unregistering stale: $stale_app"
        $LSREGISTER -u "$stale_app" 2>/dev/null || true
        # Remove if it still exists (skip Trash and mounted volumes - they're protected)
        if [ -d "$stale_app" ] && [[ "$stale_app" != *".Trash"* ]] && [[ "$stale_app" != /Volumes/* ]]; then
            echo "Removing $stale_app..."
            rm -rf "$stale_app"
        fi
    fi
done

# Garbage collect LaunchServices database to remove stale entries
echo "Garbage collecting LaunchServices database..."
$LSREGISTER -gc
echo "LaunchServices garbage collection complete."

# Reset TCC (privacy) permissions for the bundle ID
# This clears old permission entries from System Preferences
BUNDLE_ID="com.omi.computer-macos"
echo "Resetting TCC permissions for $BUNDLE_ID..."
tccutil reset ScreenCapture "$BUNDLE_ID" 2>/dev/null || true
tccutil reset Microphone "$BUNDLE_ID" 2>/dev/null || true
tccutil reset AppleEvents "$BUNDLE_ID" 2>/dev/null || true
echo "TCC permissions reset complete."

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

echo ""
echo "=== Development Environment ==="
if [ -n "$BACKEND_PID" ]; then
    echo "Backend:  http://localhost:$BACKEND_PORT (PID: $BACKEND_PID)"
fi
echo "App:      /Applications/Omi.app"
echo "==============================="
echo ""

# If backend is running, wait for it (keeps script running)
if [ -n "$BACKEND_PID" ]; then
    echo "Press Ctrl+C to stop all services..."
    wait "$BACKEND_PID"
else
    echo "Done!"
fi
