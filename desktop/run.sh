#!/bin/bash
set -e

# ─── Mode parsing ─────────────────────────────────────────────────────
MODE="dev"       # dev (default), release, build-only, yolo
BUILD_CONFIG="debug"
START_SERVICES=true
SIGN_APP=true
INSTALL_APP=true
LAUNCH_APP=true

for arg in "$@"; do
    case "$arg" in
        --help|-h)
            cat <<'USAGE'
Usage: ./run.sh [mode] [options]

Modes:
  (default)       Full dev: debug build + backend + auth + tunnel + sign + launch
  --release       Release build only, no services, no signing (for CI/Codemagic)
  --build-only    Debug build + sign + install, no services, no launch
  --yolo          Use production backend, no local services

Options (via environment variables):
  OMI_SKIP_BACKEND=1      Skip starting Rust backend
  OMI_SKIP_AUTH=1          Skip starting Python auth service
  OMI_SKIP_TUNNEL=1        Skip Cloudflare tunnel
  AUTH_PORT=10200           Auth service port (default: 10200)
  PORT=10201                Rust backend port (default: 10201)
  OMI_APP_NAME="Omi Dev"   App name (default: "Omi Dev", release: "omi")
  OMI_PYTHON_API_URL="..."  Python backend URL (default: https://api.omi.me)
  OMI_SIGN_IDENTITY="..."  Code signing identity (auto-detected)
  OMI_ENABLE_LOCAL_AUTOMATION=1  Enable agent-swift automation bridge

Examples:
  ./run.sh                                     # Full local dev
  ./run.sh --yolo                              # Quick start with prod backend
  ./run.sh --build-only                        # Build + sign, no services
  ./run.sh --release                           # Release build (replaces build.sh)
  OMI_APP_NAME="fix-bug" ./run.sh              # Named test bundle
  OMI_APP_NAME="fix-bug" ./run.sh --build-only # Named bundle, no services
USAGE
            exit 0
            ;;
        --release)
            MODE="release"
            BUILD_CONFIG="release"
            START_SERVICES=false
            SIGN_APP=false
            INSTALL_APP=false
            LAUNCH_APP=false
            ;;
        --build-only)
            MODE="build-only"
            START_SERVICES=false
            LAUNCH_APP=false
            ;;
        --yolo)
            MODE="yolo"
            export OMI_SKIP_BACKEND=1
            export OMI_SKIP_AUTH=1
            export OMI_SKIP_TUNNEL=1
            export OMI_API_URL="https://desktop-backend-hhibjajaja-uc.a.run.app"
            export OMI_PYTHON_API_URL="https://api.omi.me"
            export OMI_AUTH_URL="https://omi-desktop-auth-208440318997.us-central1.run.app/"
            export FIREBASE_API_KEY="AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8"
            ;;
    esac
done

# Clear system OPENAI_API_KEY so .env takes precedence
unset OPENAI_API_KEY

# Use Xcode's default toolchain to match the SDK version
unset TOOLCHAINS

# ─── Timing utilities ─────────────────────────────────────────────────
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

# ─── App configuration ────────────────────────────────────────────────
BINARY_NAME="Omi Computer"  # Package.swift target — binary paths, pkill, CFBundleExecutable

if [ "$MODE" = "release" ]; then
    APP_NAME="${OMI_APP_NAME:-omi}"
    DEFAULT_BUNDLE_ID="com.omi.computer-macos"
else
    APP_NAME="${OMI_APP_NAME:-Omi Dev}"
fi

slugify_identifier() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g'
}

if [ "$MODE" = "release" ]; then
    EXPECTED_BUNDLE_ID="${DEFAULT_BUNDLE_ID}"
    EXPECTED_URL_SCHEME="omi-computer"
elif [ "$APP_NAME" = "Omi Dev" ]; then
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

