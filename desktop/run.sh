#!/bin/bash
set -e

# Clear system OPENAI_API_KEY so .env takes precedence
unset OPENAI_API_KEY

# Use Xcode's default toolchain to match the SDK version
unset TOOLCHAINS

# Timing utilities
SCRIPT_START_TIME=$(date +%s.%N)
STEP_START_TIME=$SCRIPT_START_TIME

step() {
    local now=$(date +%s.%N)
    local step_elapsed=$(echo "$now - $STEP_START_TIME" | bc)
    local total_elapsed=$(echo "$now - $SCRIPT_START_TIME" | bc)
    if [ "$STEP_START_TIME" != "$SCRIPT_START_TIME" ]; then
        printf "  └─ done (%.2fs)\n" "$step_elapsed"
    fi
    STEP_START_TIME=$now
    printf "[%6.1fs] %s\n" "$total_elapsed" "$1"
}

substep() {
    local now=$(date +%s.%N)
    local total_elapsed=$(echo "$now - $SCRIPT_START_TIME" | bc)
    printf "[%6.1fs]   ├─ %s\n" "$total_elapsed" "$1"
}

# App configuration
BINARY_NAME="Omi Computer"  # Package.swift target — binary paths, pkill, CFBundleExecutable
APP_NAME="${OMI_APP_NAME:-Omi Dev}"

slugify_identifier() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g'
}

if [ "$APP_NAME" = "Omi Dev" ]; then
    EXPECTED_BUNDLE_ID="com.omi.desktop-dev"
    EXPECTED_URL_SCHEME="omi-computer-dev"
else
    APP_SLUG="$(slugify_identifier "$APP_NAME")"
    if [ -z "$APP_SLUG" ]; then
        echo "ERROR: OMI_APP_NAME must contain at least one letter or number"
        exit 1
    fi
    EXPECTED_BUNDLE_ID="com.omi.$APP_SLUG"
    EXPECTED_URL_SCHEME="omi-$APP_SLUG"
fi

BUNDLE_ID="${OMI_BUNDLE_ID:-$EXPECTED_BUNDLE_ID}"
BUILD_DIR="build"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
APP_PATH="/Applications/$APP_NAME.app"
APP_DESKTOP_PATH="$HOME/Desktop/$APP_NAME.app"
APP_DOWNLOADS_PATH="$HOME/Downloads/$APP_NAME.app"
SIGN_IDENTITY="${OMI_SIGN_IDENTITY:-}"
URL_SCHEME="${OMI_URL_SCHEME:-$EXPECTED_URL_SCHEME}"

if [ "$BUNDLE_ID" != "$EXPECTED_BUNDLE_ID" ]; then
    echo "ERROR: APP_NAME '$APP_NAME' must use bundle ID '$EXPECTED_BUNDLE_ID' (got '$BUNDLE_ID')"
    exit 1
fi

if [ "$URL_SCHEME" != "$EXPECTED_URL_SCHEME" ]; then
    echo "ERROR: APP_NAME '$APP_NAME' must use URL scheme '$EXPECTED_URL_SCHEME' (got '$URL_SCHEME')"
    exit 1
fi
AUTOMATION_ARGS=()
if [ "${OMI_ENABLE_LOCAL_AUTOMATION:-0}" = "1" ]; then
    AUTOMATION_PORT="${OMI_AUTOMATION_PORT:-47777}"
    AUTOMATION_ARGS+=(--automation-bridge "--automation-port=$AUTOMATION_PORT")
fi

# Backend configuration (Rust)
BACKEND_DIR="$(cd "$(dirname "$0")/Backend-Rust" && pwd)"
AUTH_DIR="$(cd "$(dirname "$0")/Auth-Python" && pwd)"
BACKEND_PID=""
AUTH_PID=""
TUNNEL_PID=""
TUNNEL_URL="https://omi-dev.m13v.com"
AUTH_PORT="${AUTH_PORT:-10200}"

