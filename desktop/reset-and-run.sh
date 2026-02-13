#!/bin/bash
set -e

###############################################################################
# RESET AND RUN SCRIPT FOR OMI DESKTOP DEVELOPMENT
###############################################################################
#
# This script builds and runs the Omi Desktop app with a clean slate for testing.
# It handles permission resets, app cleanup, and backend services.
#
# CRITICAL: ORDER OF OPERATIONS MATTERS!
# =============================================================================
# The sequence below was determined through extensive debugging. DO NOT change
# the order without understanding why it matters.
#
# CORRECT ORDER:
#   1. Kill app processes
#   2. Reset TCC permissions (while app STILL EXISTS in /Applications)
#   3. Delete app bundles
#   4. Reset Launch Services
#   5. Build new app
#   6. Install to /Applications
#   7. Reset UserDefaults
#   8. Launch app
#
# WHY THIS ORDER MATTERS:
# -----------------------
# - tccutil reset requires the app to exist to properly resolve the bundle ID.
#   If you delete the app first, tccutil silently fails to reset permissions.
#   This was discovered after hours of debugging where permissions appeared
#   "stuck" even after running tccutil.
#
# - The app must be killed BEFORE resetting TCC, otherwise the running app
#   may re-acquire permissions immediately.
#
# MACOS TCC (TRANSPARENCY, CONSENT, CONTROL) NOTES:
# =============================================================================
# - User TCC database: ~/Library/Application Support/com.apple.TCC/TCC.db
#   Contains: Microphone, AudioCapture, AppleEvents, Accessibility
#   Can be modified with: tccutil reset, sqlite3 DELETE
#
# - System TCC database: /Library/Application Support/com.apple.TCC/TCC.db
#   Contains: ScreenCapture (Screen Recording)
#   PROTECTED BY SIP - cannot be modified directly, even with sudo
#   Can only be reset via: tccutil reset ScreenCapture <bundle-id>
#   Or manually removed in: System Settings > Privacy & Security > Screen Recording
#
# - CGPreflightScreenCaptureAccess() can return STALE data after app rebuilds.
#   It may say "true" when the permission is actually invalid for the new binary.
#
# - ScreenCaptureKit (macOS 14+) has its OWN consent separate from TCC.
#   SCShareableContent.excludingDesktopWindows() triggers this consent dialog.
#   Don't call it repeatedly - it will show the dialog each time if not granted.
#
# LAUNCH SERVICES POLLUTION:
# =============================================================================
# Launch Services caches app metadata (bundle ID, name, icon) from ALL apps it
# sees, including:
#   - DMG staging directories in /private/tmp
#   - Mounted DMG volumes (/Volumes/Omi Computer, /Volumes/dmg.*)
#   - Apps in Trash
#   - Xcode DerivedData builds
#
# If multiple apps with the same bundle ID exist (even in Trash!), macOS gets
# confused and may:
#   - Show wrong app name in System Settings (e.g., "Omi Computer.app" with .app)
#   - Show generic icon instead of actual app icon
#   - Grant permissions to the wrong app
#
# SOLUTION: Clean up ALL these locations before building:
#   - /private/tmp/omi-dmg-staging-*
#   - ~/.Trash/Omi*, ~/.Trash/OMI*
#   - Mounted volumes: /Volumes/Omi*, /Volumes/dmg.*
#   - Xcode DerivedData Omi builds
#
# The lsregister -kill command is supposed to rebuild the database but is
# disabled on modern macOS. A reboot may be needed for complete cleanup.
#
# DEBUGGING TIPS:
# =============================================================================
# Check TCC entries:
#   sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db" \
#     "SELECT service, client, auth_value FROM access WHERE client LIKE '%omi%';"
#
# Check Launch Services registrations:
#   lsregister=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
#   $lsregister -dump | grep -A20 "com.omi.computer-macos"
#
# Check screen recording permission:
#   swift -e 'import CoreGraphics; print(CGPreflightScreenCaptureAccess())'
#
# Manually reset all TCC for a bundle:
#   tccutil reset All com.omi.desktop-dev
#
###############################################################################

# Clear system OPENAI_API_KEY so .env takes precedence
unset OPENAI_API_KEY

# Use Xcode's default toolchain to match the SDK version
unset TOOLCHAINS

# App configuration
BINARY_NAME="Omi Computer"  # Package.swift target — binary paths, pkill, CFBundleExecutable
APP_NAME="Omi Dev"
BUNDLE_ID="com.omi.desktop-dev"
BUILD_DIR="build"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
APP_PATH="/Applications/$APP_NAME.app"
SIGN_IDENTITY="Developer ID Application: Matthew Diakonov (S6DP5HF77G)"

