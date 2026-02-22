#!/bin/bash
set -e

# Use Xcode's default toolchain (avoid Swift 6.1 conflicts)
unset TOOLCHAINS

# Track release timing
START_TIME=$(date +%s)

# =============================================================================
# Release log — all stdout/stderr is tee'd to this file for post-mortem review
# =============================================================================
RELEASE_LOG="/private/tmp/omi-release.log"
exec > >(tee -a "$RELEASE_LOG") 2>&1
echo ""
echo "=== Release started at $(date -u '+%Y-%m-%d %H:%M:%S UTC') ==="
echo "Log file: $RELEASE_LOG"

# Load .env if present (for RELEASE_SECRET, SPARKLE_PRIVATE_KEY, etc.)
# Using set -a/source instead of xargs to handle multiline values (APPLE_PRIVATE_KEY)
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# =============================================================================
# OMI Release Script
# Full pipeline: deploy backend → build app → sign → notarize → DMG → GitHub
# Usage: ./release.sh [version]
# Example: ./release.sh 0.0.3
# If no version specified, auto-increments patch version from latest release
# =============================================================================

# Configuration
BINARY_NAME="Omi Computer"  # Package.swift target — binary paths, lipo, CFBundleExecutable
APP_NAME="Omi Beta"
BUNDLE_ID="com.omi.computer-macos"
BUILD_DIR="build"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
DMG_PATH="$BUILD_DIR/$APP_NAME.dmg"

# Signing & notarization
SIGN_IDENTITY="Developer ID Application: Matthew Diakonov (S6DP5HF77G)"
TEAM_ID="S6DP5HF77G"
APPLE_ID="matthew.heartful@gmail.com"
NOTARIZE_PASSWORD="${NOTARIZE_PASSWORD:-}"  # Set via .env file

# Sparkle Auto-Update
SPARKLE_PRIVATE_KEY="${SPARKLE_PRIVATE_KEY:-}"  # Set via environment or Keychain
SPARKLE_ZIP_PATH="$BUILD_DIR/Omi.zip"

# GitHub Release
GITHUB_REPO="BasedHardware/omi"

# Backend (for Firestore release registration)
DESKTOP_BACKEND_URL="${DESKTOP_BACKEND_URL:-https://desktop-backend-hhibjajaja-uc.a.run.app}"
RELEASE_SECRET="${RELEASE_SECRET:-}"

# Release channel: staging (default), beta, or stable
# New releases start on staging; use promote_release.sh to advance
RELEASE_CHANNEL="${RELEASE_CHANNEL:-staging}"