# ─── Backend configuration ────────────────────────────────────────────
BACKEND_DIR="$(cd "$(dirname "$0")/Backend-Rust" && pwd)"
AUTH_DIR="$(cd "$(dirname "$0")/Auth-Python" && pwd)"
BACKEND_PID=""
AUTH_PID=""
TUNNEL_PID=""
TUNNEL_URL="${TUNNEL_URL:-}"
AUTH_PORT="${AUTH_PORT:-10200}"

cleanup() {
    for pid_var in TUNNEL_PID AUTH_PID BACKEND_PID; do
        eval "pid=\$$pid_var"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
}
trap cleanup EXIT

AUTH_DEBUG_LOG=/private/tmp/auth-debug.log
rm -f $AUTH_DEBUG_LOG
auth_debug() { echo "[AUTH DEBUG][$(date +%H:%M:%S)] $1" >> $AUTH_DEBUG_LOG; }
touch $AUTH_DEBUG_LOG

# ─── Kill existing instances (dev/yolo only) ──────────────────────────
if [ "$START_SERVICES" = true ] || [ "$INSTALL_APP" = true ]; then
    step "Killing existing instances..."
    auth_debug "BEFORE pkill: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"
    auth_debug "BEFORE pkill: ALL_KEYS=$(defaults read "$BUNDLE_ID" 2>&1 | grep -E 'auth_|hasCompleted|hasLaunched|currentTier|userShow' || true)"
    pkill -f "$APP_NAME.app" 2>/dev/null || true
    pgrep -f "omi-desktop-backend" 2>/dev/null | while read pid; do
        substep "Killing old backend (PID: $pid)"
        kill -9 "$pid" 2>/dev/null || true
    done
    sleep 0.5
    auth_debug "AFTER pkill: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"

    rm -f /tmp/omi-dev.log 2>/dev/null || true

    step "Cleaning up conflicting app bundles..."
    rm -rf "$BUILD_DIR/Omi Computer.app" 2>/dev/null
    rm -rf "$APP_BUNDLE" 2>/dev/null
    for app in "$APP_PATH" "$HOME/Desktop/$APP_NAME.app" "$HOME/Downloads/$APP_NAME.app" \
               "$(dirname "$0")/../app/build/macos/Build/Products/Debug/Omi.app" \
               "$(dirname "$0")/../app/build/macos/Build/Products/Release/Omi.app"; do
        if [ -d "$app" ]; then
            substep "Removing: $app"
            rm -rf "$app"
        fi
    done
    find "$(dirname "$0")/../app/build" -name "$APP_NAME.app" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$HOME" -maxdepth 4 -name "$APP_NAME.app" -type d -not -path "$APP_BUNDLE" -not -path "$APP_PATH" 2>/dev/null | while read stale; do
        substep "Removing stale clone: $stale"
        rm -rf "$stale"
    done
else
    # Release mode: just clean the target bundle
    rm -rf "$APP_BUNDLE"
    mkdir -p "$BUILD_DIR"
fi

# ─── Cloudflare tunnel (dev only) ─────────────────────────────────────
if [ "$START_SERVICES" = true ] && [ "${OMI_SKIP_TUNNEL:-0}" != "1" ]; then
    step "Starting Cloudflare quick tunnel..."
    if command -v cloudflared >/dev/null 2>&1; then
        TUNNEL_LOG=$(mktemp /tmp/cloudflared-XXXXXX.log)
        cloudflared tunnel --url http://localhost:${BACKEND_PORT:-8080} > "$TUNNEL_LOG" 2>&1 &
        TUNNEL_PID=$!
        for i in {1..20}; do
            TUNNEL_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1)
            if [ -n "$TUNNEL_URL" ]; then break; fi
            sleep 0.5
        done
        if [ -n "$TUNNEL_URL" ]; then
            rm -f "$TUNNEL_LOG"
            substep "Tunnel URL: $TUNNEL_URL"
        else
            substep "Warning: Could not capture tunnel URL (see $TUNNEL_LOG)"
        fi
    else
        substep "cloudflared not found — skipping tunnel"
    fi