# Cleanup function to stop backend, auth, and tunnel on exit
cleanup() {
    if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "Stopping tunnel (PID: $TUNNEL_PID)..."
        kill "$TUNNEL_PID" 2>/dev/null || true
    fi
    if [ -n "$AUTH_PID" ] && kill -0 "$AUTH_PID" 2>/dev/null; then
        echo "Stopping auth service (PID: $AUTH_PID)..."
        kill "$AUTH_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

AUTH_DEBUG_LOG=/private/tmp/auth-debug.log
rm -f $AUTH_DEBUG_LOG
auth_debug() { echo "[AUTH DEBUG][$(date +%H:%M:%S)] $1" >> $AUTH_DEBUG_LOG; }
touch $AUTH_DEBUG_LOG

step "Killing existing instances..."
auth_debug "BEFORE pkill: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"
auth_debug "BEFORE pkill: ALL_KEYS=$(defaults read "$BUNDLE_ID" 2>&1 | grep -E 'auth_|hasCompleted|hasLaunched|currentTier|userShow' || true)"
# Only kill the dev app — never touch Omi Beta (production)
pkill -f "$APP_NAME.app" 2>/dev/null || true
pkill -f "cloudflared.*omi-computer-dev" 2>/dev/null || true
# Kill only the Rust backend on port 8080 (not other apps that might use it)
lsof -ti:8080 -sTCP:LISTEN 2>/dev/null | while read pid; do
    if ps -p "$pid" -o command= 2>/dev/null | grep -q "omi-backend\|Backend-Rust\|target/"; then
        kill -9 "$pid" 2>/dev/null || true
    fi
done
sleep 0.5  # Let cfprefsd flush after process death
auth_debug "AFTER pkill: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"
auth_debug "AFTER pkill: ALL_KEYS=$(defaults read "$BUNDLE_ID" 2>&1 | grep -E 'auth_|hasCompleted|hasLaunched|currentTier|userShow' || true)"

# Clear log file for fresh run (must be before backend starts)
rm -f /tmp/omi-dev.log 2>/dev/null || true

step "Cleaning up conflicting app bundles..."
# Clean old build names from local build dir
rm -rf "$BUILD_DIR/Omi Computer.app" 2>/dev/null
rm -rf "$APP_BUNDLE" 2>/dev/null
CONFLICTING_APPS=(
    "$APP_PATH"
    "$APP_DESKTOP_PATH"
    "$APP_DOWNLOADS_PATH"
    "$(dirname "$0")/../app/build/macos/Build/Products/Debug/Omi.app"
    "$(dirname "$0")/../app/build/macos/Build/Products/Release/Omi.app"
)
for app in "${CONFLICTING_APPS[@]}"; do
    if [ -d "$app" ]; then
        substep "Removing: $app"
        rm -rf "$app"
    fi
done
# Also remove any stale dev app bundles nested inside Flutter builds.
find "$(dirname "$0")/../app/build" -name "$APP_NAME.app" -type d -exec rm -rf {} + 2>/dev/null || true
# Kill stale app bundles from other repo clones (e.g. ~/omi-desktop/)
# These confuse LaunchServices and get launched instead of the /Applications copy.
find "$HOME" -maxdepth 4 -name "$APP_NAME.app" -type d -not -path "$APP_BUNDLE" -not -path "$APP_PATH" 2>/dev/null | while read stale; do
    substep "Removing stale clone: $stale"
    rm -rf "$stale"
done

step "Starting Cloudflare tunnel..."
cloudflared tunnel run omi-computer-dev &
TUNNEL_PID=$!
sleep 2

step "Starting Rust backend..."
cd "$BACKEND_DIR"

# Copy .env if not present
if [ ! -f ".env" ] && [ -f "../backend/.env" ]; then
    cp "../backend/.env" ".env"
elif [ ! -f ".env" ] && [ -f "../Backend/.env" ]; then
    cp "../Backend/.env" ".env"
fi

# Symlink google-credentials.json if not present
if [ ! -f "google-credentials.json" ] && [ -f "../backend/google-credentials.json" ]; then
    ln -sf "../backend/google-credentials.json" "google-credentials.json"
elif [ ! -f "google-credentials.json" ] && [ -f "../Backend/google-credentials.json" ]; then
    ln -sf "../Backend/google-credentials.json" "google-credentials.json"
fi

# Set Firestore credentials for local backend.
CREDS_PATH="$BACKEND_DIR/google-credentials.json"
if [ ! -f "$CREDS_PATH" ]; then
    echo "Missing credentials file: $CREDS_PATH"
    exit 1
fi
export GOOGLE_APPLICATION_CREDENTIALS="$CREDS_PATH"
# Read FIREBASE_PROJECT_ID from: shell env > backend .env > "based-hardware" default.
# This ensures the project ID matches the service account credentials.
if [ -z "$FIREBASE_PROJECT_ID" ] && [ -f "$BACKEND_DIR/.env" ]; then
    ENV_PROJECT_ID=$(grep "^FIREBASE_PROJECT_ID=" "$BACKEND_DIR/.env" | head -1 | cut -d= -f2-)
    if [ -n "$ENV_PROJECT_ID" ]; then
        export FIREBASE_PROJECT_ID="$ENV_PROJECT_ID"
    fi
fi
if [ -z "$FIREBASE_PROJECT_ID" ]; then
    echo "ERROR: FIREBASE_PROJECT_ID is not set. Add it to $BACKEND_DIR/.env or export it."
    echo "  For prod: FIREBASE_PROJECT_ID=based-hardware"
    echo "  For dev:  FIREBASE_PROJECT_ID=based-hardware-dev"
    exit 1
fi
# When using a dev Firestore project with the prod auth service, auth tokens
# are minted for "based-hardware" (prod). Set FIREBASE_AUTH_PROJECT_ID so the
# backend validates tokens against prod while keeping Firestore on dev.
if [ "$FIREBASE_PROJECT_ID" != "based-hardware" ] && [ -z "$FIREBASE_AUTH_PROJECT_ID" ]; then
    export FIREBASE_AUTH_PROJECT_ID="based-hardware"
    substep "Auth project split: tokens validated against based-hardware (prod), Firestore on $FIREBASE_PROJECT_ID"
fi
# Read backend PORT from .env (the Rust backend uses this)
if [ -z "$PORT" ] && [ -f "$BACKEND_DIR/.env" ]; then
    PORT=$(grep "^PORT=" "$BACKEND_DIR/.env" | head -1 | cut -d= -f2-)
fi
BACKEND_PORT="${PORT:-10201}"
export PORT="$BACKEND_PORT"
substep "Using Firestore creds: $GOOGLE_APPLICATION_CREDENTIALS"
substep "Using Firebase project: $FIREBASE_PROJECT_ID"
substep "Backend port: $BACKEND_PORT, Auth port: $AUTH_PORT"

# Build if binary doesn't exist or source is newer
if [ ! -f "target/release/omi-desktop-backend" ] || [ -n "$(find src -newer target/release/omi-desktop-backend 2>/dev/null)" ]; then
    step "Building Rust backend (cargo build --release)..."
    cargo build --release
fi

./target/release/omi-desktop-backend &
BACKEND_PID=$!
cd - > /dev/null

step "Waiting for backend to start..."
for i in {1..30}; do
    if curl -s "http://localhost:$BACKEND_PORT" > /dev/null 2>&1; then
        substep "Backend is ready!"
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Backend failed to start"
        exit 1
    fi
    sleep 0.5
done

step "Starting Python auth service (port $AUTH_PORT)..."
if [ -d "$AUTH_DIR" ]; then
    # Set up venv if needed
    if [ ! -d "$AUTH_DIR/.venv" ]; then
        substep "Creating virtualenv..."
        python3 -m venv "$AUTH_DIR/.venv"
        "$AUTH_DIR/.venv/bin/pip" install -q -r "$AUTH_DIR/requirements.txt"
    fi
    # Copy .env from backend dir if auth doesn't have its own
    if [ ! -f "$AUTH_DIR/.env" ] && [ -f "$BACKEND_DIR/.env" ]; then
        substep "Using backend .env for auth service"
    fi
    # Auth service shares credentials with the Rust backend
    export BASE_API_URL="http://localhost:$AUTH_PORT"
    (
        cd "$AUTH_DIR"
        if [ -f "$BACKEND_DIR/.env" ]; then
            set -a; source "$BACKEND_DIR/.env"; set +a
        fi
        export GOOGLE_APPLICATION_CREDENTIALS="$CREDS_PATH"
        export BASE_API_URL="http://localhost:$AUTH_PORT"
        .venv/bin/uvicorn main:app --host 0.0.0.0 --port "$AUTH_PORT" --log-level warning &
        echo $!
    ) &
    AUTH_PID=$!
    sleep 1
    if curl -s "http://localhost:$AUTH_PORT/docs" > /dev/null 2>&1; then
        substep "Auth service is ready on port $AUTH_PORT"
    else
        substep "Auth service starting (PID: $AUTH_PID)..."
    fi
else
    substep "Auth-Python/ not found — skipping (auth will use OMI_AUTH_URL from .env)"
fi

# Check if another SwiftPM instance is running (will block our build)
SWIFTPM_PID=$(pgrep -f "swiftpm-workspace-state|swift-build|swift-package" 2>/dev/null | head -1)
if [ -n "$SWIFTPM_PID" ]; then
    step "Waiting for other SwiftPM instance (PID: $SWIFTPM_PID) to finish..."
    while kill -0 "$SWIFTPM_PID" 2>/dev/null; do
        sleep 1
    done
fi

step "Building acp-bridge (npm install + tsc)..."
ACP_BRIDGE_DIR="$(dirname "$0")/acp-bridge"
if [ -d "$ACP_BRIDGE_DIR" ]; then
    cd "$ACP_BRIDGE_DIR"
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules/.package-lock.json" ]; then
        substep "Installing npm dependencies"
        npm install --no-fund --no-audit 2>&1 | tail -1
    fi
    substep "Compiling TypeScript and copying assets"
    npm run build --silent
    cd - > /dev/null
else
    echo "Warning: acp-bridge directory not found at $ACP_BRIDGE_DIR"
fi

step "Checking schema docs..."
if [ -f scripts/check_schema_docs.sh ]; then
    bash scripts/check_schema_docs.sh || substep "Schema docs check failed (non-fatal)"
fi

step "Building Swift app (swift build -c debug)..."
xcrun swift build -c debug --package-path Desktop

auth_debug "AFTER swift build: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"

step "Creating app bundle..."
substep "Creating directories"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"
mkdir -p "$APP_BUNDLE/Contents/Frameworks"

substep "Copying binary ($(du -h "Desktop/.build/debug/$BINARY_NAME" 2>/dev/null | cut -f1))"
cp -f "Desktop/.build/debug/$BINARY_NAME" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME"

substep "Adding rpath for Frameworks"
install_name_tool -add_rpath "@executable_path/../Frameworks" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME" 2>/dev/null || true

# Copy Sparkle framework
SPARKLE_FRAMEWORK="Desktop/.build/arm64-apple-macosx/debug/Sparkle.framework"
if [ -d "$SPARKLE_FRAMEWORK" ]; then
    substep "Copying Sparkle framework ($(du -sh "$SPARKLE_FRAMEWORK" 2>/dev/null | cut -f1))"
    rm -rf "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
    cp -R "$SPARKLE_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
fi

# Copy HeapSwiftCore framework and its dependency CSSwiftProtobuf
HEAP_FRAMEWORK="Desktop/.build/artifacts/heap-swift-core-sdk/HeapSwiftCore/HeapSwiftCore.xcframework/macos-arm64_x86_64/HeapSwiftCore.framework"
if [ -d "$HEAP_FRAMEWORK" ]; then
    substep "Copying HeapSwiftCore framework"
    rm -rf "$APP_BUNDLE/Contents/Frameworks/HeapSwiftCore.framework"
    cp -R "$HEAP_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
fi
CSPROTOBUF_FRAMEWORK="Desktop/.build/artifacts/csswiftprotobuf/CSSwiftProtobuf/CSSwiftProtobuf.xcframework/macos-arm64_x86_64/CSSwiftProtobuf.framework"
if [ -d "$CSPROTOBUF_FRAMEWORK" ]; then
    substep "Copying CSSwiftProtobuf framework"
    rm -rf "$APP_BUNDLE/Contents/Frameworks/CSSwiftProtobuf.framework"
    cp -R "$CSPROTOBUF_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
fi

substep "Copying Info.plist"
cp -f Desktop/Info.plist "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $BINARY_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleURLTypes:0:CFBundleURLSchemes:0 $URL_SCHEME" "$APP_BUNDLE/Contents/Info.plist"

auth_debug "AFTER plist edits: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"

substep "Copying GoogleService-Info.plist"
if [ -f "Desktop/Sources/GoogleService-Info-Dev.plist" ]; then
    cp -f Desktop/Sources/GoogleService-Info-Dev.plist "$APP_BUNDLE/Contents/Resources/GoogleService-Info.plist"
else
    cp -f Desktop/Sources/GoogleService-Info.plist "$APP_BUNDLE/Contents/Resources/"
fi
/usr/libexec/PlistBuddy -c "Set :BUNDLE_ID $BUNDLE_ID" "$APP_BUNDLE/Contents/Resources/GoogleService-Info.plist" 2>/dev/null || true

# Copy resource bundle (contains app assets like permissions.gif, herologo.png, etc.)
RESOURCE_BUNDLE="Desktop/.build/arm64-apple-macosx/debug/Omi Computer_Omi Computer.bundle"
if [ -d "$RESOURCE_BUNDLE" ]; then
    substep "Copying resource bundle ($(du -sh "$RESOURCE_BUNDLE" 2>/dev/null | cut -f1))"
    cp -Rf "$RESOURCE_BUNDLE" "$APP_BUNDLE/Contents/Resources/"
fi

substep "Copying acp-bridge"
if [ -d "$ACP_BRIDGE_DIR/dist" ]; then
    mkdir -p "$APP_BUNDLE/Contents/Resources/acp-bridge"
    cp -Rf "$ACP_BRIDGE_DIR/dist" "$APP_BUNDLE/Contents/Resources/acp-bridge/"
    cp -f "$ACP_BRIDGE_DIR/package.json" "$APP_BUNDLE/Contents/Resources/acp-bridge/"
    cp -Rf "$ACP_BRIDGE_DIR/node_modules" "$APP_BUNDLE/Contents/Resources/acp-bridge/"
fi

substep "Copying .env.app"
if [ -f ".env.app.dev" ]; then
    cp -f .env.app.dev "$APP_BUNDLE/Contents/Resources/.env"
elif [ -f ".env.app" ]; then
    cp -f .env.app "$APP_BUNDLE/Contents/Resources/.env"
else
    touch "$APP_BUNDLE/Contents/Resources/.env"
fi
if grep -q "^OMI_API_URL=" "$APP_BUNDLE/Contents/Resources/.env"; then
    sed -i '' "s|^OMI_API_URL=.*|OMI_API_URL=$TUNNEL_URL|" "$APP_BUNDLE/Contents/Resources/.env"
else
    echo "OMI_API_URL=$TUNNEL_URL" >> "$APP_BUNDLE/Contents/Resources/.env"
fi
# Bootstrap FIREBASE_API_KEY from backend .env so auth can restore on launch
# (before APIKeyService.fetchKeys() has a chance to fetch it from the backend)
if [ -f "$BACKEND_DIR/.env" ]; then
    FIREBASE_KEY=$(grep "^FIREBASE_API_KEY=" "$BACKEND_DIR/.env" | head -1 | cut -d= -f2-)
    if [ -n "$FIREBASE_KEY" ] && ! grep -q "^FIREBASE_API_KEY=" "$APP_BUNDLE/Contents/Resources/.env"; then
        echo "FIREBASE_API_KEY=$FIREBASE_KEY" >> "$APP_BUNDLE/Contents/Resources/.env"
        substep "Bootstrapped FIREBASE_API_KEY from backend .env"
    fi
fi
# Bootstrap OMI_AUTH_URL — for local dev, point to the local Python auth service.
# For prod, set OMI_AUTH_URL explicitly in Backend-Rust/.env.
if ! grep -q "^OMI_AUTH_URL=" "$APP_BUNDLE/Contents/Resources/.env"; then
    AUTH_URL=""
    if [ -f "$BACKEND_DIR/.env" ]; then
        AUTH_URL=$(grep "^OMI_AUTH_URL=" "$BACKEND_DIR/.env" | head -1 | cut -d= -f2-)
    fi
    if [ -z "$AUTH_URL" ]; then
        # Default to local Python auth service
        AUTH_URL="http://localhost:${AUTH_PORT}/"
        substep "OMI_AUTH_URL not set — defaulting to local auth service: $AUTH_URL"
    fi
    echo "OMI_AUTH_URL=$AUTH_URL" >> "$APP_BUNDLE/Contents/Resources/.env"
    substep "Set OMI_AUTH_URL=$AUTH_URL"
fi

substep "Copying app icon"
cp -f omi_icon.icns "$APP_BUNDLE/Contents/Resources/OmiIcon.icns" 2>/dev/null || true

substep "Creating PkgInfo"
echo -n "APPL????" > "$APP_BUNDLE/Contents/PkgInfo"

# Embed provisioning profile (required for Sign In with Apple entitlement)
# Use dev profile for dev builds, production profile for release builds
if [ -f "Desktop/embedded-dev.provisionprofile" ]; then
    substep "Copying dev provisioning profile"
    cp "Desktop/embedded-dev.provisionprofile" "$APP_BUNDLE/Contents/embedded.provisionprofile"
elif [ -f "Desktop/embedded.provisionprofile" ]; then
    substep "Copying provisioning profile"
    cp "Desktop/embedded.provisionprofile" "$APP_BUNDLE/Contents/embedded.provisionprofile"
fi

auth_debug "BEFORE signing: $(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"

step "Removing extended attributes (xattr -cr)..."
xattr -cr "$APP_BUNDLE"

step "Signing app with hardened runtime..."
# Auto-detect a stable signing identity so TCC permissions persist across rebuilds.
# Ad-hoc signing (--sign -) generates a new CDHash each build, causing macOS to
# reset Screen Recording, Accessibility, and Notification permissions every time.
if [ -z "$SIGN_IDENTITY" ]; then
    # For dev builds: prefer Apple Development (matches Mac Development provisioning profile,
    # required for native Sign In with Apple). Fall back to Developer ID if unavailable.
    SIGN_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | sed 's/.*"\(.*\)"/\1/')
    if [ -z "$SIGN_IDENTITY" ]; then
        SIGN_IDENTITY=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | sed 's/.*"\(.*\)"/\1/')
    fi
