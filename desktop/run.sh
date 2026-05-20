#!/bin/bash
set -e

# Force C locale for numeric formatting so `printf %f` accepts the
# dot-decimal values produced by `bc` even when the user's shell runs in
# a non-English locale (e.g. de_DE.UTF-8 expects a comma separator).
export LC_NUMERIC=C

# ─── Help ──────────────────────────────────────────────────────────────
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    cat <<'USAGE'
Usage: ./run.sh [options]

Build and run the Omi Desktop dev app with local backend services.

Options (via environment variables):
  OMI_SKIP_BACKEND=1      Skip starting Rust backend (use remote backend via OMI_DESKTOP_API_URL)
  OMI_SKIP_TUNNEL=1        Skip Cloudflare tunnel (use OMI_DESKTOP_API_URL from .env directly)
  PORT=10201                Rust backend port (default: 10201, never use 8080)
  OMI_APP_NAME="Omi Dev"   App name (default: "Omi Dev")
  OMI_PYTHON_API_URL="..."  Python backend URL (subscriptions, payments, etc; default: https://api.omi.me)
  OMI_SIGN_IDENTITY="..."  Code signing identity (auto-detected if not set)
  OMI_ENABLE_LOCAL_AUTOMATION=1  Enable agent-swift automation bridge
  OMI_DESKTOP_BACKEND_MODE=local  Route MVP data flows to the local daemon
  OMI_LOCAL_DAEMON_SUPERVISE=1    In local mode, start desktop/local-backend if /health is unreachable
  OMI_LOCAL_DAEMON_URL="..."      Local daemon URL (default: http://127.0.0.1:8765)
  OMI_HYBRID_DIRECT_STT_ENABLED   Hybrid Apple Speech live transcription in local daemon (default 1 in configure_local_daemon_mode when unset)
  OMI_HYBRID_DIRECT_CHAT_ENABLED   Hybrid OpenAI-compatible chat + daemon-backed sessions/messages (default 1 in configure_local_daemon_mode when unset)
  OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED  Optional hybrid direct embeddings for vector search (default 0 in local bundle; local wiki search does not require embeddings)

Required files for cloud backend mode:
  Backend-Rust/.env         Environment variables (copy from ../.env.example)
  Backend-Rust/google-credentials.json  GCP service account key

Required tools:
  cargo, xcrun/swift, python3, npm, node, codesign, cloudflared (unless skipped)

Port allocation (avoid 8080 to prevent port conflicts):
  Backend default: 10201

Examples:
  ./run.sh                                  # Full local dev (backend + tunnel + app)
  OMI_SKIP_BACKEND=1 ./run.sh               # App only (backend running elsewhere)
  OMI_SKIP_TUNNEL=1 ./run.sh                # No Cloudflare tunnel (use direct URL)
  OMI_DESKTOP_BACKEND_MODE=local OMI_LOCAL_DAEMON_SUPERVISE=1 ./run.sh
                                            # Local daemon mode with dev supervisor
  ./run.sh --yolo                            # Quick start: use prod backend, no local services
USAGE
    exit 0
fi

# ─── YOLO mode: use prod backend, zero local setup ───────────────────
# WARNING: Temporary shortcut while desktop dev setup is being cleaned up.
# Will be removed once all desktop slop is fixed.
if [ "$1" = "--yolo" ]; then
    echo ""
    echo "=========================================="
    echo "  YOLO MODE — using production backend"
    echo "=========================================="
    echo ""
    echo "  WARNING: This connects directly to the prod Cloud Run backend."
    echo "  No local Rust backend, no local auth, no tunnel."
    echo "  This is a temporary shortcut — will be removed once"
    echo "  desktop dev setup friction is fully resolved."
    echo ""
    echo "=========================================="
    echo ""

    export OMI_SKIP_BACKEND=1
    export OMI_SKIP_TUNNEL=1
    export OMI_DESKTOP_API_URL="https://desktop-backend-hhibjajaja-uc.a.run.app"
    export OMI_PYTHON_API_URL="https://api.omi.me"
    export FIREBASE_API_KEY="AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8"
fi

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
IS_NAMED_BUNDLE=false
[ -n "${OMI_APP_NAME:-}" ] && IS_NAMED_BUNDLE=true

slugify_identifier() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g'
}

if [ "$IS_NAMED_BUNDLE" = false ]; then
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
LOCAL_DAEMON_DIR="$(cd "$(dirname "$0")/local-backend" && pwd)"
BACKEND_PID=""
LOCAL_DAEMON_PID=""
TUNNEL_PID=""
TUNNEL_URL="${TUNNEL_URL:-}"

is_local_daemon_mode() {
    local mode
    mode="$(printf '%s' "${OMI_DESKTOP_BACKEND_MODE:-${OMI_BACKEND_MODE:-}}" | tr '[:upper:]' '[:lower:]')"
    case "$mode" in
        local|local-daemon|local_daemon|daemon) return 0 ;;
        *) return 1 ;;
    esac
}