fi

# ─── Load .env and credentials ────────────────────────────────────────
cd "$BACKEND_DIR"

if [ ! -f ".env" ] && [ -f "../backend/.env" ]; then
    cp "../backend/.env" ".env"
elif [ ! -f ".env" ] && [ -f "../Backend/.env" ]; then
    cp "../Backend/.env" ".env"
fi
if [ ! -f ".env" ] && [ "$MODE" != "yolo" ] && [ "$MODE" != "release" ]; then
    echo ""
    echo "=== First-time setup ==="
    echo "No .env file found at $BACKEND_DIR/.env"
    echo ""
    echo "Quick start:"
    echo "  1. cp .env.example .env"
    echo "  2. Fill in required values (see comments in .env.example)"
    echo "  3. Place google-credentials.json in $BACKEND_DIR/"
    echo ""
    echo "Or just use the production backend (no setup needed):"
    echo "  ./run.sh --yolo"
    echo "==========================="
    exit 1
fi

if [ ! -f "google-credentials.json" ] && [ -f "../backend/google-credentials.json" ]; then
    ln -sf "../backend/google-credentials.json" "google-credentials.json"
elif [ ! -f "google-credentials.json" ] && [ -f "../Backend/google-credentials.json" ]; then
    ln -sf "../Backend/google-credentials.json" "google-credentials.json"
fi

if [ -f "$BACKEND_DIR/.env" ]; then
    set -a; source "$BACKEND_DIR/.env"; set +a
fi

BACKEND_PORT="${PORT:-10201}"
export PORT="$BACKEND_PORT"

CREDS_PATH="$BACKEND_DIR/google-credentials.json"
if [ "${OMI_SKIP_BACKEND:-0}" != "1" ] && [ "$START_SERVICES" = true ] && [ ! -f "$CREDS_PATH" ]; then
    echo "ERROR: Missing credentials file: $CREDS_PATH"
    echo "  Option A: cp /path/to/google-credentials.json $CREDS_PATH"
    echo "  Option B: OMI_SKIP_BACKEND=1 ./run.sh"
    exit 1
fi
if [ -f "$CREDS_PATH" ]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$CREDS_PATH"
fi

if [ -z "$FIREBASE_PROJECT_ID" ] && [ "${OMI_SKIP_BACKEND:-0}" != "1" ] && [ "$START_SERVICES" = true ]; then
    echo "ERROR: FIREBASE_PROJECT_ID is not set. Add to $BACKEND_DIR/.env"
    exit 1
fi
if [ -n "$FIREBASE_AUTH_PROJECT_ID" ]; then
    substep "Auth project: tokens validated against $FIREBASE_AUTH_PROJECT_ID, Firestore on $FIREBASE_PROJECT_ID"
fi
if [ "$START_SERVICES" = true ]; then
    substep "Firebase project: $FIREBASE_PROJECT_ID | Backend port: $BACKEND_PORT | Auth port: $AUTH_PORT"
fi
cd - > /dev/null

# ─── Start Rust backend (dev only) ────────────────────────────────────
if [ "$START_SERVICES" = true ] && [ "${OMI_SKIP_BACKEND:-0}" != "1" ]; then
    step "Starting Rust backend..."
    cd "$BACKEND_DIR"
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
            echo "ERROR: Backend failed to start. Check $BACKEND_DIR/.env and credentials."
            exit 1
        fi
        sleep 0.5
    done
fi

# ─── Start Python auth service (dev only) ─────────────────────────────
if [ "$START_SERVICES" = true ] && [ "${OMI_SKIP_AUTH:-0}" != "1" ]; then
    step "Starting Python auth service (port $AUTH_PORT)..."
    if [ -d "$AUTH_DIR" ]; then
        if [ ! -d "$AUTH_DIR/.venv" ]; then
            substep "Creating virtualenv..."
            python3 -m venv "$AUTH_DIR/.venv"
            "$AUTH_DIR/.venv/bin/pip" install -q -r "$AUTH_DIR/requirements.txt"
        fi
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
        substep "Auth-Python/ not found — skipping"
    fi