fi

if [ -n "$SIGN_IDENTITY" ]; then
    substep "Using identity: $SIGN_IDENTITY"
    if [ -d "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework" ]; then
        substep "Signing Sparkle framework"
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
    fi
    if [ -d "$APP_BUNDLE/Contents/Frameworks/CSSwiftProtobuf.framework" ]; then
        substep "Signing CSSwiftProtobuf framework"
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/Frameworks/CSSwiftProtobuf.framework"
    fi
    if [ -d "$APP_BUNDLE/Contents/Frameworks/HeapSwiftCore.framework" ]; then
        substep "Signing HeapSwiftCore framework"
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/Frameworks/HeapSwiftCore.framework"
    fi
    # Sign the bundled node binary with developer identity + Node.entitlements
    # (macOS requires executables inside app bundles to be properly signed)
    NODE_BIN="$APP_BUNDLE/Contents/Resources/Omi Computer_Omi Computer.bundle/node"
    if [ -f "$NODE_BIN" ]; then
        substep "Signing bundled node binary"
        codesign --force --options runtime --entitlements Desktop/Node.entitlements --sign "$SIGN_IDENTITY" "$NODE_BIN"
    fi

    # If local signing identity doesn't match embedded profile team, macOS rejects
    # restricted entitlements (notably com.apple.developer.applesignin) and launch
    # fails with RBS/launchd spawn errors. Fallback to a local dev entitlements set.
    EFFECTIVE_ENTITLEMENTS="Desktop/Omi.entitlements"
    PROFILE_PATH="$APP_BUNDLE/Contents/embedded.provisionprofile"
    IDENTITY_TEAM_ID=$(echo "$SIGN_IDENTITY" | sed -n 's/.*(\([A-Z0-9]*\)).*/\1/p')
    PROFILE_TEAM_ID=""
    if [ -f "$PROFILE_PATH" ]; then
        PROFILE_TEAM_ID=$(security cms -D -i "$PROFILE_PATH" > /tmp/omi-dev-profile.plist 2>/dev/null && \
            /usr/libexec/PlistBuddy -c "Print :TeamIdentifier:0" /tmp/omi-dev-profile.plist 2>/dev/null || true)
    fi
    if [ -n "$PROFILE_TEAM_ID" ] && [ "$PROFILE_TEAM_ID" != "$IDENTITY_TEAM_ID" ]; then
        substep "Profile team ($PROFILE_TEAM_ID) != identity team ($IDENTITY_TEAM_ID); using local entitlements fallback"
        cp Desktop/Omi.entitlements /tmp/omi-local-dev.entitlements
        /usr/libexec/PlistBuddy -c "Delete :com.apple.developer.applesignin" /tmp/omi-local-dev.entitlements 2>/dev/null || true
        rm -f "$PROFILE_PATH"
        EFFECTIVE_ENTITLEMENTS="/tmp/omi-local-dev.entitlements"
    fi
    substep "Signing app bundle"
    codesign --force --options runtime --entitlements "$EFFECTIVE_ENTITLEMENTS" --sign "$SIGN_IDENTITY" "$APP_BUNDLE"