# Backend configuration (Rust)
BACKEND_DIR="$(dirname "$0")/Backend-Rust"
BACKEND_PID=""
TUNNEL_PID=""
TUNNEL_URL="https://omi-dev.m13v.com"

# Cleanup function to stop backend and tunnel on exit
cleanup() {
    if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "Stopping tunnel (PID: $TUNNEL_PID)..."
        kill "$TUNNEL_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Kill existing instances
echo "Killing existing instances..."
pkill -f "$APP_NAME.app" 2>/dev/null || true
pkill -f "cloudflared.*omi-computer-dev" 2>/dev/null || true
lsof -ti:8080 | xargs kill -9 2>/dev/null || true

# Clear log file for fresh run (must be before backend starts)
rm -f /tmp/omi.log 2>/dev/null || true

# =============================================================================
# STEP 2: RESET TCC PERMISSIONS
# =============================================================================
# CRITICAL: This MUST happen BEFORE deleting the app from /Applications!
# tccutil needs the app to exist to resolve the bundle ID and find the correct
# TCC entries to reset. If the app doesn't exist, tccutil silently succeeds
# but doesn't actually reset anything.
#
# We reset BOTH bundle IDs:
# - Development: com.omi.desktop-dev (this script's builds)
# - Production: com.omi.computer-macos (release DMG builds)
#
# Using "reset All" instead of individual services (ScreenCapture, Microphone, etc.)
# because it's more reliable and catches any permissions we might have missed.
BUNDLE_ID_PROD="com.omi.computer-macos"
echo "Resetting TCC permissions (before deleting apps)..."
tccutil reset All "$BUNDLE_ID" 2>/dev/null || true
tccutil reset All "$BUNDLE_ID_PROD" 2>/dev/null || true

# Belt-and-suspenders: Also clean user TCC database directly via sqlite3
# This catches any entries that tccutil might have missed
# Note: System TCC database (Screen Recording) is SIP-protected and cannot be
# modified this way - only tccutil can reset it
sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db" "DELETE FROM access WHERE client LIKE '%com.omi.computer-macos%';" 2>/dev/null || true
sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db" "DELETE FROM access WHERE client LIKE '%com.omi.desktop%';" 2>/dev/null || true

# =============================================================================
# STEP 3: DELETE ALL CONFLICTING APP BUNDLES
# =============================================================================
# Multiple apps with the same bundle ID confuse macOS. When granting permissions,
# the system may pick the wrong app, resulting in:
# - Permissions granted to old/deleted app instead of new build
# - Wrong app name/icon shown in System Settings
# - "Quit and reopen" prompt not appearing after enabling permissions
#
# We clean up apps from ALL possible locations where they might exist.
echo "Cleaning up conflicting app bundles..."
CONFLICTING_APPS=(
    "/Applications/Omi.app"
    "/Applications/Omi Computer.app"
    "/Applications/Omi Dev.app"
    "$APP_BUNDLE"  # Local build folder
    "$HOME/Desktop/Omi.app"
    "$HOME/Downloads/Omi.app"
    # Flutter app builds (with and without -prod suffix)
    "$(dirname "$0")/../omi/app/build/macos/Build/Products/Debug/Omi.app"
    "$(dirname "$0")/../omi/app/build/macos/Build/Products/Release/Omi.app"
    "$(dirname "$0")/../omi/app/build/macos/Build/Products/Debug-prod/Omi.app"
    "$(dirname "$0")/../omi/app/build/macos/Build/Products/Release-prod/Omi.app"
    "$(dirname "$0")/../omi-computer/build/macos/Build/Products/Debug/Omi.app"
    "$(dirname "$0")/../omi-computer/build/macos/Build/Products/Release/Omi.app"
)
# Xcode DerivedData can contain old builds with production bundle ID
# These get registered in Launch Services and cause permission confusion
echo "Cleaning Xcode DerivedData..."
find "$HOME/Library/Developer/Xcode/DerivedData" -name "Omi.app" -type d 2>/dev/null | while read app; do
    echo "  Removing: $app"
    rm -rf "$app"
done
find "$HOME/Library/Developer/Xcode/DerivedData" -name "Omi Computer.app" -type d 2>/dev/null | while read app; do
    echo "  Removing: $app"
    rm -rf "$app"
done
find "$HOME/Library/Developer/Xcode/DerivedData" -name "Omi Dev.app" -type d 2>/dev/null | while read app; do
    echo "  Removing: $app"
    rm -rf "$app"
done

# DMG staging directories from release.sh builds contain production bundle ID apps
# Launch Services sees these and caches them, causing permission confusion
echo "Cleaning DMG staging directories..."
rm -rf /private/tmp/omi-dmg-staging-* /private/tmp/omi-dmg-test-* 2>/dev/null || true

# IMPORTANT: Apps in Trash are STILL registered in Launch Services!
# This was a major source of bugs - deleted apps in Trash were being picked up
# by macOS when granting permissions, resulting in wrong app names/icons
echo "Cleaning Omi apps from Trash..."
rm -rf "$HOME/.Trash/OMI"* "$HOME/.Trash/Omi"* 2>/dev/null || true

# Mounted DMG volumes also register their apps in Launch Services
# If you opened a release DMG to test, the mounted app pollutes the database
echo "Ejecting mounted Omi DMG volumes..."
for vol in /Volumes/Omi* /Volumes/OMI* /Volumes/dmg.*; do
    if [ -d "$vol" ]; then
        echo "  Ejecting: $vol"
        diskutil eject "$vol" 2>/dev/null || hdiutil detach "$vol" 2>/dev/null || true
    fi
done

for app in "${CONFLICTING_APPS[@]}"; do
    if [ -d "$app" ]; then
        echo "  Removing: $app"
        rm -rf "$app"
    fi
done

# =============================================================================
# STEP 4: RESET LAUNCH SERVICES DATABASE
# =============================================================================
# Launch Services caches app metadata (bundle ID → app path, name, icon).
# After cleaning up old apps, we need to tell Launch Services to rebuild.
#
# NOTE: The -kill flag is deprecated/disabled on modern macOS. This command
# may not fully clear the cache. If you still see wrong app names/icons in
# System Settings after running this script, a REBOOT may be required to
# fully rebuild the Launch Services database.
#
# The lsregister tool reads from an in-memory daemon, not disk. Deleting the
# database file (~/.../com.apple.LaunchServices.lsdb) only takes effect after
# the daemon restarts (i.e., after reboot).
echo "Resetting Launch Services database..."
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -kill -r -domain local -domain user 2>/dev/null || true

# Start Cloudflare tunnel
echo "Starting Cloudflare tunnel..."
cloudflared tunnel run omi-computer-dev &
TUNNEL_PID=$!
sleep 2

# Start Rust backend
echo "Starting Rust backend..."
cd "$BACKEND_DIR"

# Copy .env if not present
if [ ! -f ".env" ] && [ -f "../Backend/.env" ]; then
    cp "../Backend/.env" ".env"
fi

# Symlink google-credentials.json if not present
if [ ! -f "google-credentials.json" ] && [ -f "../Backend/google-credentials.json" ]; then
    ln -sf "../Backend/google-credentials.json" "google-credentials.json"
fi

# Build if binary doesn't exist or source is newer
if [ ! -f "target/release/omi-desktop-backend" ] || [ -n "$(find src -newer target/release/omi-desktop-backend 2>/dev/null)" ]; then
    echo "Building Rust backend..."
    cargo build --release
fi

./target/release/omi-desktop-backend &
BACKEND_PID=$!
cd - > /dev/null

# Wait for backend to be ready
echo "Waiting for backend to start..."
for i in {1..30}; do
    if curl -s http://localhost:8080 > /dev/null 2>&1; then
        echo "Backend is ready!"
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Backend failed to start"
        exit 1
    fi
    sleep 0.5
done

# Build debug
echo "Building app..."
xcrun swift build -c debug --package-path Desktop

# Remove old app bundles to avoid permission issues with signed apps
rm -rf "$APP_BUNDLE" "$BUILD_DIR/Omi Computer.app"

# Create app bundle
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Copy binary
cp "Desktop/.build/debug/$BINARY_NAME" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME"

# Add rpath for Frameworks folder (needed for Sparkle)
install_name_tool -add_rpath "@executable_path/../Frameworks" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME" 2>/dev/null || true

# Copy Sparkle framework (keep original signatures intact)
mkdir -p "$APP_BUNDLE/Contents/Frameworks"
SPARKLE_FRAMEWORK="Desktop/.build/arm64-apple-macosx/debug/Sparkle.framework"
if [ -d "$SPARKLE_FRAMEWORK" ]; then
    rm -rf "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
    cp -R "$SPARKLE_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
    echo "  Copied Sparkle.framework"
fi

# Copy resource bundle (contains app assets like permissions.gif, herologo.png, etc.)
RESOURCE_BUNDLE="Desktop/.build/arm64-apple-macosx/debug/Omi Computer_Omi Computer.bundle"
if [ -d "$RESOURCE_BUNDLE" ]; then
    cp -Rf "$RESOURCE_BUNDLE" "$APP_BUNDLE/Contents/Resources/"
    echo "  Copied resource bundle"
fi

# Copy and fix Info.plist
cp Desktop/Info.plist "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $BINARY_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleURLTypes:0:CFBundleURLSchemes:0 omi-computer-dev" "$APP_BUNDLE/Contents/Info.plist"

# Copy GoogleService-Info.plist for Firebase
cp Desktop/Sources/GoogleService-Info.plist "$APP_BUNDLE/Contents/Resources/"

# Copy .env.app (app runtime secrets only) and add API URL
if [ -f ".env.app" ]; then
    cp .env.app "$APP_BUNDLE/Contents/Resources/.env"
else
    touch "$APP_BUNDLE/Contents/Resources/.env"
fi
# Set API URL to tunnel for development (overrides production default)
echo "OMI_API_URL=$TUNNEL_URL" >> "$APP_BUNDLE/Contents/Resources/.env"
echo "Using backend: $TUNNEL_URL"

# Copy app icon
cp omi_icon.icns "$APP_BUNDLE/Contents/Resources/OmiIcon.icns" 2>/dev/null || true

# Create PkgInfo
echo -n "APPL????" > "$APP_BUNDLE/Contents/PkgInfo"

# Strip extended attributes before signing (prevents "resource fork, Finder information" errors)
xattr -cr "$APP_BUNDLE"

# Sign Sparkle framework components individually (like release.sh does)
echo "Signing Sparkle framework components..."
SPARKLE_FW="$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
if [ -d "$SPARKLE_FW" ]; then
    # Sign innermost components first
    codesign --force --options runtime --sign "$SIGN_IDENTITY" \
        "$SPARKLE_FW/Versions/B/XPCServices/Downloader.xpc" 2>/dev/null || true
    codesign --force --options runtime --sign "$SIGN_IDENTITY" \
        "$SPARKLE_FW/Versions/B/XPCServices/Installer.xpc" 2>/dev/null || true
    codesign --force --options runtime --sign "$SIGN_IDENTITY" \
        "$SPARKLE_FW/Versions/B/Autoupdate" 2>/dev/null || true
    codesign --force --options runtime --sign "$SIGN_IDENTITY" \
        "$SPARKLE_FW/Versions/B/Updater.app" 2>/dev/null || true
    # Sign framework itself
    codesign --force --options runtime --sign "$SIGN_IDENTITY" "$SPARKLE_FW"
fi

# Sign main app
echo "Signing app..."
codesign --force --options runtime --entitlements Desktop/Omi.entitlements --sign "$SIGN_IDENTITY" "$APP_BUNDLE"

# Install to /Applications
echo "Installing to /Applications..."
rm -rf "$APP_PATH"
ditto "$APP_BUNDLE" "$APP_PATH"

# Reset app data (UserDefaults, onboarding state, etc.) for BOTH bundle IDs
# (TCC permissions were already reset before building)
echo "Resetting app data..."
defaults delete "$BUNDLE_ID" 2>/dev/null || true
defaults delete "$BUNDLE_ID_PROD" 2>/dev/null || true

# Clear delivered notifications
echo "Clearing notifications..."
osascript -e "tell application \"System Events\" to tell process \"NotificationCenter\" to click button 1 of every window" 2>/dev/null || true

# Note: Notification PERMISSIONS cannot be reset programmatically (Apple limitation)
# To fully reset notification permissions, manually go to:
# System Settings > Notifications > Omi Computer > Remove
echo "Note: Notification permissions can only be reset manually in System Settings"

echo ""
echo "=== Services Running ==="
echo "Backend:  http://localhost:8080 (PID: $BACKEND_PID)"
echo "Tunnel:   $TUNNEL_URL (PID: $TUNNEL_PID)"
echo "App:      $APP_PATH"
echo "========================"
echo ""

# Remove quarantine and start app from /Applications
echo "Starting app..."
xattr -cr "$APP_PATH"
open "$APP_PATH" || "$APP_PATH/Contents/MacOS/$BINARY_NAME" &

# Wait for backend process (keeps script running and shows logs)
echo "Press Ctrl+C to stop all services..."
wait "$BACKEND_PID"