fi

# ─── Wait for other SwiftPM instances ─────────────────────────────────
SWIFTPM_PID=$(pgrep -f "swiftpm-workspace-state|swift-build|swift-package" 2>/dev/null | head -1)
if [ -n "$SWIFTPM_PID" ]; then
    step "Waiting for other SwiftPM instance (PID: $SWIFTPM_PID) to finish..."
    while kill -0 "$SWIFTPM_PID" 2>/dev/null; do sleep 1; done
fi

# ─── Build acp-bridge ─────────────────────────────────────────────────
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

# ─── Schema docs check ────────────────────────────────────────────────
step "Checking schema docs..."
if [ -f scripts/check_schema_docs.sh ]; then
    bash scripts/check_schema_docs.sh || substep "Schema docs check failed (non-fatal)"
fi

# ─── Ensure bundled Node.js exists (release only downloads if missing) ─
NODE_RESOURCE="Desktop/Sources/Resources/node"
if [ ! -x "$NODE_RESOURCE" ]; then
    step "Downloading Node.js binary..."
    NODE_VERSION="v22.14.0"
    ARCH=$(uname -m)
    NODE_ARCH=$( [ "$ARCH" = "arm64" ] && echo "arm64" || echo "x64" )
    NODE_TEMP_DIR="/tmp/node-dev-$$"
    mkdir -p "$NODE_TEMP_DIR"
    curl -L -o "$NODE_TEMP_DIR/node.tar.gz" \
        "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-darwin-$NODE_ARCH.tar.gz"
    tar -xzf "$NODE_TEMP_DIR/node.tar.gz" -C "$NODE_TEMP_DIR" --strip-components=1 --include="*/bin/node" 2>/dev/null || \
    tar -xzf "$NODE_TEMP_DIR/node.tar.gz" -C "$NODE_TEMP_DIR"
    NODE_BIN=$(find "$NODE_TEMP_DIR" -name "node" -type f | head -1)
    if [ -n "$NODE_BIN" ]; then
        cp "$NODE_BIN" "$NODE_RESOURCE"
        chmod +x "$NODE_RESOURCE"
        substep "Downloaded Node.js $NODE_VERSION ($NODE_ARCH)"
    else
        echo "Warning: Could not extract Node.js binary."
    fi
    rm -rf "$NODE_TEMP_DIR"
fi

# ─── Build Swift app ──────────────────────────────────────────────────
step "Building Swift app (swift build -c $BUILD_CONFIG)..."
if [ "$BUILD_CONFIG" = "release" ]; then
    swift build -c release --package-path Desktop
    BINARY_PATH=$(swift build -c release --package-path Desktop --show-bin-path)/"$BINARY_NAME"
    SWIFT_BUILD_DIR=$(swift build -c release --package-path Desktop --show-bin-path)
else
    xcrun swift build -c debug --package-path Desktop
    BINARY_PATH="Desktop/.build/debug/$BINARY_NAME"
    SWIFT_BUILD_DIR="Desktop/.build/arm64-apple-macosx/debug"
fi

auth_debug "AFTER swift build: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"

if [ ! -f "$BINARY_PATH" ]; then
    echo "ERROR: Binary not found at $BINARY_PATH"
    exit 1
fi

# ─── Create app bundle ────────────────────────────────────────────────
step "Creating app bundle..."
substep "Creating directories"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"
mkdir -p "$APP_BUNDLE/Contents/Frameworks"

substep "Copying binary ($(du -h "$BINARY_PATH" 2>/dev/null | cut -f1))"
cp -f "$BINARY_PATH" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME"

substep "Adding rpath for Frameworks"
install_name_tool -add_rpath "@executable_path/../Frameworks" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME" 2>/dev/null || true