else
    echo ""
    echo "ERROR: No signing identity found. Ad-hoc signing causes macOS to reset"
    echo "       Screen Recording permissions for ALL Omi apps (including prod/beta)."
    echo ""
    echo "  Fix: Install an Apple Development certificate in Keychain Access,"
    echo "       or set OMI_SIGN_IDENTITY to a valid identity:"
    echo "       OMI_SIGN_IDENTITY=\"Apple Development: you@example.com\" ./run.sh"
    echo ""
    exit 1
fi

step "Removing quarantine attributes..."
xattr -cr "$APP_BUNDLE"

step "Installing to /Applications/..."
# Install to /Applications/ so "Quit & Reopen" (after granting screen recording
# permission) launches the correct binary instead of a stale copy elsewhere.
ditto "$APP_BUNDLE" "$APP_PATH"
substep "Installed to $APP_PATH"

step "Clearing stale LaunchServices registration..."
# Unregister first to clear any launch-disabled flag from stale entries,
# then let `open` re-register the app fresh. Without this, notifications
# fail with "Notifications are not allowed for this application" because
# the launch-disabled flag prevents notification center registration.
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
$LSREGISTER -u "$APP_BUNDLE" 2>/dev/null || true
$LSREGISTER -u "$APP_PATH" 2>/dev/null || true
# Purge stale registrations from old DMG staging dirs and unmounted volumes
# These create ghost entries that can cause notification icons to show a
# generic folder instead of the app icon
for stale in /private/tmp/omi-dmg-staging-*/Omi\ Beta.app; do
    [ -d "$stale" ] || $LSREGISTER -u "$stale" 2>/dev/null || true