# Read changelog from CHANGELOG.json
CHANGELOG_FILE="CHANGELOG.json"
if [ -f "$CHANGELOG_FILE" ]; then
    # Get the latest release entry (first in array)
    CHANGELOG_ITEMS=$(cat "$CHANGELOG_FILE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data.get('releases') and len(data['releases']) > 0:
    changes = data['releases'][0].get('changes', [])
    for c in changes:
        print(c)
")
    # Create markdown bullet list for GitHub notes
    CHANGELOG_MD=$(echo "$CHANGELOG_ITEMS" | sed 's/^/- /')
    # Create JSON array for Firestore
    CHANGELOG_JSON=$(cat "$CHANGELOG_FILE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if data.get('releases') and len(data['releases']) > 0:
    print(json.dumps(data['releases'][0].get('changes', [])))
else:
    print('[]')
")
else
    echo "Warning: $CHANGELOG_FILE not found. Using empty changelog."
    CHANGELOG_MD="- No changelog available"
    CHANGELOG_JSON='[]'
fi

# Google Cloud (Backend deployment)
GCP_PROJECT="based-hardware"
GCP_REGION="us-central1"
BACKEND_IMAGE="gcr.io/$GCP_PROJECT/desktop-backend"
CLOUD_RUN_SERVICE="desktop-backend"

# -----------------------------------------------------------------------------
# Version handling: auto-increment if not specified
# -----------------------------------------------------------------------------
if [ -z "$1" ]; then
    echo "No version specified, checking latest release..."

    # Get latest version from git tags
    LATEST=$(git tag -l 'v*' 2>/dev/null | sort -V | tail -1 | sed 's/^v//' || echo "")

    # Default to 0.0.0 if no previous version found
    if [ -z "$LATEST" ]; then
        LATEST="0.0.0"
        echo "  No previous version found, starting at 0.0.1"
    else
        echo "  Latest version: $LATEST"
    fi

    # Parse and increment patch version
    MAJOR=$(echo "$LATEST" | cut -d. -f1)
    MINOR=$(echo "$LATEST" | cut -d. -f2)
    PATCH=$(echo "$LATEST" | cut -d. -f3 | cut -d+ -f1)  # Handle v1.0.0+100 format
    PATCH=$((PATCH + 1))
    VERSION="$MAJOR.$MINOR.$PATCH"
    echo "  Auto-incrementing to: $VERSION"
else
    VERSION="$1"
fi

# Calculate build number early (needed for CFBundleVersion in app bundle)
# Converts "0.0.7" → 7, "1.2.3" → 1002003
BUILD_NUMBER=$(echo "$VERSION" | tr '.' '\n' | awk '{s=s*1000+$1}END{print s}')

echo "=============================================="
echo "  OMI Release Pipeline v$VERSION (build $BUILD_NUMBER)"
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Step 1: Deploy Backend to Cloud Run
# -----------------------------------------------------------------------------
echo "[1/12] Deploying Rust backend to Cloud Run..."

# Check if Docker is running
if ! docker info &>/dev/null; then
    echo "  Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Build for linux/amd64 (Cloud Run runs on x86_64)
echo "  Building Docker image for linux/amd64..."
docker build --platform linux/amd64 -t "$BACKEND_IMAGE:$VERSION" -t "$BACKEND_IMAGE:latest" Backend-Rust/

# Push to GCR
echo "  Pushing to Google Container Registry..."
docker push "$BACKEND_IMAGE:$VERSION"
docker push "$BACKEND_IMAGE:latest"

# Deploy to Cloud Run with all backend env vars from .env
echo "  Deploying to Cloud Run..."
gcloud run deploy "$CLOUD_RUN_SERVICE" \
    --image "$BACKEND_IMAGE:$VERSION" \
    --project "$GCP_PROJECT" \
    --region "$GCP_REGION" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID,FIREBASE_API_KEY=$FIREBASE_API_KEY,GEMINI_API_KEY=$GEMINI_API_KEY,APPLE_CLIENT_ID=$APPLE_CLIENT_ID,APPLE_TEAM_ID=$APPLE_TEAM_ID,APPLE_KEY_ID=$APPLE_KEY_ID,GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID,GOOGLE_CLIENT_SECRET=$GOOGLE_CLIENT_SECRET,RUST_LOG=info,RELEASE_SECRET=$RELEASE_SECRET,RESEND_API_KEY=$RESEND_API_KEY,SENTRY_AUTH_TOKEN=$SENTRY_AUTH_TOKEN,SENTRY_ADMIN_UID=$SENTRY_ADMIN_UID,SENTRY_WEBHOOK_SECRET=$SENTRY_WEBHOOK_SECRET,REDIS_DB_HOST=$REDIS_DB_HOST,REDIS_DB_PORT=$REDIS_DB_PORT,REDIS_DB_PASSWORD=$REDIS_DB_PASSWORD" \
    --quiet

# Add APPLE_PRIVATE_KEY separately (multiline value requires special handling)
echo "  Adding Apple Sign-In private key..."
gcloud run services update "$CLOUD_RUN_SERVICE" \
    --project "$GCP_PROJECT" \
    --region "$GCP_REGION" \
    --update-env-vars "^@^APPLE_PRIVATE_KEY=$APPLE_PRIVATE_KEY" \
    --quiet

echo "  ✓ Backend deployed"

# -----------------------------------------------------------------------------
# Step 1.1: Check settings search coverage
# -----------------------------------------------------------------------------
echo "[1.1/12] Checking settings search coverage..."
if xcrun swift scripts/check_settings_search.swift; then
    echo "  ✓ Settings search coverage verified"
else
    echo "  Settings search coverage check FAILED!"
    echo "  Fix missing entries in SettingsSidebar.swift before releasing."
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 1.5: Prepare Universal ffmpeg (arm64 + x86_64)
# -----------------------------------------------------------------------------
echo "[1.5/12] Preparing universal ffmpeg binary..."

FFMPEG_RESOURCE="Desktop/Sources/Resources/ffmpeg"
FFMPEG_TEMP_DIR="/tmp/ffmpeg-universal-$$"

# Check if current ffmpeg is already universal
if file "$FFMPEG_RESOURCE" 2>/dev/null | grep -q "universal binary"; then
    echo "  ffmpeg is already universal, skipping download"
else
    echo "  Current ffmpeg is single-arch, creating universal binary..."

    mkdir -p "$FFMPEG_TEMP_DIR"

    # Backup current ffmpeg to temp dir (NOT source dir to avoid build cache issues)
    if [ -f "$FFMPEG_RESOURCE" ]; then
        cp "$FFMPEG_RESOURCE" "$FFMPEG_TEMP_DIR/ffmpeg.backup"
    fi

    # Download arm64 ffmpeg from Martin Riedl
    echo "  Downloading arm64 ffmpeg..."
    curl -L -o "$FFMPEG_TEMP_DIR/ffmpeg-arm64.zip" \
        "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip" || {
        echo "Error: Failed to download arm64 ffmpeg"
        exit 1
    }
    unzip -q -o "$FFMPEG_TEMP_DIR/ffmpeg-arm64.zip" -d "$FFMPEG_TEMP_DIR/arm64/"

    # Download x86_64 ffmpeg from Martin Riedl (or use evermeet.cx backup)
    echo "  Downloading x86_64 ffmpeg..."
    curl -L -o "$FFMPEG_TEMP_DIR/ffmpeg-x86_64.zip" \
        "https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffmpeg.zip" || {
        echo "Error: Failed to download x86_64 ffmpeg"
        exit 1
    }
    unzip -q -o "$FFMPEG_TEMP_DIR/ffmpeg-x86_64.zip" -d "$FFMPEG_TEMP_DIR/x86_64/"

    # Find the ffmpeg binaries
    ARM64_FFMPEG=$(find "$FFMPEG_TEMP_DIR/arm64" -name "ffmpeg" -type f | head -1)
    X86_64_FFMPEG=$(find "$FFMPEG_TEMP_DIR/x86_64" -name "ffmpeg" -type f | head -1)

    if [ -z "$ARM64_FFMPEG" ] || [ -z "$X86_64_FFMPEG" ]; then
        echo "Error: Could not find ffmpeg binaries in downloaded archives"
        echo "  arm64: $ARM64_FFMPEG"
        echo "  x86_64: $X86_64_FFMPEG"
        exit 1
    fi

    # Create universal binary with lipo
    echo "  Creating universal ffmpeg with lipo..."
    lipo -create "$ARM64_FFMPEG" "$X86_64_FFMPEG" -output "$FFMPEG_RESOURCE"

    # Make executable and ad-hoc sign (required for Apple Silicon)
    chmod +x "$FFMPEG_RESOURCE"
    xattr -cr "$FFMPEG_RESOURCE"
    codesign -f -s - "$FFMPEG_RESOURCE"

    # Verify it's universal
    if file "$FFMPEG_RESOURCE" | grep -q "universal binary"; then
        echo "  ✓ Universal ffmpeg created successfully"
    else
        echo "Error: Failed to create universal ffmpeg"
        if [ -f "$FFMPEG_TEMP_DIR/ffmpeg.backup" ]; then
            mv "$FFMPEG_TEMP_DIR/ffmpeg.backup" "$FFMPEG_RESOURCE"
        fi
        exit 1
    fi

    # Cleanup temp files
    rm -rf "$FFMPEG_TEMP_DIR"
fi

# Show ffmpeg architectures
echo "  ffmpeg: $(file "$FFMPEG_RESOURCE" | sed 's/.*: //')"

# -----------------------------------------------------------------------------
# Step 1.6: Prepare Universal Node.js binary (for AI chat / Claude Agent Bridge)
# -----------------------------------------------------------------------------
echo "[1.6/12] Preparing universal Node.js binary..."

NODE_RESOURCE="Desktop/Sources/Resources/node"
NODE_TEMP_DIR="/tmp/node-universal-$$"
NODE_VERSION="v22.14.0"

# Check if current node is already universal
if file "$NODE_RESOURCE" 2>/dev/null | grep -q "universal binary"; then
    echo "  Node.js is already universal, skipping download"
else
    echo "  Creating universal Node.js binary..."

    mkdir -p "$NODE_TEMP_DIR"

    # Backup current node if exists
    if [ -f "$NODE_RESOURCE" ]; then
        cp "$NODE_RESOURCE" "$NODE_TEMP_DIR/node.backup"
    fi

    # Download arm64 Node.js
    echo "  Downloading arm64 Node.js $NODE_VERSION..."
    curl -L -o "$NODE_TEMP_DIR/node-arm64.tar.gz" \
        "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-darwin-arm64.tar.gz" || {
        echo "Error: Failed to download arm64 Node.js"
        exit 1
    }
    tar -xzf "$NODE_TEMP_DIR/node-arm64.tar.gz" -C "$NODE_TEMP_DIR" --strip-components=1 --include="*/bin/node" 2>/dev/null || \
    tar -xzf "$NODE_TEMP_DIR/node-arm64.tar.gz" -C "$NODE_TEMP_DIR"
    ARM64_NODE=$(find "$NODE_TEMP_DIR" -name "node" -type f | head -1)
    # Move arm64 node aside so x86_64 extraction doesn't overwrite
    mv "$ARM64_NODE" "$NODE_TEMP_DIR/node-arm64"

    # Download x86_64 Node.js
    echo "  Downloading x86_64 Node.js $NODE_VERSION..."
    curl -L -o "$NODE_TEMP_DIR/node-x86_64.tar.gz" \
        "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-darwin-x64.tar.gz" || {
        echo "Error: Failed to download x86_64 Node.js"
        exit 1
    }
    tar -xzf "$NODE_TEMP_DIR/node-x86_64.tar.gz" -C "$NODE_TEMP_DIR" --strip-components=1 --include="*/bin/node" 2>/dev/null || \
    tar -xzf "$NODE_TEMP_DIR/node-x86_64.tar.gz" -C "$NODE_TEMP_DIR"
    X86_64_NODE=$(find "$NODE_TEMP_DIR" -name "node" -type f ! -name "node-arm64" | head -1)

    if [ -z "$NODE_TEMP_DIR/node-arm64" ] || [ ! -f "$NODE_TEMP_DIR/node-arm64" ] || [ -z "$X86_64_NODE" ]; then
        echo "Error: Could not find Node.js binaries in downloaded archives"
        exit 1
    fi

    # Create universal binary with lipo
    echo "  Creating universal Node.js with lipo..."
    lipo -create "$NODE_TEMP_DIR/node-arm64" "$X86_64_NODE" -output "$NODE_RESOURCE"

    # Make executable and ad-hoc sign
    chmod +x "$NODE_RESOURCE"
    xattr -cr "$NODE_RESOURCE"
    codesign -f -s - "$NODE_RESOURCE"

    # Verify it's universal
    if file "$NODE_RESOURCE" | grep -q "universal binary"; then
        echo "  ✓ Universal Node.js created successfully"
    else
        echo "Error: Failed to create universal Node.js"
        if [ -f "$NODE_TEMP_DIR/node.backup" ]; then
            mv "$NODE_TEMP_DIR/node.backup" "$NODE_RESOURCE"
        fi
        exit 1
    fi

    # Cleanup temp files
    rm -rf "$NODE_TEMP_DIR"
fi

# Show node architectures
echo "  node: $(file "$NODE_RESOURCE" | sed 's/.*: //')"

# -----------------------------------------------------------------------------
# Step 2: Build Desktop App (Universal Binary: arm64 + x86_64)
# -----------------------------------------------------------------------------
echo "[2/12] Building $APP_NAME (Universal Binary)..."

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Build agent-bridge (Node.js Claude Code integration)
AGENT_BRIDGE_DIR="$(dirname "$0")/agent-bridge"
if [ -d "$AGENT_BRIDGE_DIR" ]; then
    echo "  Building agent-bridge..."
    cd "$AGENT_BRIDGE_DIR"
    npm install --no-fund --no-audit
    npx tsc
    cd - > /dev/null
fi

# Build for Apple Silicon (arm64)
echo "  Building for arm64..."
xcrun swift build -c release --package-path Desktop --triple arm64-apple-macosx

# Build for Intel (x86_64)
echo "  Building for x86_64..."
xcrun swift build -c release --package-path Desktop --triple x86_64-apple-macosx

# Get binary paths for each architecture
ARM64_BINARY="Desktop/.build/arm64-apple-macosx/release/$BINARY_NAME"
X86_64_BINARY="Desktop/.build/x86_64-apple-macosx/release/$BINARY_NAME"

if [ ! -f "$ARM64_BINARY" ]; then
    echo "Error: arm64 binary not found at $ARM64_BINARY"
    exit 1
fi
if [ ! -f "$X86_64_BINARY" ]; then
    echo "Error: x86_64 binary not found at $X86_64_BINARY"
    exit 1
fi

# Create app bundle
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"
mkdir -p "$APP_BUNDLE/Contents/Frameworks"

# Create universal binary with lipo
echo "  Creating universal binary with lipo..."
lipo -create "$ARM64_BINARY" "$X86_64_BINARY" -output "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME"

# Verify universal binary
echo "  Verifying universal binary..."
file "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME" | grep -q "universal binary" || {
    echo "Error: Failed to create universal binary"
    exit 1
}

cp Desktop/Info.plist "$APP_BUNDLE/Contents/Info.plist"

# Copy Sparkle framework (already universal from SPM)
SPARKLE_FRAMEWORK="Desktop/.build/arm64-apple-macosx/release/Sparkle.framework"
if [ -d "$SPARKLE_FRAMEWORK" ]; then
    cp -R "$SPARKLE_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
    echo "  Copied Sparkle.framework (universal)"
else
    echo "Error: Sparkle.framework not found at $SPARKLE_FRAMEWORK"
    exit 1
fi

# Add rpath for embedded frameworks (required for Sparkle to be found at runtime)
install_name_tool -add_rpath "@executable_path/../Frameworks" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME"
echo "  Added Frameworks rpath"

# Copy icon if exists
if [ -f "omi_icon.icns" ]; then
    cp omi_icon.icns "$APP_BUNDLE/Contents/Resources/OmiIcon.icns"
fi

# Copy GoogleService-Info.plist for Firebase
cp Desktop/Sources/GoogleService-Info.plist "$APP_BUNDLE/Contents/Resources/"

# Copy resource bundle (contains app assets like permissions.gif, herologo.png, etc.)
# Note: Bundle goes in Contents/Resources/ - our custom BundleExtension.swift looks for it there
SWIFT_BUILD_DIR="Desktop/.build/arm64-apple-macosx/release"
if [ -d "$SWIFT_BUILD_DIR/Omi Computer_Omi Computer.bundle" ]; then
    cp -R "$SWIFT_BUILD_DIR/Omi Computer_Omi Computer.bundle" "$APP_BUNDLE/Contents/Resources/"
    echo "  Copied resource bundle"
else
    echo "Warning: Resource bundle not found at $SWIFT_BUILD_DIR/Omi Computer_Omi Computer.bundle"
fi

# Update Info.plist with version and bundle info
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $BINARY_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || \
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $BUILD_NUMBER" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 14.0" "$APP_BUNDLE/Contents/Info.plist"

# Copy .env.app (app runtime secrets only - not build secrets)
if [ -f ".env.app" ]; then
    cp ".env.app" "$APP_BUNDLE/Contents/Resources/.env"
    echo "  Copied .env.app to bundle"
else
    echo "  Warning: No .env.app file found"
fi

# Copy agent-bridge (Node.js Claude Code integration)
if [ -d "$AGENT_BRIDGE_DIR/dist" ]; then
    mkdir -p "$APP_BUNDLE/Contents/Resources/agent-bridge"
    cp -Rf "$AGENT_BRIDGE_DIR/dist" "$APP_BUNDLE/Contents/Resources/agent-bridge/"
    cp -f "$AGENT_BRIDGE_DIR/package.json" "$APP_BUNDLE/Contents/Resources/agent-bridge/"
    cp -Rf "$AGENT_BRIDGE_DIR/node_modules" "$APP_BUNDLE/Contents/Resources/agent-bridge/"
    echo "  Copied agent-bridge to bundle"
fi

echo -n "APPL????" > "$APP_BUNDLE/Contents/PkgInfo"

# Embed provisioning profile (required for Sign In with Apple entitlement)
if [ -f "Desktop/embedded.provisionprofile" ]; then
    cp "Desktop/embedded.provisionprofile" "$APP_BUNDLE/Contents/embedded.provisionprofile"
    echo "  Copied provisioning profile"
fi

echo "  ✓ Build complete"

# -----------------------------------------------------------------------------
# Step 3: Sign App
# -----------------------------------------------------------------------------
echo "[3/12] Signing app with Developer ID..."

# Remove extended attributes that block code signing
xattr -cr "$APP_BUNDLE"

# Sign ffmpeg binary in resource bundle (if present)
FFMPEG_PATH="$APP_BUNDLE/Contents/Resources/Omi Computer_Omi Computer.bundle/ffmpeg"
if [ -f "$FFMPEG_PATH" ]; then
    echo "  Signing ffmpeg binary..."
    codesign --force --options runtime --timestamp \
        --sign "$SIGN_IDENTITY" \
        "$FFMPEG_PATH"
fi

# Sign node binary in resource bundle (if present)
# Node.js requires JIT entitlements for V8 and WebAssembly (used by fetch/undici).
# Without these, Hardened Runtime blocks MAP_JIT causing SIGTRAP on launch.
NODE_BUNDLE_PATH="$APP_BUNDLE/Contents/Resources/Omi Computer_Omi Computer.bundle/node"
if [ -f "$NODE_BUNDLE_PATH" ]; then
    echo "  Signing node binary (with JIT entitlements)..."
    codesign --force --options runtime --timestamp \
        --sign "$SIGN_IDENTITY" \
        --entitlements Desktop/Node.entitlements \
        "$NODE_BUNDLE_PATH"
fi

# Sign native binaries in agent-bridge node_modules
AGENT_BRIDGE_RESOURCES="$APP_BUNDLE/Contents/Resources/agent-bridge/node_modules"
if [ -d "$AGENT_BRIDGE_RESOURCES" ]; then
    echo "  Signing agent-bridge native binaries..."
    find "$AGENT_BRIDGE_RESOURCES" \( -name "*.node" -o -name "*.dylib" -o -name "rg" \) -type f | while read -r binary; do
        codesign --force --options runtime --timestamp \
            --sign "$SIGN_IDENTITY" \
            "$binary" 2>/dev/null && echo "    Signed: $(basename "$binary")" || true
    done
fi

# Sign Sparkle framework components (innermost first)
# XPC Services
codesign --force --options runtime --timestamp \
    --sign "$SIGN_IDENTITY" \
    "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework/Versions/B/XPCServices/Downloader.xpc"
codesign --force --options runtime --timestamp \
    --sign "$SIGN_IDENTITY" \
    "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework/Versions/B/XPCServices/Installer.xpc"
# Autoupdate and Updater.app
codesign --force --options runtime --timestamp \
    --sign "$SIGN_IDENTITY" \
    "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework/Versions/B/Autoupdate"
codesign --force --options runtime --timestamp \
    --sign "$SIGN_IDENTITY" \
    "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework/Versions/B/Updater.app"
# Framework itself
codesign --force --options runtime --timestamp \
    --sign "$SIGN_IDENTITY" \
    "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"

# Sign the main app
codesign --force --options runtime --timestamp \
    --sign "$SIGN_IDENTITY" \
    --entitlements Desktop/Omi-Release.entitlements \
    "$APP_BUNDLE"

codesign --verify --verbose=2 "$APP_BUNDLE" 2>&1 | head -3
echo "  ✓ App signed"

# -----------------------------------------------------------------------------
# Step 4: Notarize App
# -----------------------------------------------------------------------------
echo "[4/12] Notarizing app (this may take a minute)..."

# Create temporary zip for notarization
TEMP_ZIP="$BUILD_DIR/notarize-temp.zip"
ditto -c -k --keepParent "$APP_BUNDLE" "$TEMP_ZIP"

xcrun notarytool submit "$TEMP_ZIP" \
    --apple-id "$APPLE_ID" \
    --team-id "$TEAM_ID" \
    --password "$NOTARIZE_PASSWORD" \
    --wait

rm -f "$TEMP_ZIP"
echo "  ✓ App notarized"

# -----------------------------------------------------------------------------
# Step 5: Staple App
# -----------------------------------------------------------------------------
echo "[5/12] Stapling notarization ticket to app..."

xcrun stapler staple "$APP_BUNDLE"
echo "  ✓ App stapled"

# -----------------------------------------------------------------------------
# Step 6: Create DMG (with Applications shortcut for drag-to-install)
# -----------------------------------------------------------------------------
echo "[6/12] Creating installer DMG..."

rm -f "$DMG_PATH"

# Copy app to temp staging directory
# IMPORTANT: Use ditto instead of cp -R to preserve extended attributes
# (extended attributes contain the notarization stapling ticket)
STAGING_DIR="/tmp/omi-dmg-staging-$$"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
DMG_APP_NAME="$APP_NAME"
ditto "$APP_BUNDLE" "$STAGING_DIR/$DMG_APP_NAME.app"
STAGED_APP="$STAGING_DIR/$DMG_APP_NAME.app"

# Verify stapling was preserved, re-staple if needed
if ! xcrun stapler validate "$STAGED_APP" 2>/dev/null; then
    echo "  Re-stapling app in staging directory..."
    xcrun stapler staple "$STAGED_APP"
fi

# Use create-dmg for a proper installer DMG with Applications shortcut
if command -v create-dmg &> /dev/null; then
    # Use background image if available
    BG_ARGS=""
    if [ -f "dmg-assets/background.png" ]; then
        BG_ARGS="--background dmg-assets/background.png"
    fi

    create-dmg \
        --volname "$APP_NAME" \
        --volicon "$STAGED_APP/Contents/Resources/OmiIcon.icns" \
        --window-pos 200 120 \
        --window-size 610 365 \
        --icon-size 80 \
        --icon "$DMG_APP_NAME.app" 155 175 \
        --hide-extension "$DMG_APP_NAME.app" \
        --app-drop-link 455 175 \
        --no-internet-enable \
        $BG_ARGS \
        "$DMG_PATH" \
        "$STAGED_APP"
else
    # Fallback to basic hdiutil if create-dmg not available
    echo "  Warning: create-dmg not found, using basic DMG creation"
    hdiutil create -volname "$APP_NAME" \
        -srcfolder "$STAGED_APP" \
        -ov -format UDZO \
        "$DMG_PATH"
fi

# Clean up staging directory
rm -rf "$STAGING_DIR"

echo "  ✓ DMG created"

# -----------------------------------------------------------------------------
# Step 7: Sign DMG
# -----------------------------------------------------------------------------
echo "[7/12] Signing DMG..."

codesign --force --sign "$SIGN_IDENTITY" "$DMG_PATH"
echo "  ✓ DMG signed"

# -----------------------------------------------------------------------------
# Step 8: Notarize DMG
# -----------------------------------------------------------------------------
echo "[8/12] Notarizing DMG..."

xcrun notarytool submit "$DMG_PATH" \
    --apple-id "$APPLE_ID" \
    --team-id "$TEAM_ID" \
    --password "$NOTARIZE_PASSWORD" \
    --wait

echo "  ✓ DMG notarized"

# -----------------------------------------------------------------------------
# Step 9: Staple DMG
# -----------------------------------------------------------------------------
echo "[9/12] Stapling notarization ticket to DMG..."

xcrun stapler staple "$DMG_PATH"
echo "  ✓ DMG stapled"

# Set custom icon on DMG file (must be after signing/stapling to persist)
if [ -f "omi_icon.icns" ]; then
    echo "  Setting DMG file icon..."
    if command -v fileicon &> /dev/null; then
        fileicon set "$DMG_PATH" omi_icon.icns && echo "    Icon set successfully" || echo "    Warning: Could not set icon"
    else
        echo "    Warning: fileicon not installed (brew install fileicon)"
    fi
fi

# -----------------------------------------------------------------------------
# Step 10: Create Sparkle ZIP and Sign for Auto-Update
# -----------------------------------------------------------------------------
echo "[10/12] Creating Sparkle update package..."

# Check if Sparkle tools are available
SPARKLE_BIN=""
if [ -d "Desktop/.build/artifacts/sparkle/Sparkle/bin" ]; then
    SPARKLE_BIN="Desktop/.build/artifacts/sparkle/Sparkle/bin"
fi

# Create ZIP of the app bundle for Sparkle (Sparkle expects .app in a ZIP, not DMG)
rm -f "$SPARKLE_ZIP_PATH"
ditto -c -k --keepParent "$APP_BUNDLE" "$SPARKLE_ZIP_PATH"
echo "  Created: $SPARKLE_ZIP_PATH"

# Sign the ZIP with Sparkle EdDSA signature
ED_SIGNATURE=""
if [ -n "$SPARKLE_BIN" ] && [ -f "$SPARKLE_BIN/sign_update" ]; then
    if [ -n "$SPARKLE_PRIVATE_KEY" ]; then
        # Use private key from environment
        ED_SIGNATURE=$(echo "$SPARKLE_PRIVATE_KEY" | "$SPARKLE_BIN/sign_update" "$SPARKLE_ZIP_PATH" --ed-key-file - 2>/dev/null | grep "sparkle:edSignature" | sed 's/.*edSignature="\([^"]*\)".*/\1/')
    else
        # Try to use key from Keychain
        ED_SIGNATURE=$("$SPARKLE_BIN/sign_update" "$SPARKLE_ZIP_PATH" 2>/dev/null | grep "sparkle:edSignature" | sed 's/.*edSignature="\([^"]*\)".*/\1/')
    fi

    if [ -n "$ED_SIGNATURE" ]; then
        echo "  EdDSA signature: $ED_SIGNATURE"
    else
        echo "  Warning: Could not generate EdDSA signature"
    fi
else
    echo "  Warning: Sparkle sign_update not found, skipping signature"
fi

# -----------------------------------------------------------------------------
# Step 11: Create GitHub Release & Register in Firestore
# -----------------------------------------------------------------------------
echo "[11/12] Publishing to GitHub and registering release..."

# Tag format: v{version}+{build}-macos
RELEASE_TAG="v${VERSION}+${BUILD_NUMBER}-macos"

# Create release notes
RELEASE_NOTES=$(cat <<EOF
## Omi Desktop v${VERSION}

### What's New
$CHANGELOG_MD

### Downloads
- **DMG Installer**: For fresh installs, download the DMG below
- **Auto-Update**: Existing users will receive this update automatically
EOF
)

# Check if gh CLI is available
if command -v gh &> /dev/null; then
    # Delete existing release if it exists (ensures re-runs are safe)
    if gh release view "$RELEASE_TAG" --repo "$GITHUB_REPO" &>/dev/null; then
        echo "  Deleting existing GitHub release $RELEASE_TAG..."
        gh release delete "$RELEASE_TAG" --repo "$GITHUB_REPO" --yes 2>/dev/null
    fi

    # Create GitHub release with both Omi.zip and DMG
    gh release create "$RELEASE_TAG" \
        --repo "$GITHUB_REPO" \
        --title "Omi Desktop v${VERSION}" \
        --notes "$RELEASE_NOTES" \
        "$SPARKLE_ZIP_PATH" \
        "$DMG_PATH" \
        2>/dev/null && {
        echo "  ✓ GitHub release created: $RELEASE_TAG"
        echo "  ✓ Uploaded: Omi.zip (for auto-update)"
        echo "  ✓ Uploaded: $APP_NAME.dmg (for manual download)"
    } || {
        echo "  Warning: Could not create GitHub release"
        echo "  You may need to run: gh auth login"
        echo "  Or create the release manually at: https://github.com/$GITHUB_REPO/releases/new"
    }
else
    echo "  Warning: GitHub CLI (gh) not found"
    echo "  Install with: brew install gh"
fi

# Upload DMG to GCS for direct downloads (avoids GitHub redirect chain that triggers Chrome warnings)
GCS_BUCKET="gs://omi_macos_updates"
echo "  Uploading DMG to GCS..."
gcloud storage cp --content-disposition='attachment; filename="Omi Beta.dmg"' "$DMG_PATH" "$GCS_BUCKET/releases/v${VERSION}/Omi.Beta.dmg" 2>/dev/null && {
    echo "  ✓ Uploaded DMG to GCS (versioned)"
} || {
    echo "  Warning: Could not upload DMG to GCS"
}
# Only update the latest/ pointer for stable releases (macos.omi.me serves this)
if [ "$RELEASE_CHANNEL" = "stable" ]; then
    gcloud storage cp "$GCS_BUCKET/releases/v${VERSION}/Omi.Beta.dmg" "$GCS_BUCKET/latest/Omi.Beta.dmg" 2>/dev/null && {
        echo "  ✓ Updated latest/ pointer (direct download)"
    } || {
        echo "  Warning: Could not update latest/ pointer"
    }
else
    echo "  ⏭ Skipping latest/ update (channel: $RELEASE_CHANNEL)"
fi

# Get the GitHub release download URL for Omi.zip
DOWNLOAD_URL="https://github.com/$GITHUB_REPO/releases/download/$RELEASE_TAG/Omi.zip"

# Register release in Firestore via backend API
if [ -n "$RELEASE_SECRET" ]; then
    # Create JSON payload
    RELEASE_JSON=$(cat <<EOJSON
{
    "version": "$VERSION",
    "build_number": $BUILD_NUMBER,
    "download_url": "$DOWNLOAD_URL",
    "ed_signature": "$ED_SIGNATURE",
    "changelog": $CHANGELOG_JSON,
    "is_live": true,
    "is_critical": false,
    "channel": "${RELEASE_CHANNEL:-staging}"
}
EOJSON
)

    # Register release via backend API
    HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -H "X-Release-Secret: $RELEASE_SECRET" \
        -d "$RELEASE_JSON" \
        "$DESKTOP_BACKEND_URL/updates/releases" 2>/dev/null)

    HTTP_CODE=$(echo "$HTTP_RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" = "201" ]; then
        echo "  ✓ Release registered in Firestore"
    else
        echo "  Warning: Could not register release (HTTP $HTTP_CODE)"
        echo "  You can manually add it using: local-scripts/add_release.py"
    fi
else
    echo "  Warning: RELEASE_SECRET not set, skipping Firestore registration"
    echo "  Set RELEASE_SECRET in .env or environment"
fi

# -----------------------------------------------------------------------------
# Create local git tag for version tracking
# -----------------------------------------------------------------------------
echo ""
echo "Creating local git tag..."
git tag "v$VERSION" 2>/dev/null && echo "  ✓ Created tag v$VERSION" || echo "  Tag v$VERSION already exists"

# -----------------------------------------------------------------------------
# Step 12: Trigger Installation Test
# -----------------------------------------------------------------------------
echo ""
echo "[12/12] Triggering installation test on GitHub Actions..."

# Trigger the test workflow via repository_dispatch
TEST_REPO="m13v/omi-computer-swift"
if command -v gh &> /dev/null; then
    gh workflow run test-install.yml \
        --repo "$TEST_REPO" \
        -f release_tag="$RELEASE_TAG" 2>/dev/null && {
        echo "  ✓ Installation test triggered"
        echo "  View results: https://github.com/$TEST_REPO/actions/workflows/test-install.yml"
    } || {
        echo "  Warning: Could not trigger test workflow"
        echo "  You can run it manually: gh workflow run test-install.yml --repo $TEST_REPO"
    }
else
    echo "  Warning: GitHub CLI (gh) not found, skipping test trigger"
fi

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
ELAPSED_MIN=$((ELAPSED / 60))
ELAPSED_SEC=$((ELAPSED % 60))

echo ""
echo "=============================================="
echo "  Release $VERSION Complete!"
echo "  Total time: ${ELAPSED_MIN}m ${ELAPSED_SEC}s"
echo "=============================================="
echo ""
echo "Local files:"
echo "  App: $APP_BUNDLE"
echo "  DMG: $DMG_PATH"
echo "  Sparkle ZIP: $SPARKLE_ZIP_PATH"
echo ""
echo "Download URL:"
echo "  https://github.com/$GITHUB_REPO/releases/tag/$RELEASE_TAG"
echo ""
echo "Auto-Update:"
echo "  Appcast URL: $DESKTOP_BACKEND_URL/appcast.xml"
echo "  EdDSA Signature: ${ED_SIGNATURE:-'(not generated)'}"
echo ""
echo "Verify with:"
echo "  spctl --assess --verbose=2 $APP_BUNDLE"
echo "  spctl --assess --verbose=2 --type open --context context:primary-signature $DMG_PATH"
echo ""