# Frameworks
for fw_name in Sparkle HeapSwiftCore CSSwiftProtobuf; do
    case "$fw_name" in
        Sparkle)
            FW_PATH="$SWIFT_BUILD_DIR/Sparkle.framework"
            # release mode: look in parent dir
            [ ! -d "$FW_PATH" ] && FW_PATH="$SWIFT_BUILD_DIR/../Sparkle.framework"
            ;;
        HeapSwiftCore)
            FW_PATH="Desktop/.build/artifacts/heap-swift-core-sdk/HeapSwiftCore/HeapSwiftCore.xcframework/macos-arm64_x86_64/HeapSwiftCore.framework"
            ;;
        CSSwiftProtobuf)
            FW_PATH="Desktop/.build/artifacts/csswiftprotobuf/CSSwiftProtobuf/CSSwiftProtobuf.xcframework/macos-arm64_x86_64/CSSwiftProtobuf.framework"
            ;;
    esac
    if [ -d "$FW_PATH" ]; then
        substep "Copying $fw_name framework"
        rm -rf "$APP_BUNDLE/Contents/Frameworks/$fw_name.framework"
        cp -R "$FW_PATH" "$APP_BUNDLE/Contents/Frameworks/"
    fi
done

# Info.plist
substep "Copying Info.plist"
cp -f Desktop/Info.plist "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $BINARY_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleURLTypes:0:CFBundleURLSchemes:0 $URL_SCHEME" "$APP_BUNDLE/Contents/Info.plist"

auth_debug "AFTER plist edits: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"

# GoogleService-Info.plist
substep "Copying GoogleService-Info.plist"
if [ -f "Desktop/Sources/GoogleService-Info-Dev.plist" ] && [ "$MODE" != "release" ]; then
    cp -f Desktop/Sources/GoogleService-Info-Dev.plist "$APP_BUNDLE/Contents/Resources/GoogleService-Info.plist"
else
    cp -f Desktop/Sources/GoogleService-Info.plist "$APP_BUNDLE/Contents/Resources/"
fi
/usr/libexec/PlistBuddy -c "Set :BUNDLE_ID $BUNDLE_ID" "$APP_BUNDLE/Contents/Resources/GoogleService-Info.plist" 2>/dev/null || true

# Resource bundle
RESOURCE_BUNDLE_NAME="Omi Computer_Omi Computer.bundle"
RESOURCE_BUNDLE_PATH="$SWIFT_BUILD_DIR/$RESOURCE_BUNDLE_NAME"
if [ -d "$RESOURCE_BUNDLE_PATH" ]; then
    substep "Copying resource bundle ($(du -sh "$RESOURCE_BUNDLE_PATH" 2>/dev/null | cut -f1))"
    cp -Rf "$RESOURCE_BUNDLE_PATH" "$APP_BUNDLE/Contents/Resources/"
fi

# acp-bridge
substep "Copying acp-bridge"
if [ -d "$ACP_BRIDGE_DIR/dist" ]; then
    mkdir -p "$APP_BUNDLE/Contents/Resources/acp-bridge"
    cp -Rf "$ACP_BRIDGE_DIR/dist" "$APP_BUNDLE/Contents/Resources/acp-bridge/"
    cp -f "$ACP_BRIDGE_DIR/package.json" "$APP_BUNDLE/Contents/Resources/acp-bridge/"
    cp -RPf "$ACP_BRIDGE_DIR/node_modules" "$APP_BUNDLE/Contents/Resources/acp-bridge/"
fi

# .env
substep "Copying .env.app"
if [ -f ".env.app.dev" ] && [ "$MODE" != "release" ]; then
    cp -f .env.app.dev "$APP_BUNDLE/Contents/Resources/.env"
elif [ -f ".env.app" ]; then
    cp -f .env.app "$APP_BUNDLE/Contents/Resources/.env"
else
    touch "$APP_BUNDLE/Contents/Resources/.env"
fi