done
# Register the /Applications/ copy as the canonical bundle for this bundle ID
$LSREGISTER -f "$APP_PATH" 2>/dev/null || true

step "Starting app..."

# Print summary
NOW=$(date +%s.%N)
TOTAL_TIME=$(echo "$NOW - $SCRIPT_START_TIME" | bc)
printf "  └─ done (%.2fs)\n" "$(echo "$NOW - $STEP_START_TIME" | bc)"
echo ""
echo "=== Services Running (total: ${TOTAL_TIME%.*}s) ==="
echo "Backend:  http://localhost:$BACKEND_PORT (PID: $BACKEND_PID)"
echo "Auth:     http://localhost:$AUTH_PORT (PID: ${AUTH_PID:-none})"
echo "Tunnel:   $TUNNEL_URL (PID: $TUNNEL_PID)"
echo "App:      $APP_PATH (installed from $APP_BUNDLE)"
if [ "${#AUTOMATION_ARGS[@]}" -gt 0 ]; then
    echo "Automation bridge: http://127.0.0.1:${AUTOMATION_PORT}"
fi
echo "Using backend: $TUNNEL_URL"
echo "========================================"
echo ""

auth_debug "BEFORE launch: $(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"
if [ "${#AUTOMATION_ARGS[@]}" -gt 0 ]; then
    open "$APP_PATH" --args "${AUTOMATION_ARGS[@]}" || "$APP_PATH/Contents/MacOS/$BINARY_NAME" "${AUTOMATION_ARGS[@]}" &
else
    open "$APP_PATH" || "$APP_PATH/Contents/MacOS/$BINARY_NAME" &
fi

# Wait for backend process (keeps script running and shows logs)
echo "Press Ctrl+C to stop all services..."
wait "$BACKEND_PID"