normalize_local_daemon_url() {
    local url="${OMI_LOCAL_DAEMON_URL:-http://127.0.0.1:8765}"
    url="${url%/}"
    export OMI_LOCAL_DAEMON_URL="$url"
}

configure_local_daemon_mode() {
    if ! is_local_daemon_mode; then
        return
    fi

    normalize_local_daemon_url
    export OMI_SKIP_BACKEND="${OMI_SKIP_BACKEND:-1}"
    export OMI_SKIP_TUNNEL="${OMI_SKIP_TUNNEL:-1}"

    if [ -z "${OMI_LOCAL_BACKEND_PORT:-}" ]; then
        OMI_LOCAL_BACKEND_PORT="$(python3 - "$OMI_LOCAL_DAEMON_URL" <<'PY'
from urllib.parse import urlparse
import sys

parsed = urlparse(sys.argv[1])
print(parsed.port or 8765)
PY
)"
        export OMI_LOCAL_BACKEND_PORT
    fi
    export OMI_LOCAL_BACKEND_HOST="${OMI_LOCAL_BACKEND_HOST:-127.0.0.1}"
    # Default hybrid on-device STT for local daemon dev (Apple Speech). Set OMI_HYBRID_DIRECT_STT_ENABLED=0 to disable.
    if [ -z "${OMI_HYBRID_DIRECT_STT_ENABLED+x}" ]; then
        export OMI_HYBRID_DIRECT_STT_ENABLED=1
    fi
    # Hybrid direct chat capability for GUI launches (requires chat_provider in daemon settings).
    if [ -z "${OMI_HYBRID_DIRECT_CHAT_ENABLED+x}" ]; then
        export OMI_HYBRID_DIRECT_CHAT_ENABLED=1
    fi
    # Optional direct embeddings for vector search. Default off: this local profile uses local wiki/FTS memory search.
    if [ -z "${OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED+x}" ]; then
        export OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED=0
    fi
}

local_daemon_health_ok() {
    curl -fsS "${OMI_LOCAL_DAEMON_URL}/health" >/dev/null 2>&1
}

configure_local_daemon_mode