if [ "$MODE" != "release" ]; then
    # Set OMI_API_URL: tunnel URL > env var > local backend
    if [ -n "$TUNNEL_URL" ]; then
        EFFECTIVE_API_URL="$TUNNEL_URL"
    elif [ -n "$OMI_API_URL" ]; then
        EFFECTIVE_API_URL="$OMI_API_URL"
    else
        EFFECTIVE_API_URL="http://localhost:$BACKEND_PORT"
    fi
    if grep -q "^OMI_API_URL=" "$APP_BUNDLE/Contents/Resources/.env"; then
        sed -i '' "s|^OMI_API_URL=.*|OMI_API_URL=$EFFECTIVE_API_URL|" "$APP_BUNDLE/Contents/Resources/.env"
    else
        echo "OMI_API_URL=$EFFECTIVE_API_URL" >> "$APP_BUNDLE/Contents/Resources/.env"
    fi
    substep "OMI_API_URL=$EFFECTIVE_API_URL"

    # Bootstrap FIREBASE_API_KEY
    if ! grep -q "^FIREBASE_API_KEY=" "$APP_BUNDLE/Contents/Resources/.env"; then
        FIREBASE_KEY="${FIREBASE_API_KEY:-}"
        if [ -z "$FIREBASE_KEY" ] && [ -f "$BACKEND_DIR/.env" ]; then
            FIREBASE_KEY=$(grep "^FIREBASE_API_KEY=" "$BACKEND_DIR/.env" | head -1 | cut -d= -f2-)
        fi
        if [ -n "$FIREBASE_KEY" ]; then
            echo "FIREBASE_API_KEY=$FIREBASE_KEY" >> "$APP_BUNDLE/Contents/Resources/.env"
            substep "Bootstrapped FIREBASE_API_KEY"
        fi
    fi

    # Bootstrap OMI_AUTH_URL
    if ! grep -q "^OMI_AUTH_URL=" "$APP_BUNDLE/Contents/Resources/.env"; then
        AUTH_URL="${OMI_AUTH_URL:-}"
        if [ -z "$AUTH_URL" ] && [ -f "$BACKEND_DIR/.env" ]; then
            AUTH_URL=$(grep "^OMI_AUTH_URL=" "$BACKEND_DIR/.env" | head -1 | cut -d= -f2-)
        fi
        if [ -z "$AUTH_URL" ]; then
            AUTH_URL="http://localhost:${AUTH_PORT}/"
            substep "OMI_AUTH_URL not set — defaulting to local auth: $AUTH_URL"
        fi
        echo "OMI_AUTH_URL=$AUTH_URL" >> "$APP_BUNDLE/Contents/Resources/.env"
        substep "Set OMI_AUTH_URL=$AUTH_URL"
    fi

    # Bootstrap OMI_PYTHON_API_URL
    if ! grep -q "^OMI_PYTHON_API_URL=" "$APP_BUNDLE/Contents/Resources/.env"; then
        PYTHON_API_URL="${OMI_PYTHON_API_URL:-}"
        if [ -z "$PYTHON_API_URL" ] && [ -f "$BACKEND_DIR/.env" ]; then
            PYTHON_API_URL=$(grep "^OMI_PYTHON_API_URL=" "$BACKEND_DIR/.env" | head -1 | cut -d= -f2-)
        fi
        if [ -z "$PYTHON_API_URL" ]; then
            PYTHON_API_URL="https://api.omi.me"
            substep "OMI_PYTHON_API_URL not set — defaulting to production: $PYTHON_API_URL"
        fi
        echo "OMI_PYTHON_API_URL=$PYTHON_API_URL" >> "$APP_BUNDLE/Contents/Resources/.env"
        substep "Set OMI_PYTHON_API_URL=$PYTHON_API_URL"
    fi
fi

# App icon + PkgInfo
substep "Copying app icon"
cp -f omi_icon.icns "$APP_BUNDLE/Contents/Resources/OmiIcon.icns" 2>/dev/null || true

substep "Creating PkgInfo"
echo -n "APPL????" > "$APP_BUNDLE/Contents/PkgInfo"

# Provisioning profile (dev builds only, and only for "Omi Dev")
if [ "$MODE" != "release" ] && [ "$APP_NAME" = "Omi Dev" ]; then
    if [ -f "Desktop/embedded-dev.provisionprofile" ]; then
        substep "Copying dev provisioning profile"
        cp "Desktop/embedded-dev.provisionprofile" "$APP_BUNDLE/Contents/embedded.provisionprofile"
    elif [ -f "Desktop/embedded.provisionprofile" ]; then
        substep "Copying provisioning profile"
        cp "Desktop/embedded.provisionprofile" "$APP_BUNDLE/Contents/embedded.provisionprofile"
    fi
elif [ "$MODE" != "release" ] && [ "$APP_NAME" != "Omi Dev" ]; then
    substep "Named bundle ($BUNDLE_ID) — skipping provisioning profile"
fi

# ─── Release mode: done ───────────────────────────────────────────────
if [ "$MODE" = "release" ]; then
    NOW=$(date +%s.%N)
    TOTAL_TIME=$(echo "$NOW - $SCRIPT_START_TIME" | bc)
    printf "  └─ done (%.2fs)\n" "$(echo "$NOW - $STEP_START_TIME" | bc)"
    echo ""
    echo "Build complete: $APP_BUNDLE (${TOTAL_TIME%.*}s)"
    echo ""
    echo "To run:  open $APP_BUNDLE"
    echo "To install:  cp -r $APP_BUNDLE /Applications/"
    exit 0
fi

# ─── Code signing ─────────────────────────────────────────────────────
auth_debug "BEFORE signing: $(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"

step "Removing extended attributes (xattr -cr)..."
xattr -cr "$APP_BUNDLE"

step "Signing app with hardened runtime..."
if [ -z "$SIGN_IDENTITY" ]; then
    SIGN_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | sed 's/.*"\(.*\)"/\1/')
    if [ -z "$SIGN_IDENTITY" ]; then
        SIGN_IDENTITY=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | sed 's/.*"\(.*\)"/\1/')
    fi
fi

if [ -n "$SIGN_IDENTITY" ]; then
    substep "Using identity: $SIGN_IDENTITY"

    # Sign frameworks
    for fw in Sparkle CSSwiftProtobuf HeapSwiftCore; do
        if [ -d "$APP_BUNDLE/Contents/Frameworks/$fw.framework" ]; then
            substep "Signing $fw framework"
            codesign --force --options runtime --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/Frameworks/$fw.framework"
        fi
    done

    # Sign bundled node binary
    NODE_BIN="$APP_BUNDLE/Contents/Resources/Omi Computer_Omi Computer.bundle/node"
    if [ -f "$NODE_BIN" ]; then
        substep "Signing bundled node binary"
        codesign --force --options runtime --entitlements Desktop/Node.entitlements --sign "$SIGN_IDENTITY" "$NODE_BIN"
    fi

    # Entitlements: named bundles and mismatched profiles strip applesignin
    EFFECTIVE_ENTITLEMENTS="Desktop/Omi.entitlements"
    PROFILE_PATH="$APP_BUNDLE/Contents/embedded.provisionprofile"

    if [ "$APP_NAME" != "Omi Dev" ]; then
        substep "Named bundle — using local entitlements (no applesignin)"
        cp Desktop/Omi.entitlements /tmp/omi-local-dev.entitlements
        /usr/libexec/PlistBuddy -c "Delete :com.apple.developer.applesignin" /tmp/omi-local-dev.entitlements 2>/dev/null || true
        rm -f "$PROFILE_PATH"
        EFFECTIVE_ENTITLEMENTS="/tmp/omi-local-dev.entitlements"
    elif [ -f "$PROFILE_PATH" ]; then
        IDENTITY_TEAM_ID=$(echo "$SIGN_IDENTITY" | sed -n 's/.*(\([A-Z0-9]*\)).*/\1/p')
        PROFILE_TEAM_ID=$(security cms -D -i "$PROFILE_PATH" > /tmp/omi-dev-profile.plist 2>/dev/null && \
            /usr/libexec/PlistBuddy -c "Print :TeamIdentifier:0" /tmp/omi-dev-profile.plist 2>/dev/null || true)
        if [ -z "$PROFILE_TEAM_ID" ] || [ "$PROFILE_TEAM_ID" != "$IDENTITY_TEAM_ID" ]; then
            substep "Profile/identity team mismatch — stripping applesignin"
            cp Desktop/Omi.entitlements /tmp/omi-local-dev.entitlements
            /usr/libexec/PlistBuddy -c "Delete :com.apple.developer.applesignin" /tmp/omi-local-dev.entitlements 2>/dev/null || true
            rm -f "$PROFILE_PATH"
            EFFECTIVE_ENTITLEMENTS="/tmp/omi-local-dev.entitlements"
        fi
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