# Cleanup function to stop only services started by this dev launcher.
cleanup() {
    if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "Stopping tunnel (PID: $TUNNEL_PID)..."
        kill "$TUNNEL_PID" 2>/dev/null || true
    fi
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$LOCAL_DAEMON_PID" ] && kill -0 "$LOCAL_DAEMON_PID" 2>/dev/null; then
        echo "Stopping local daemon (PID: $LOCAL_DAEMON_PID)..."
        kill "$LOCAL_DAEMON_PID" 2>/dev/null || true
        wait "$LOCAL_DAEMON_PID" 2>/dev/null || true
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
# Note: don't pkill cloudflared here — other agents may have tunnels running on this machine
# Kill any old dev cloud-shaped Rust backend by process name (port-agnostic).
# Do not kill omi-local-backend here; local daemon mode may use a manually
# managed daemon that this launcher should only detect.
pgrep -f "omi-desktop-backend" 2>/dev/null | while read pid; do
    substep "Killing old backend (PID: $pid)"
    kill -9 "$pid" 2>/dev/null || true
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
# In local daemon mode, keep the primary user-test command fast and avoid broad
# home-directory scans unless explicitly requested.
if ! is_local_daemon_mode || [ "${OMI_CLEAN_STALE_CLONES:-0}" = "1" ]; then
    find "$HOME" -maxdepth 4 -name "$APP_NAME.app" -type d -not -path "$APP_BUNDLE" -not -path "$APP_PATH" 2>/dev/null | while read stale; do
        substep "Removing stale clone: $stale"
        rm -rf "$stale"
    done
else
    substep "Local daemon mode: skipping stale clone scan (set OMI_CLEAN_STALE_CLONES=1 to enable)"
fi

if [ "${OMI_SKIP_TUNNEL:-0}" != "1" ]; then
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
            substep "Warning: Could not capture tunnel URL (see $TUNNEL_LOG for details)"
        fi
    else
        substep "cloudflared not found — skipping tunnel (set OMI_DESKTOP_API_URL in .env instead)"
    fi
else
    substep "Skipping tunnel (OMI_SKIP_TUNNEL=1)"
fi

# ─── Load .env and credentials ─────────────────────────────────────────
cd "$BACKEND_DIR"

# Copy .env if not present — try sibling dirs, then scaffold from .env.example
if [ ! -f ".env" ] && [ -f "../backend/.env" ]; then
    cp "../backend/.env" ".env"
elif [ ! -f ".env" ] && [ -f "../Backend/.env" ]; then
    cp "../Backend/.env" ".env"
fi
if [ ! -f ".env" ] && [ "$1" != "--yolo" ] && ! is_local_daemon_mode; then
    echo ""
    echo "=== First-time setup ==="
    echo "No .env file found at $BACKEND_DIR/.env"
    echo ""
    echo "Quick start:"
    echo "  1. cp .env.example .env"
    echo "  2. Fill in required values (see comments in .env.example)"
    echo "  3. Place google-credentials.json in $BACKEND_DIR/"
    echo "     (GCP service account key with Firestore + Firebase Auth access)"
    echo ""
    echo "Minimal .env for local dev:"
    echo "  PORT=10201"
    echo "  FIREBASE_PROJECT_ID=based-hardware-dev"
    echo "  FIREBASE_API_KEY=<from GCP console>"
    echo "  GOOGLE_APPLICATION_CREDENTIALS=./google-credentials.json"
    echo ""
    echo "Or skip the backend entirely:"
    echo "  OMI_SKIP_BACKEND=1 ./run.sh"
    echo "  (set OMI_DESKTOP_API_URL and OMI_PYTHON_API_URL in .env.app to point to remote backends)"
    echo ""
    echo "Or just use the production backend (no setup needed):"
    echo "  ./run.sh --yolo"
    echo "==========================="
    exit 1
fi

# Symlink google-credentials.json if not present
if [ ! -f "google-credentials.json" ] && [ -f "../backend/google-credentials.json" ]; then
    ln -sf "../backend/google-credentials.json" "google-credentials.json"
elif [ ! -f "google-credentials.json" ] && [ -f "../Backend/google-credentials.json" ]; then
    ln -sf "../Backend/google-credentials.json" "google-credentials.json"
fi

# Read environment from .env (skip if missing — yolo mode doesn't need it)
if [ -f "$BACKEND_DIR/.env" ]; then
    set -a; source "$BACKEND_DIR/.env"; set +a
fi
configure_local_daemon_mode

# Read backend PORT from env (default: 10201, never use 8080)
BACKEND_PORT="${PORT:-10201}"
export PORT="$BACKEND_PORT"

# Validate credentials (needed for both backend and auth)
CREDS_PATH="$BACKEND_DIR/google-credentials.json"
if [ "${OMI_SKIP_BACKEND:-0}" != "1" ] && [ ! -f "$CREDS_PATH" ]; then
    echo "ERROR: Missing credentials file: $CREDS_PATH"
    echo ""
    echo "  Option A: Place your GCP service account key here:"
    echo "    cp /path/to/google-credentials.json $CREDS_PATH"
    echo ""
    echo "  Option B: Skip the local backend and use a remote one:"
    echo "    OMI_SKIP_BACKEND=1 ./run.sh"
    exit 1
fi
if [ -f "$CREDS_PATH" ]; then
    export GOOGLE_APPLICATION_CREDENTIALS="$CREDS_PATH"
fi

# Validate FIREBASE_PROJECT_ID (required unless yolo mode — no local backend)
if [ -z "$FIREBASE_PROJECT_ID" ] && [ "${OMI_SKIP_BACKEND:-0}" != "1" ]; then
    echo "ERROR: FIREBASE_PROJECT_ID is not set."
    echo ""
    echo "  Add to $BACKEND_DIR/.env:"
    echo "    FIREBASE_PROJECT_ID=based-hardware       # prod Firestore"
    echo "    FIREBASE_PROJECT_ID=based-hardware-dev   # dev Firestore"
    exit 1
fi
if is_local_daemon_mode; then
    substep "Local daemon mode: skipping cloud backend credential requirements"
elif [ -n "$FIREBASE_AUTH_PROJECT_ID" ]; then
    substep "Auth project: tokens validated against $FIREBASE_AUTH_PROJECT_ID, Firestore on $FIREBASE_PROJECT_ID"
    substep "Firebase project: $FIREBASE_PROJECT_ID | Backend port: $BACKEND_PORT"
else
    substep "Firebase project: $FIREBASE_PROJECT_ID | Backend port: $BACKEND_PORT"
fi
cd - > /dev/null

# ─── Local daemon health preflight / dev supervision ──────────────────
if is_local_daemon_mode; then
    step "Checking local daemon health..."
    if local_daemon_health_ok; then
        substep "Local daemon is ready at $OMI_LOCAL_DAEMON_URL"
    elif [ "${OMI_LOCAL_DAEMON_SUPERVISE:-0}" = "1" ]; then
        LOCAL_DAEMON_LOG="${OMI_LOCAL_DAEMON_LOG:-/tmp/omi-local-backend-dev.log}"
        substep "Starting local daemon from $LOCAL_DAEMON_DIR"
        cd "$LOCAL_DAEMON_DIR"
        cargo run --quiet > "$LOCAL_DAEMON_LOG" 2>&1 &
        LOCAL_DAEMON_PID=$!
        cd - > /dev/null

        for i in {1..80}; do
            if local_daemon_health_ok; then
                substep "Local daemon is ready at $OMI_LOCAL_DAEMON_URL (PID: $LOCAL_DAEMON_PID)"
                break
            fi
            if ! kill -0 "$LOCAL_DAEMON_PID" 2>/dev/null; then
                echo "ERROR: Local daemon exited during startup. Log:"
                sed -n '1,160p' "$LOCAL_DAEMON_LOG" 2>/dev/null || true
                exit 1
            fi
            sleep 0.25
        done

        if ! local_daemon_health_ok; then
            echo "ERROR: Timed out waiting for local daemon health at $OMI_LOCAL_DAEMON_URL/health"
            echo "Log: $LOCAL_DAEMON_LOG"
            sed -n '1,160p' "$LOCAL_DAEMON_LOG" 2>/dev/null || true
            exit 1
        fi
    else
        echo "ERROR: Local daemon mode is enabled, but $OMI_LOCAL_DAEMON_URL/health is unreachable."
        echo ""
        echo "Start it manually:"
        echo "  cd desktop/local-backend && cargo run"
        echo ""
        echo "Or let this dev launcher supervise it:"
        echo "  OMI_DESKTOP_BACKEND_MODE=local OMI_LOCAL_DAEMON_SUPERVISE=1 ./run.sh"
        exit 1
    fi

    if local_daemon_health_ok; then
        SEED_SCRIPT="$(cd "$(dirname "$0")/local-backend/tools" && pwd)/seed_hybrid_defaults.sh"
        if [ -x "$SEED_SCRIPT" ]; then
            substep "Seeding hybrid provider defaults (if unset)"
            "$SEED_SCRIPT" || substep "Warning: hybrid provider seed failed (non-fatal)"
        fi
    fi
fi

# ─── Start Rust backend ───────────────────────────────────────────────
if [ "${OMI_SKIP_BACKEND:-0}" != "1" ]; then
    step "Starting Rust backend..."
    cd "$BACKEND_DIR"

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
            echo "ERROR: Backend failed to start. Check $BACKEND_DIR/.env and credentials."
            exit 1
        fi
        sleep 0.5
    done
else
    substep "Skipping backend (OMI_SKIP_BACKEND=1) — using OMI_DESKTOP_API_URL from .env"
fi

# Check if another SwiftPM instance is running (will block our build)
SWIFTPM_PID=$(pgrep -f "swiftpm-workspace-state|swift-build|swift-package" 2>/dev/null | head -1)
if [ -n "$SWIFTPM_PID" ]; then
    step "Waiting for other SwiftPM instance (PID: $SWIFTPM_PID) to finish..."
    while kill -0 "$SWIFTPM_PID" 2>/dev/null; do
        sleep 1
    done
fi

step "Building agent (npm install + tsc)..."
AGENT_DIR="$(dirname "$0")/agent"
if [ -d "$AGENT_DIR" ]; then
    cd "$AGENT_DIR"
    if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules/.package-lock.json" ]; then
        substep "Installing npm dependencies"
        npm install --no-fund --no-audit 2>&1 | tail -1
    fi
    substep "Compiling TypeScript and copying assets"
    npm run build --silent
    cd - > /dev/null
else
    echo "Warning: agent directory not found at $AGENT_DIR"
fi

step "Checking schema docs..."
if [ -f scripts/check_schema_docs.sh ]; then
    bash scripts/check_schema_docs.sh || substep "Schema docs check failed (non-fatal)"
fi

if ! pkg-config --exists libwebp 2>/dev/null; then
    echo "ERROR: libwebp headers not found (required by CWebP for screen capture)."
    echo "  brew install webp"
    echo "  Then re-run ./run.sh"
    exit 1
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

# Copy Sentry framework
SENTRY_FRAMEWORK="Desktop/.build/arm64-apple-macosx/debug/Sentry.framework"
if [ -d "$SENTRY_FRAMEWORK" ]; then
    substep "Copying Sentry framework"
    rm -rf "$APP_BUNDLE/Contents/Frameworks/Sentry.framework"
    cp -R "$SENTRY_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
fi

# Copy onnxruntime framework
ONNX_FRAMEWORK="Desktop/.build/arm64-apple-macosx/debug/onnxruntime.framework"
if [ -d "$ONNX_FRAMEWORK" ]; then
    substep "Copying onnxruntime framework"
    rm -rf "$APP_BUNDLE/Contents/Frameworks/onnxruntime.framework"
    cp -R "$ONNX_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
fi

# Copy libwebp dylibs and rewrite load paths
WEBP_LIB="$(pkg-config --variable=libdir libwebp 2>/dev/null)/libwebp.7.dylib"
if [ -f "$WEBP_LIB" ]; then
    substep "Bundling libwebp"
    cp "$WEBP_LIB" "$APP_BUNDLE/Contents/Frameworks/libwebp.7.dylib"
    # Find libsharpyuv (libwebp dependency)
    SHARPYUV_LIB="$(dirname "$WEBP_LIB")/libsharpyuv.0.dylib"
    if [ -f "$SHARPYUV_LIB" ]; then
        cp "$SHARPYUV_LIB" "$APP_BUNDLE/Contents/Frameworks/libsharpyuv.0.dylib"
        install_name_tool -id "@rpath/libsharpyuv.0.dylib" "$APP_BUNDLE/Contents/Frameworks/libsharpyuv.0.dylib"
    fi
    install_name_tool -id "@rpath/libwebp.7.dylib" "$APP_BUNDLE/Contents/Frameworks/libwebp.7.dylib"
    install_name_tool -change "$WEBP_LIB" "@rpath/libwebp.7.dylib" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME"
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

substep "Copying agent"
if [ -d "$AGENT_DIR/dist" ]; then
    mkdir -p "$APP_BUNDLE/Contents/Resources/agent"
    cp -Rf "$AGENT_DIR/dist" "$APP_BUNDLE/Contents/Resources/agent/"
    cp -f "$AGENT_DIR/package.json" "$APP_BUNDLE/Contents/Resources/agent/"
    cp -Rf "$AGENT_DIR/node_modules" "$APP_BUNDLE/Contents/Resources/agent/"
fi

substep "Copying pi-mono-extension (for piMono harness)"
PI_MONO_EXT_DIR="$(dirname "$0")/pi-mono-extension"
if [ -d "$PI_MONO_EXT_DIR" ]; then
    mkdir -p "$APP_BUNDLE/Contents/Resources/pi-mono-extension"
    cp -f "$PI_MONO_EXT_DIR/index.ts" "$APP_BUNDLE/Contents/Resources/pi-mono-extension/"
    cp -f "$PI_MONO_EXT_DIR/package.json" "$APP_BUNDLE/Contents/Resources/pi-mono-extension/"
else
    echo "Warning: pi-mono-extension not found at $PI_MONO_EXT_DIR"
fi

substep "Building Codex proxy (omi-codex-proxy)"
CODEX_PROXY_DIR="$(dirname "$0")/codex-proxy"
if [ -d "$CODEX_PROXY_DIR" ]; then
    (cd "$CODEX_PROXY_DIR" && cargo build --release --quiet)
    mkdir -p "$APP_BUNDLE/Contents/Resources"
    cp -f "$CODEX_PROXY_DIR/target/release/omi-codex-proxy" "$APP_BUNDLE/Contents/Resources/omi-codex-proxy"
    chmod +x "$APP_BUNDLE/Contents/Resources/omi-codex-proxy"
else
    echo "Warning: codex-proxy not found at $CODEX_PROXY_DIR"
fi

substep "Copying .env.app"
if [ -f ".env.app.dev" ]; then
    cp -f .env.app.dev "$APP_BUNDLE/Contents/Resources/.env"
elif [ -f ".env.app" ]; then
    cp -f .env.app "$APP_BUNDLE/Contents/Resources/.env"
else
    touch "$APP_BUNDLE/Contents/Resources/.env"
fi

set_bundle_env() {
    local key="$1"
    local value="$2"
    local env_file="$APP_BUNDLE/Contents/Resources/.env"
    if grep -q "^${key}=" "$env_file"; then
        sed -i '' "s|^${key}=.*|${key}=${value}|" "$env_file"
    else
        echo "${key}=${value}" >> "$env_file"
    fi
}

# Set OMI_DESKTOP_API_URL: tunnel URL if available, otherwise from .env or local backend
if [ -n "$TUNNEL_URL" ]; then
    EFFECTIVE_API_URL="$TUNNEL_URL"
elif [ -n "$OMI_DESKTOP_API_URL" ]; then
    EFFECTIVE_API_URL="$OMI_DESKTOP_API_URL"
else
    EFFECTIVE_API_URL="http://localhost:$BACKEND_PORT"
fi
set_bundle_env "OMI_DESKTOP_API_URL" "$EFFECTIVE_API_URL"
substep "OMI_DESKTOP_API_URL=$EFFECTIVE_API_URL"
if is_local_daemon_mode; then
    set_bundle_env "OMI_DESKTOP_BACKEND_MODE" "local"
    set_bundle_env "OMI_LOCAL_DAEMON_URL" "$OMI_LOCAL_DAEMON_URL"
    # GUI launches via `open` do not inherit shell exports — AppState.loadEnvironment() reads bundled .env.
    set_bundle_env "OMI_HYBRID_DIRECT_STT_ENABLED" "${OMI_HYBRID_DIRECT_STT_ENABLED:-1}"
    set_bundle_env "OMI_HYBRID_DIRECT_CHAT_ENABLED" "${OMI_HYBRID_DIRECT_CHAT_ENABLED:-1}"
    set_bundle_env "OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED" "${OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED:-0}"
    substep "OMI_DESKTOP_BACKEND_MODE=local"
    substep "OMI_LOCAL_DAEMON_URL=$OMI_LOCAL_DAEMON_URL"
    substep "OMI_HYBRID_DIRECT_STT_ENABLED=${OMI_HYBRID_DIRECT_STT_ENABLED:-1}"
    substep "OMI_HYBRID_DIRECT_CHAT_ENABLED=${OMI_HYBRID_DIRECT_CHAT_ENABLED:-1}"
    substep "OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED=${OMI_HYBRID_DIRECT_EMBEDDINGS_ENABLED:-0}"
fi
# Bootstrap FIREBASE_API_KEY — check env var first (yolo mode), then backend .env
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
# Bootstrap OMI_PYTHON_API_URL — main Omi Python backend (auth, subscriptions, payments, transcription)
# Do NOT fall back to OMI_DESKTOP_API_URL — that's the Rust desktop-backend which doesn't serve these routes
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

substep "Copying app icon"
cp -f omi_icon.icns "$APP_BUNDLE/Contents/Resources/OmiIcon.icns" 2>/dev/null || true

substep "Creating PkgInfo"
echo -n "APPL????" > "$APP_BUNDLE/Contents/PkgInfo"

# Embed provisioning profile (required for Sign In with Apple entitlement).
# Named bundles skip this — the profile is bundle-specific to com.omi.desktop-dev,
# embedding it in a different bundle ID causes RBSRequestErrorDomain Code=5.
if [ "$IS_NAMED_BUNDLE" = false ]; then
    if [ -f "Desktop/embedded-dev.provisionprofile" ]; then
        substep "Embedding dev provisioning profile"
        cp "Desktop/embedded-dev.provisionprofile" "$APP_BUNDLE/Contents/embedded.provisionprofile"
    elif [ -f "Desktop/embedded.provisionprofile" ]; then
        substep "Embedding provisioning profile"
        cp "Desktop/embedded.provisionprofile" "$APP_BUNDLE/Contents/embedded.provisionprofile"
    fi
else
    substep "Named bundle ($BUNDLE_ID) — skipping provisioning profile"
fi

auth_debug "BEFORE signing: $(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"

step "Removing extended attributes (xattr -cr)..."
# SwiftPM copies some dylibs (libsharpyuv, libwebp) with read-only perms,
# which makes `xattr -cr` fail with EACCES. Make the bundle writable first.
chmod -R u+w "$APP_BUNDLE"
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
    if [ -d "$APP_BUNDLE/Contents/Frameworks/Sentry.framework" ]; then
        substep "Signing Sentry framework"
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/Frameworks/Sentry.framework"
    fi
    if [ -d "$APP_BUNDLE/Contents/Frameworks/onnxruntime.framework" ]; then
        substep "Signing onnxruntime framework"
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/Frameworks/onnxruntime.framework"
    fi
    if [ -f "$APP_BUNDLE/Contents/Frameworks/libsharpyuv.0.dylib" ]; then
        substep "Signing libsharpyuv"
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/Frameworks/libsharpyuv.0.dylib"
    fi
    if [ -f "$APP_BUNDLE/Contents/Frameworks/libwebp.7.dylib" ]; then
        substep "Signing libwebp"
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/Frameworks/libwebp.7.dylib"
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
    #
    # Named bundles always use fallback — they have no provisioning profile, so
    # com.apple.developer.applesignin would cause launchd to reject the launch.
    EFFECTIVE_ENTITLEMENTS="Desktop/Omi.entitlements"
    PROFILE_PATH="$APP_BUNDLE/Contents/embedded.provisionprofile"
    USE_FALLBACK_ENTITLEMENTS=false

    if [ "$IS_NAMED_BUNDLE" = true ]; then
        substep "Named bundle — stripping applesignin entitlement"
        USE_FALLBACK_ENTITLEMENTS=true
    elif [ -f "$PROFILE_PATH" ]; then
        IDENTITY_TEAM_ID=$(echo "$SIGN_IDENTITY" | sed -n 's/.*(\([A-Z0-9]*\)).*/\1/p')
        PROFILE_TEAM_ID=""
        PROFILE_TEAM_ID=$(security cms -D -i "$PROFILE_PATH" > /tmp/omi-dev-profile.plist 2>/dev/null && \
            /usr/libexec/PlistBuddy -c "Print :TeamIdentifier:0" /tmp/omi-dev-profile.plist 2>/dev/null || true)
        if [ -z "$PROFILE_TEAM_ID" ]; then
            substep "Could not extract profile team ID (security cms failed); using local entitlements fallback"
            USE_FALLBACK_ENTITLEMENTS=true
        elif [ "$PROFILE_TEAM_ID" != "$IDENTITY_TEAM_ID" ]; then
            substep "Profile team ($PROFILE_TEAM_ID) != identity team ($IDENTITY_TEAM_ID); using local entitlements fallback"
            USE_FALLBACK_ENTITLEMENTS=true
        fi
    fi

    if [ "$USE_FALLBACK_ENTITLEMENTS" = true ]; then
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
chmod -R u+w "$APP_BUNDLE"
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
if [ -n "$BACKEND_PID" ]; then
    echo "Backend:  http://localhost:$BACKEND_PORT (PID: $BACKEND_PID)"
else
    echo "Backend:  skipped (OMI_SKIP_BACKEND=1)"
fi
if [ -n "$TUNNEL_PID" ]; then
    echo "Tunnel:   $TUNNEL_URL (PID: $TUNNEL_PID)"
else
    echo "Tunnel:   skipped"
fi
echo "App:      $APP_PATH"
echo "API URL:  $EFFECTIVE_API_URL"
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

# Keep script running until Ctrl+C
echo "Press Ctrl+C to stop all services..."
if [ -n "$BACKEND_PID" ]; then
    wait "$BACKEND_PID"
else
    # No backend — just wait for user to Ctrl+C
    while true; do sleep 60; done
fi