# ─── Install + launch ─────────────────────────────────────────────────
step "Removing quarantine attributes..."
xattr -cr "$APP_BUNDLE"

step "Installing to /Applications/..."
ditto "$APP_BUNDLE" "$APP_PATH"
substep "Installed to $APP_PATH"

step "Clearing stale LaunchServices registration..."
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
$LSREGISTER -u "$APP_BUNDLE" 2>/dev/null || true
$LSREGISTER -u "$APP_PATH" 2>/dev/null || true
for stale in /private/tmp/omi-dmg-staging-*/Omi\ Beta.app; do
    [ -d "$stale" ] || $LSREGISTER -u "$stale" 2>/dev/null || true
done
$LSREGISTER -f "$APP_PATH" 2>/dev/null || true

step "Starting app..."

NOW=$(date +%s.%N)
TOTAL_TIME=$(echo "$NOW - $SCRIPT_START_TIME" | bc)
printf "  └─ done (%.2fs)\n" "$(echo "$NOW - $STEP_START_TIME" | bc)"
echo ""
echo "=== Services Running (total: ${TOTAL_TIME%.*}s) ==="
if [ -n "$BACKEND_PID" ]; then
    echo "Backend:  http://localhost:$BACKEND_PORT (PID: $BACKEND_PID)"
else
    echo "Backend:  skipped"
fi
if [ -n "$AUTH_PID" ]; then
    echo "Auth:     http://localhost:$AUTH_PORT (PID: $AUTH_PID)"
else
    echo "Auth:     skipped"
fi
if [ -n "$TUNNEL_PID" ]; then
    echo "Tunnel:   $TUNNEL_URL (PID: $TUNNEL_PID)"
else
    echo "Tunnel:   skipped"
fi
echo "App:      $APP_PATH"
if [ -n "$EFFECTIVE_API_URL" ]; then
    echo "API URL:  $EFFECTIVE_API_URL"
fi
if [ "${#AUTOMATION_ARGS[@]}" -gt 0 ]; then
    echo "Automation bridge: http://127.0.0.1:${AUTOMATION_PORT}"
fi
echo "========================================"
echo ""

auth_debug "BEFORE launch: $(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"
if [ "${#AUTOMATION_ARGS[@]}" -gt 0 ]; then
    open "$APP_PATH" --args "${AUTOMATION_ARGS[@]}" || "$APP_PATH/Contents/MacOS/$BINARY_NAME" "${AUTOMATION_ARGS[@]}" &
else
    open "$APP_PATH" || "$APP_PATH/Contents/MacOS/$BINARY_NAME" &
fi

echo "Press Ctrl+C to stop all services..."
if [ -n "$BACKEND_PID" ]; then
    wait "$BACKEND_PID"
elif [ -n "$AUTH_PID" ]; then
    wait "$AUTH_PID"
else
    while true; do sleep 60; done
fi
