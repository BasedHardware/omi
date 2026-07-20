#!/bin/bash
set -e

# Force C locale for numeric formatting so `printf %f` accepts the
# dot-decimal values produced by `bc` even when the user's shell runs in
# a non-English locale (e.g. de_DE.UTF-8 expects a comma separator).
export LC_NUMERIC=C

# ─── Arguments ─────────────────────────────────────────────────────────
YOLO_MODE=0
FORCE_FULL_BUNDLE="${OMI_FORCE_FULL_BUNDLE:-0}"
# Reseeding replaces an existing named profile after preserving it. It must run
# through the install/seed path; a fast executable patch intentionally skips it.
if [ "${OMI_FORCE_REWIND_SEED:-0}" = "1" ]; then
    FORCE_FULL_BUNDLE=1
fi
FAST_ONLY=0
NO_WAIT="${NO_WAIT:-0}"
SHOW_HELP=0
for arg in "$@"; do
    case "$arg" in
        --yolo)
            YOLO_MODE=1
            ;;
        --full)
            FORCE_FULL_BUNDLE=1
            ;;
        --fast-only)
            FAST_ONLY=1
            ;;
        --no-wait)
            NO_WAIT=1
            ;;
        --help|-h)
            SHOW_HELP=1
            ;;
        *)
            echo "ERROR: unknown option: $arg" >&2
            exit 2
            ;;
    esac
done

if [ "$FAST_ONLY" = "1" ] && [ "$FORCE_FULL_BUNDLE" = "1" ]; then
    echo "ERROR: --fast-only cannot be combined with --full or OMI_FORCE_FULL_BUNDLE=1" >&2
    exit 2
fi

# ─── Help ──────────────────────────────────────────────────────────────
if [ "$SHOW_HELP" = "1" ]; then
    cat <<'USAGE'
Usage: ./run.sh [options]

Build and run the Omi Desktop dev app with local backend services.

Options (via environment variables):
  OMI_SKIP_BACKEND=1      Skip starting Rust backend (use remote backend via OMI_DESKTOP_API_URL)
  OMI_SKIP_TUNNEL=1        Skip Cloudflare tunnel (use OMI_DESKTOP_API_URL from .env directly)
  PORT=10201                Rust backend port (default: 10201, never use 8080)
  OMI_APP_NAME="Omi Dev"   App name (default: "Omi Dev")
  OMI_SKIP_AUTH_SEED=1     Do not copy auth/onboarding from Omi Dev into named bundles
  OMI_SKIP_SETTINGS_SEED=1  Do not copy shortcuts/settings from Omi Dev into named bundles
  OMI_SKIP_REWIND_SEED=1    Do not copy the local Rewind history into a new named bundle
  OMI_FORCE_REWIND_SEED=1   Replace an existing named-bundle Rewind history with a fresh Omi Dev snapshot
  OMI_DEV_EAGER_PERMISSIONS=1  Preserve eager mic/screen/file startup behavior in named bundles
  OMI_PYTHON_API_URL="..."  Python backend URL (explicit override; named bundles default to dev)
  OMI_SIGN_IDENTITY="..."  Code signing identity (auto-detected if not set)
  OMI_DESKTOP_BACKEND_RELEASE=1  Use an optimized Rust backend locally (debug is the fast default)
  OMI_FORCE_FULL_BUNDLE=1  Rebuild the complete app bundle on this launch
  OMI_SCAN_STALE_BUNDLES=1  Remove stale same-named app bundles under $HOME (recovery only)
  OMI_ENABLE_LOCAL_AUTOMATION=1   Force the automation bridge on (auto-on for non-prod bundles; see scripts/omi-ctl)
  OMI_DISABLE_LOCAL_AUTOMATION=1  Run a dev build "clean" with the bridge off
  OMI_AUTOMATION_PORT=47777       Bridge port (set per bundle when running several at once)
  OMI_DESKTOP_LOCAL_PROFILE=1     Local harness profile; localhost endpoints/Auth emulator only

Required files:
  Backend-Rust/.env         Environment variables (copy from ../.env.example)
  Backend-Rust/google-credentials.json  GCP service account key

Required tools:
  cargo, xcrun/swift, python3, npm, node, codesign, cloudflared (unless skipped)

Port allocation (avoid 8080 to prevent port conflicts):
  Backend default: 10201

Examples:
  ./run.sh                                  # Fast incremental launch after first run
  OMI_SKIP_BACKEND=1 ./run.sh               # App only (backend running elsewhere)
  OMI_SKIP_TUNNEL=1 ./run.sh                # No Cloudflare tunnel (use direct URL)
  ./run.sh --yolo                            # Quick start: use dev backend, no local services
  ./run.sh --full                            # Rebuild every packaged dependency
  ./run.sh --fast-only                       # Reuse an eligible installed bundle or fail without packaging
  ./run.sh --fast-only --no-wait             # Relaunch an eligible remote/harness bundle, then return
USAGE
    exit 0
fi

# ─── YOLO mode: use dev backend, zero local setup ────────────────────
# Keep these endpoint values aligned with DesktopBackendEnvironment's dev
# defaults. The dev services currently mint prod Firebase identities, so this
# is a service-revision target, not an isolated local-data harness.
apply_yolo_env() {
    export OMI_SKIP_BACKEND=1
    export OMI_SKIP_TUNNEL=1
    export OMI_DESKTOP_API_URL="https://desktop-backend-dt5lrfkkoa-uc.a.run.app"
    export OMI_PYTHON_API_URL="https://api.omiapi.com"
    export FIREBASE_API_KEY="AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8"
}

if [ "$YOLO_MODE" = "1" ]; then
    echo ""
    echo "=========================================="
    echo "  YOLO MODE — using development backend"
    echo "=========================================="
    echo ""
    echo "  WARNING: This connects directly to the dev Cloud Run backends."
    echo "  They currently use production Firebase identities and data stores."
    echo "  No local Rust backend, no local auth, no tunnel."
    echo "  This is a temporary shortcut — will be removed once"
    echo "  desktop dev setup friction is fully resolved."
    echo ""
    echo "=========================================="
    echo ""

    apply_yolo_env
fi

# Clear system OPENAI_API_KEY so .env takes precedence
unset OPENAI_API_KEY

# Use Xcode's default toolchain to match the SDK version
unset TOOLCHAINS

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# shellcheck source=fast-dev-bundle.sh
source "$SCRIPT_DIR/scripts/fast-dev-bundle.sh"
# shellcheck source=local-profile-env.sh
source "$SCRIPT_DIR/scripts/local-profile-env.sh"
# shellcheck source=rust-backend-dev.sh
source "$SCRIPT_DIR/scripts/rust-backend-dev.sh"

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

macos_copy_tree() {
    local src="$1"
    local dest="$2"
    if [ "$(uname -s)" = "Darwin" ] && command -v ditto >/dev/null 2>&1; then
        ditto --norsrc "$src" "$dest"
    elif [ "$(uname -s)" = "Darwin" ]; then
        cp -R -X "$src" "$dest"
    else
        cp -R "$src" "$dest"
    fi
}

# Per-worktree isolation: derive unique ports + bundle name so parallel worktrees don't
# collide. Sets OMI_INSTANCE / RUST_PORT / PYTHON_PORT / AUTOMATION_PORT / OMI_APP_NAME /
# OMI_DEV_DIR (explicit overrides always win; the primary checkout keeps "Omi Dev" + 10201).
source "$SCRIPT_DIR/../../scripts/dev-instance.sh"
BACKEND_PORT="${PORT:-$RUST_PORT}"
export PORT="$BACKEND_PORT"

# Serialize same-worktree builds only (shared Desktop/.build + build/$APP_NAME.app).
# Cross-worktree ./run.sh must not block each other. Hold through install/seed/open,
# then release before the long-running wait — see scripts/run-sh-build-lock.sh.
# Explicit OMI_APP_NAME overrides that collide across worktrees are unsupported
# (/Applications/$APP_NAME.app is machine-global and not cross-locked).
source "$SCRIPT_DIR/scripts/run-sh-build-lock.sh"
omi_run_sh_acquire_build_lock "another ./run.sh in this worktree" 600 || exit 1
# Temporary until `trap cleanup EXIT` below chains release into cleanup().
trap 'omi_run_sh_release_build_lock' EXIT INT TERM

# App configuration
BINARY_NAME="Omi Computer"  # Package.swift target — binary paths, pkill, CFBundleExecutable
source "$SCRIPT_DIR/scripts/app-config.sh"
derive_omi_app_config "${OMI_APP_NAME:-Omi Dev}" || exit 1
LOCAL_PROFILE=false
[ "${OMI_DESKTOP_LOCAL_PROFILE:-0}" = "1" ] && LOCAL_PROFILE=true

# A named QA bundle should exercise the shared development service unless its
# launcher deliberately selects another profile.  Check variable *presence*,
# not values: `OMI_SKIP_BACKEND=0` is an explicit local-launch request and
# must never be overwritten by the remote-dev defaults.
should_default_named_bundle_to_dev_backend() {
    [ "${IS_NAMED_BUNDLE:-false}" = true ] \
        && [ "${LOCAL_PROFILE:-false}" = false ] \
        && [ "${YOLO_MODE:-0}" != "1" ] \
        && [ -z "${OMI_SKIP_BACKEND+x}" ] \
        && [ -z "${OMI_SKIP_TUNNEL+x}" ] \
        && [ -z "${OMI_DESKTOP_API_URL+x}" ] \
        && [ -z "${OMI_PYTHON_API_URL+x}" ]
}

NAMED_BUNDLE_DEFAULT_DEV_BACKEND=false
if should_default_named_bundle_to_dev_backend; then
    NAMED_BUNDLE_DEFAULT_DEV_BACKEND=true
fi

# Named QA bundles are remote-dev by default. Apply this before any launch
# preparation so they do not start a local backend or tunnel, and reapply it
# after sourcing Backend-Rust/.env below so repository-local defaults cannot
# silently retarget a QA bundle. Explicit launch environment values above opt
# out and remain authoritative.
if [ "$NAMED_BUNDLE_DEFAULT_DEV_BACKEND" = true ]; then
    substep "Named bundle default: using development backend"
    apply_yolo_env
fi

# A detached launch is safe only when another service owns the backend. It is
# intended for the remote-dev and local-harness fast lanes; a run.sh-owned
# backend must remain attached so its lifecycle and logs stay scoped here.
if [ "$NO_WAIT" = "1" ] \
    && { [ "${OMI_SKIP_BACKEND:-0}" != "1" ] || [ "${OMI_SKIP_TUNNEL:-0}" != "1" ]; }; then
    echo "ERROR: --no-wait requires OMI_SKIP_BACKEND=1 and OMI_SKIP_TUNNEL=1 (use --yolo or the local harness)." >&2
    exit 2
fi

BUILD_DIR="build"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
APP_PATH="/Applications/$APP_NAME.app"
APP_DESKTOP_PATH="$HOME/Desktop/$APP_NAME.app"
APP_DOWNLOADS_PATH="$HOME/Downloads/$APP_NAME.app"
SIGN_IDENTITY="${OMI_SIGN_IDENTITY:-}"
if [ "$LOCAL_PROFILE" = true ]; then
    if [ "$BUNDLE_ID" = "com.omi.desktop-dev" ] || { [ "$IS_NAMED_BUNDLE" = false ] && [ "$APP_NAME" = "Omi Dev" ]; }; then
        echo "ERROR: OMI_DESKTOP_LOCAL_PROFILE=1 cannot target Omi Dev (com.omi.desktop-dev)."
        echo "       Local profile would overwrite Omi Dev auth/state/binary. Use a named omi- bundle instead:"
        echo "         DESKTOP_APP_NAME=omi-memory make desktop-run-local"
        echo "       or:  cd desktop/macos && OMI_APP_NAME=omi-memory OMI_DESKTOP_LOCAL_PROFILE=1 OMI_SKIP_BACKEND=1 OMI_SKIP_TUNNEL=1 ./run.sh"
        exit 1
    fi
    if [ "$IS_NAMED_BUNDLE" = true ]; then
        case "$APP_NAME" in
            omi-*|Omi-*) ;;
            *)
                echo "ERROR: OMI_DESKTOP_LOCAL_PROFILE=1 with OMI_APP_NAME requires an omi- prefixed bundle (got OMI_APP_NAME='$APP_NAME')"
                exit 1
                ;;
        esac
        export OMI_LOCAL_PROFILE_STORAGE_NAME="${OMI_LOCAL_PROFILE_STORAGE_NAME:-$APP_NAME}"
    else
        echo "ERROR: OMI_DESKTOP_LOCAL_PROFILE=1 requires an omi- prefixed named bundle (OMI_APP_NAME or DESKTOP_APP_NAME)"
        exit 1
    fi
    if [ "${OMI_SKIP_BACKEND:-0}" != "1" ] || [ "${OMI_SKIP_TUNNEL:-0}" != "1" ]; then
        echo "ERROR: Omi Dev local harness requires OMI_SKIP_BACKEND=1 and OMI_SKIP_TUNNEL=1; start the harness with make dev-up first"
        exit 1
    fi
    case "${OMI_DESKTOP_API_URL:-}" in http://127.*|http://localhost*) ;; *) echo "ERROR: OMI_DESKTOP_API_URL must be localhost for Omi Dev local harness"; exit 1 ;; esac
    case "${OMI_PYTHON_API_URL:-}" in http://127.*|http://localhost*) ;; *) echo "ERROR: OMI_PYTHON_API_URL must be localhost for Omi Dev local harness"; exit 1 ;; esac
    if [ "${FIREBASE_PROJECT_ID:-}" != "demo-omi-local" ] || [ "${FIREBASE_AUTH_PROJECT_ID:-demo-omi-local}" != "demo-omi-local" ]; then
        echo "ERROR: Omi Dev local harness must use Firebase project demo-omi-local"
        exit 1
    fi
fi
AUTOMATION_PORT="${OMI_AUTOMATION_PORT:-${AUTOMATION_PORT:-47777}}"
AUTOMATION_CAPTURE_ROOT="${OMI_AUTOMATION_CAPTURE_ROOT:-$SCRIPT_DIR/.harness/runs}"
AUTOMATION_ARGS=("--automation-port=$AUTOMATION_PORT" "--automation-capture-root=$AUTOMATION_CAPTURE_ROOT")
if [ "${OMI_ENABLE_LOCAL_AUTOMATION:-0}" = "1" ]; then
    AUTOMATION_ARGS=(--automation-bridge "${AUTOMATION_ARGS[@]}")
fi

# Backend configuration (Rust)
BACKEND_DIR="$(cd "$(dirname "$0")/Backend-Rust" && pwd)"
BACKEND_PID=""
BACKEND_REUSED_PID=""
BACKEND_PIDFILE="$OMI_DEV_DIR/rust-backend.pid"
BACKEND_METADATA="$OMI_DEV_DIR/rust-backend.meta"
TUNNEL_PID=""
TUNNEL_URL="${TUNNEL_URL:-}"
AUTH_CACHE=""

# Cleanup function to stop backend, auth, and tunnel on exit
cleanup() {
    # Release the build lock if still held (early exit before install, or if
    # the post-install release was skipped). Chained here because
    # `trap cleanup EXIT` overwrites the earlier lock-only trap.
    omi_run_sh_release_build_lock
    if [ -n "$AUTH_CACHE" ]; then
        rm -f "$AUTH_CACHE"
    fi
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

AUTH_DEBUG_LOG=/private/tmp/auth-debug.log
rm -f $AUTH_DEBUG_LOG
auth_debug() { echo "[AUTH DEBUG][$(date +%H:%M:%S)] $1" >> $AUTH_DEBUG_LOG; }
touch $AUTH_DEBUG_LOG

resolve_signing_identity() {
    if [ -n "$SIGN_IDENTITY" ]; then
        return
    fi
    # Prefer the development identity so local permissions remain stable.
    SIGN_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | sed 's/.*"\(.*\)"/\1/')
    if [ -z "$SIGN_IDENTITY" ]; then
        SIGN_IDENTITY=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | sed 's/.*"\(.*\)"/\1/')
    fi
    if [ -z "$SIGN_IDENTITY" ] && [ "${OMI_ALLOW_ADHOC_SIGN:-0}" = "1" ] && [ "$IS_NAMED_BUNDLE" = true ]; then
        SIGN_IDENTITY="-"
        substep "Using ad-hoc signing for named test bundle ($BUNDLE_ID)"
    fi
}

fast_bundle_fingerprint() {
    local desktop_api_fingerprint="${OMI_DESKTOP_API_URL:-}"
    local python_api_fingerprint="${OMI_PYTHON_API_URL:-}"
    # The local-profile writer refreshes both endpoint settings plus disposable
    # Auth-emulator values inside the installed bundle on every fast patch.
    # They are launch configuration, not a packaged-input boundary.
    if [ "$LOCAL_PROFILE" = true ]; then
        desktop_api_fingerprint="local-profile-refreshed"
        python_api_fingerprint="local-profile-refreshed"
    fi
    omi_fast_bundle_fingerprint \
        "$SCRIPT_DIR" \
        "bundle-id=$BUNDLE_ID" \
        "signing-identity=$SIGN_IDENTITY" \
        "local-profile=$LOCAL_PROFILE" \
        "yolo=$YOLO_MODE" \
        "skip-backend=${OMI_SKIP_BACKEND:-0}" \
        "skip-tunnel=${OMI_SKIP_TUNNEL:-0}" \
        "desktop-api-url=$desktop_api_fingerprint" \
        "python-api-url=$python_api_fingerprint" \
        "backend-port=$BACKEND_PORT"
}

fast_bundle_profile_root() {
    if [ "$IS_NAMED_BUNDLE" = true ]; then
        printf '%s\n' "$HOME/Library/Application Support/Omi Dev Bundles/$BUNDLE_ID"
    else
        printf '%s\n' "$HOME/Library/Application Support/Omi"
    fi
}

reset_local_profile_keychain_state() {
    if [ "$LOCAL_PROFILE" = true ]; then
        step "Resetting local-profile Keychain state..."
        # Local profiles sign into the synthetic Auth emulator on every launch.
        # Clear only this installed named bundle's scoped disposable items so an
        # earlier ad-hoc build cannot block startup on a stale TrustedApplication
        # ACL. The reset helper rejects Prod, Beta, Omi Dev, and identity mismatch.
        ./scripts/omi-local-profile-keychain-reset.sh "$BUNDLE_ID" "$APP_PATH"
    fi
}

fail_fast_only() {
    local reason="$1"
    printf 'launch_mode=failed fast_reason=%s bundle_id=%s profile_root=%q\n' \
        "$reason" "$BUNDLE_ID" "$(fast_bundle_profile_root)" >&2
    exit 3
}

# `--fast-only` is an inspection-first agent operation. Read the same selected
# configuration that a normal launch will use, but do it before killing an app,
# clearing a build directory, starting a tunnel, or starting a backend. This
# makes an ineligible fast launch safe to probe repeatedly.
prepare_fast_only_configuration() {
    if [ "$LOCAL_PROFILE" = false ] && [ -f "$BACKEND_DIR/.env" ]; then
        set -a
        # shellcheck disable=SC1090
        source "$BACKEND_DIR/.env"
        set +a
    fi
    if [ "$YOLO_MODE" = "1" ] || [ "$NAMED_BUNDLE_DEFAULT_DEV_BACKEND" = true ]; then
        apply_yolo_env
    fi
}

FAST_BUNDLE_STAMP="$OMI_DEV_DIR/fast-dev-bundles/$BUNDLE_ID.stamp"
if [ "$FAST_ONLY" = "1" ]; then
    prepare_fast_only_configuration
    resolve_signing_identity
    FAST_BUNDLE_FINGERPRINT="$(fast_bundle_fingerprint)"
    FAST_BUNDLE_REASON="$(omi_fast_bundle_eligibility_reason "$APP_PATH" "$FAST_BUNDLE_STAMP" "$FAST_BUNDLE_FINGERPRINT")"
    if [ "$FAST_BUNDLE_REASON" != "reusable" ]; then
        fail_fast_only "$FAST_BUNDLE_REASON"
    fi
fi

sign_app_bundle() {
    local bundle="$1"
    local sign_nested="$2"
    local effective_entitlements="Desktop/Omi.entitlements"
    local profile_path="$bundle/Contents/embedded.provisionprofile"
    local use_fallback_entitlements=false

    resolve_signing_identity
    "$(dirname "$0")/scripts/prepare-local-dev-entitlements.sh" \
        --validate-identity \
        "$SIGN_IDENTITY" \
        "$IS_NAMED_BUNDLE" \
        "${OMI_ALLOW_ADHOC_SIGN:-0}"

    if [ -z "$SIGN_IDENTITY" ]; then
        echo ""
        echo "ERROR: No signing identity found. Ad-hoc signing causes macOS to reset"
        echo "       Screen Recording permissions for ALL Omi apps (including prod/beta)."
        echo ""
        echo "  Fix: Install an Apple Development certificate in Keychain Access,"
        echo "       or set OMI_SIGN_IDENTITY to a valid identity:"
        echo "       OMI_SIGN_IDENTITY=\"Apple Development: you@example.com\" ./run.sh"
        echo ""
        echo "       For named throwaway bundles only, tests may opt into ad-hoc signing:"
        echo "       OMI_APP_NAME=\"omi-my-test\" OMI_ALLOW_ADHOC_SIGN=1 ./run.sh"
        echo ""
        exit 1
    fi

    substep "Using identity: $SIGN_IDENTITY"
    local agent_runtime_bin="$bundle/Contents/Resources/Omi Computer_Omi Computer.bundle/omi-agent-runtime"
    if [ -f "$agent_runtime_bin" ]; then
        substep "Signing Rust agent runtime"
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$agent_runtime_bin"
    fi
    if [ "$sign_nested" = true ]; then
        if [ -d "$bundle/Contents/Frameworks/Sparkle.framework" ]; then
            substep "Signing Sparkle framework"
            codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/Sparkle.framework"
        fi
        if [ -d "$bundle/Contents/Frameworks/Sentry.framework" ]; then
            substep "Signing Sentry framework"
            codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/Sentry.framework"
        fi
        if [ -d "$bundle/Contents/Frameworks/onnxruntime.framework" ]; then
            substep "Signing onnxruntime framework"
            codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/onnxruntime.framework"
        fi
        if [ -f "$bundle/Contents/Frameworks/libsharpyuv.0.dylib" ]; then
            substep "Signing libsharpyuv"
            codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/libsharpyuv.0.dylib"
        fi
        if [ -f "$bundle/Contents/Frameworks/libwebp.7.dylib" ]; then
            substep "Signing libwebp"
            codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/libwebp.7.dylib"
        fi
    fi

    # Named bundles deliberately omit Sign in with Apple because their bundle
    # IDs are not covered by Omi Dev's provisioning profile.
    if [ "$IS_NAMED_BUNDLE" = true ]; then
        substep "Named bundle — stripping applesignin entitlement"
        use_fallback_entitlements=true
    elif [ -f "$profile_path" ]; then
        local identity_team_id profile_team_id profile_plist
        identity_team_id=$(echo "$SIGN_IDENTITY" | sed -n 's/.*(\([A-Z0-9]*\)).*/\1/p')
        profile_plist=$(mktemp /tmp/omi-dev-profile.XXXXXX)
        profile_team_id=$(security cms -D -i "$profile_path" > "$profile_plist" 2>/dev/null && \
            /usr/libexec/PlistBuddy -c "Print :TeamIdentifier:0" "$profile_plist" 2>/dev/null || true)
        rm -f "$profile_plist"
        if [ -z "$profile_team_id" ]; then
            substep "Could not extract profile team ID (security cms failed); using local entitlements fallback"
            use_fallback_entitlements=true
        elif [ "$profile_team_id" != "$identity_team_id" ]; then
            substep "Profile team ($profile_team_id) != identity team ($identity_team_id); using local entitlements fallback"
            use_fallback_entitlements=true
        fi
    fi

    if [ "$use_fallback_entitlements" = true ]; then
        local local_signing_mode="development"
        if [ "$SIGN_IDENTITY" = "-" ]; then
            local_signing_mode="adhoc"
        fi
        effective_entitlements="$("$(dirname "$0")/scripts/prepare-local-dev-entitlements.sh" \
            Desktop/Omi.entitlements \
            "$OMI_DEV_DIR" \
            "$BUNDLE_ID" \
            "$local_signing_mode")"
        rm -f "$profile_path"
    fi

    substep "Signing app bundle"
    codesign --force --options runtime --entitlements "$effective_entitlements" --sign "$SIGN_IDENTITY" "$bundle"
}

update_app_desktop_api_url() {
    local env_file="$1"
    # An explicit environment or .env endpoint is authoritative over a tunnel.
    # Tunnels are a local-dev fallback only.
    if [ -n "${OMI_DESKTOP_API_URL:-}" ]; then
        EFFECTIVE_API_URL="$OMI_DESKTOP_API_URL"
    elif [ -n "$TUNNEL_URL" ]; then
        EFFECTIVE_API_URL="$TUNNEL_URL"
    else
        EFFECTIVE_API_URL="http://localhost:$BACKEND_PORT"
    fi

    if grep -q "^OMI_DESKTOP_API_URL=" "$env_file"; then
        sed -i '' "s|^OMI_DESKTOP_API_URL=.*|OMI_DESKTOP_API_URL=$EFFECTIVE_API_URL|" "$env_file"
    else
        echo "OMI_DESKTOP_API_URL=$EFFECTIVE_API_URL" >> "$env_file"
    fi
    substep "OMI_DESKTOP_API_URL=$EFFECTIVE_API_URL"
}

rewrite_bundled_dylib_load_path() {
    local binary="$1"
    local dylib_name="$2"
    local bundled_load_path="@rpath/$dylib_name"
    local current_load_path

    current_load_path="$(otool -L "$binary" | awk -v dylib_name="$dylib_name" '
        NR > 1 {
            sub(/^[[:space:]]+/, "")
            sub(/ \(compatibility version.*$/, "")
            if ($0 ~ ("/" dylib_name "$")) {
                print
                exit
            }
        }
    ')"

    if [ -z "$current_load_path" ]; then
        echo "ERROR: expected $binary to link $dylib_name" >&2
        return 1
    fi

    if [ "$current_load_path" != "$bundled_load_path" ]; then
        install_name_tool -change "$current_load_path" "$bundled_load_path" "$binary"
        current_load_path="$(otool -L "$binary" | awk -v dylib_name="$dylib_name" '
            NR > 1 {
                sub(/^[[:space:]]+/, "")
                sub(/ \(compatibility version.*$/, "")
                if ($0 ~ ("/" dylib_name "$")) {
                    print
                    exit
                }
            }
        ')"
    fi

    if [ "$current_load_path" != "$bundled_load_path" ]; then
        echo "ERROR: $binary must load $dylib_name from $bundled_load_path, found ${current_load_path:-none}" >&2
        return 1
    fi
}

step "Killing existing instances..."
auth_debug "BEFORE pkill: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"
auth_debug "BEFORE pkill: ALL_KEYS=$(defaults read "$BUNDLE_ID" 2>&1 | grep -E 'auth_|hasCompleted|hasLaunched|currentTier|userShow' || true)"
# Only kill the dev app — never touch Omi Beta (production)
pkill -f "$APP_NAME.app" 2>/dev/null || true
# Note: don't pkill cloudflared here — other agents may have tunnels running on this machine
# Keep an owned local Rust backend alive until a replacement has compiled. The
# backend startup path refreshes Firebase keys before it binds, so restarting it
# for a Swift-only edit adds network-dependent delay and makes a compiler error
# take down an otherwise healthy development server.
if [ -n "${OMI_HARNESS_INSTANCE:-}" ]; then
    substep "Keeping harness desktop-backend (OMI_HARNESS_INSTANCE=${OMI_HARNESS_INSTANCE})"
elif omi_rust_backend_pid_is_alive "$BACKEND_PIDFILE"; then
    OLD_BACKEND_PID="$(omi_rust_backend_read_pid "$BACKEND_PIDFILE")"
    substep "Deferring recorded backend verification until a candidate is ready (PID: $OLD_BACKEND_PID, port $BACKEND_PORT)"
else
    if [ -f "$BACKEND_PIDFILE" ] || [ -f "$BACKEND_METADATA" ]; then
        substep "Removing stale owned backend metadata"
        rm -f "$BACKEND_PIDFILE" "$BACKEND_METADATA"
    fi
fi
sleep 0.5  # Let cfprefsd flush after process death
auth_debug "AFTER pkill: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"
auth_debug "AFTER pkill: ALL_KEYS=$(defaults read "$BUNDLE_ID" 2>&1 | grep -E 'auth_|hasCompleted|hasLaunched|currentTier|userShow' || true)"

# Each non-production app writes to its own bundle-and-launch log path. Never clear a
# machine-global log here: another named QA or qualification bundle may still be running.

if [ "$FAST_ONLY" = "1" ]; then
    # --fast-only already proved that the installed bundle fingerprint matches;
    # scanning unrelated Flutter output and deleting staging bundles can only
    # add latency to this strictly incremental path.
    substep "Fast-only: skipping unrelated bundle cleanup"
else
    step "Cleaning up conflicting app bundles..."
    # Clean old build names from local build dir
    rm -rf "$BUILD_DIR/Omi Computer.app" 2>/dev/null
    rm -rf "$APP_BUNDLE" 2>/dev/null
    CONFLICTING_APPS=(
        "$APP_DESKTOP_PATH"
        "$APP_DOWNLOADS_PATH"
        "$(dirname "$0")/../../app/build/macos/Build/Products/Debug/Omi.app"
        "$(dirname "$0")/../../app/build/macos/Build/Products/Release/Omi.app"
    )
    for app in "${CONFLICTING_APPS[@]}"; do
        if [ -d "$app" ]; then
            substep "Removing: $app"
            rm -rf "$app"
        fi
    done
    # Also remove any stale dev app bundles nested inside Flutter builds.
    find "$(dirname "$0")/../../app/build" -name "$APP_NAME.app" -type d -exec rm -rf {} + 2>/dev/null || true
    # A recursive $HOME scan can take minutes and is unnecessary when relaunching
    # the already-registered named dev bundle. Keep it as an explicit recovery tool
    # for a stale LaunchServices registration instead of charging every edit.
    if [ "${OMI_SCAN_STALE_BUNDLES:-0}" = "1" ] && [ "${OMI_SKIP_STALE_BUNDLE_SCAN:-0}" != "1" ]; then
        substep "Scanning for stale clone bundles (OMI_SCAN_STALE_BUNDLES=1)"
        find "$HOME" -maxdepth 4 -name "$APP_NAME.app" -type d -not -path "$APP_BUNDLE" -not -path "$APP_PATH" 2>/dev/null | while read stale; do
            substep "Removing stale clone: $stale"
            rm -rf "$stale"
        done
    else
        substep "Skipping stale clone scan (set OMI_SCAN_STALE_BUNDLES=1 to enable)"
    fi
fi

if [ -n "${OMI_DESKTOP_API_URL:-}" ]; then
    substep "Skipping tunnel (explicit OMI_DESKTOP_API_URL)"
elif [ "${OMI_SKIP_TUNNEL:-0}" != "1" ]; then
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

if [ "$LOCAL_PROFILE" = true ]; then
    substep "Omi Dev local harness: skipping Backend-Rust/.env copy/source and google-credentials bootstrap"
else
# Copy .env if not present — try sibling dirs, then scaffold from .env.example
if [ ! -f ".env" ] && [ -f "../../backend/.env" ]; then
    cp "../../backend/.env" ".env"
elif [ ! -f ".env" ] && [ -f "../Backend/.env" ]; then
    cp "../Backend/.env" ".env"
fi
if [ ! -f ".env" ] && [ "$YOLO_MODE" != "1" ] && [ "$NAMED_BUNDLE_DEFAULT_DEV_BACKEND" != true ] \
    && { [ "${OMI_SKIP_BACKEND:-0}" != "1" ] || [ -z "${OMI_DESKTOP_API_URL:-}" ]; }; then
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
    echo "Or just use the development backend (no setup needed):"
    echo "  ./run.sh --yolo"
    echo "==========================="
    exit 1
fi

# Symlink google-credentials.json if not present
if [ ! -f "google-credentials.json" ] && [ -f "../../backend/google-credentials.json" ]; then
    ln -sf "../../backend/google-credentials.json" "google-credentials.json"
elif [ ! -f "google-credentials.json" ] && [ -f "../Backend/google-credentials.json" ]; then
    ln -sf "../Backend/google-credentials.json" "google-credentials.json"
fi

# Read environment from .env (skip if missing — yolo mode doesn't need it)
if [ -f "$BACKEND_DIR/.env" ]; then
    set -a; source "$BACKEND_DIR/.env"; set +a
fi
if [ "$YOLO_MODE" = "1" ] || [ "$NAMED_BUNDLE_DEFAULT_DEV_BACKEND" = true ]; then
    apply_yolo_env
fi

# A checked-in/local `.env` commonly contains PORT=10201. The worktree-derived
# selection above remains authoritative so the child process, probes, and
# ownership metadata all use the same isolated port.
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
fi # end non-local profile .env/credential bootstrap

# Validate FIREBASE_PROJECT_ID (required unless yolo mode — no local backend)
if [ -z "$FIREBASE_PROJECT_ID" ] && [ "${OMI_SKIP_BACKEND:-0}" != "1" ]; then
    echo "ERROR: FIREBASE_PROJECT_ID is not set."
    echo ""
    echo "  Add to $BACKEND_DIR/.env:"
    echo "    FIREBASE_PROJECT_ID=based-hardware       # prod Firestore"
    echo "    FIREBASE_PROJECT_ID=based-hardware-dev   # dev Firestore"
    exit 1
fi
if [ -n "$FIREBASE_AUTH_PROJECT_ID" ]; then
    substep "Auth project: tokens validated against $FIREBASE_AUTH_PROJECT_ID, Firestore on $FIREBASE_PROJECT_ID"
fi
substep "Firebase project: $FIREBASE_PROJECT_ID | Backend port: $BACKEND_PORT"
cd - > /dev/null

# ─── Start Rust backend ───────────────────────────────────────────────
if [ "${OMI_SKIP_BACKEND:-0}" != "1" ]; then
    cd "$BACKEND_DIR"
    RUST_BACKEND_PROFILE="$(omi_rust_backend_profile)"
    RUST_BACKEND_BINARY="$(omi_rust_backend_binary "$BACKEND_DIR" "$RUST_BACKEND_PROFILE")"
    OLD_BACKEND_PID=""
    if omi_rust_backend_pid_is_alive "$BACKEND_PIDFILE"; then
        OLD_BACKEND_PID="$(omi_rust_backend_read_pid "$BACKEND_PIDFILE")"
        # A pidfile alone is never authority to signal a process: PIDs can be
        # reused after a crash. Require the recorded process-start identity
        # before a later replacement may stop it. This intentionally does not
        # require the requested profile/configuration to match: a known-owned
        # debug process must be safely replaceable by an explicit release run.
        if ! omi_rust_backend_pid_matches_metadata "$BACKEND_METADATA" "$OLD_BACKEND_PID"; then
            substep "Ignoring unverified Rust backend pidfile (PID: $OLD_BACKEND_PID)"
            rm -f "$BACKEND_PIDFILE" "$BACKEND_METADATA"
            OLD_BACKEND_PID=""
        fi
    fi

    # The local harness already owns an isolated debug backend. Do not compete
    # for its port or replace its process from the app launcher.
    if [ -n "${OMI_HARNESS_INSTANCE:-}" ]; then
        substep "Reusing harness desktop-backend (instance $OMI_HARNESS_INSTANCE)"
    elif [ -n "$OLD_BACKEND_PID" ] \
        && omi_rust_backend_metadata_matches "$BACKEND_METADATA" "$RUST_BACKEND_PROFILE" "$RUST_BACKEND_BINARY" "$BACKEND_PORT" \
        && ! omi_rust_backend_sources_are_stale "$BACKEND_DIR" "$RUST_BACKEND_BINARY" \
        && ! omi_rust_backend_config_is_newer "$BACKEND_DIR" "$BACKEND_PIDFILE" \
        && omi_rust_backend_pid_listens_on_port "$OLD_BACKEND_PID" "$BACKEND_PORT" \
        && omi_rust_backend_health_check "$BACKEND_PORT"; then
        BACKEND_REUSED_PID="$OLD_BACKEND_PID"
        substep "Reusing healthy $RUST_BACKEND_PROFILE Rust backend (PID: $BACKEND_REUSED_PID, port $BACKEND_PORT)"
    else
        # Compile before stopping the current owned backend. A Rust compiler
        # error must leave the developer's last healthy server available.
        if omi_rust_backend_sources_are_stale "$BACKEND_DIR" "$RUST_BACKEND_BINARY"; then
            step "Building Rust backend (cargo build --locked, $RUST_BACKEND_PROFILE)..."
            if [ "$RUST_BACKEND_PROFILE" = "release" ]; then
                cargo build --locked --release
            else
                cargo build --locked
            fi
        fi

        if [ ! -x "$RUST_BACKEND_BINARY" ]; then
            echo "ERROR: Rust backend build did not produce $RUST_BACKEND_BINARY" >&2
            exit 1
        fi

        if [ -n "$OLD_BACKEND_PID" ]; then
            substep "Replacing owned Rust backend after successful build (PID: $OLD_BACKEND_PID)"
            omi_rust_backend_stop_owned "$BACKEND_PIDFILE" "$BACKEND_METADATA"
        fi

        # Fail loud (don't clobber) if our derived port is held by a different
        # worktree. The pidfile only grants ownership over the process above.
        PORT_HOLDER="$(lsof -ti tcp:"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null | head -1)"
        if [ -n "$PORT_HOLDER" ]; then
            echo "ERROR: backend port $BACKEND_PORT (instance '$OMI_INSTANCE') is already in use by pid $PORT_HOLDER:"
            echo "  $(ps -o command= -p "$PORT_HOLDER" 2>/dev/null)"
            echo "  Another worktree probably owns it. Stop that process, or run with PORT=<free> / OMI_INSTANCE=<name>."
            exit 1
        fi

        # Backend stdout is part of launch diagnostics, but must never share a
        # file with a Swift named bundle or another QA run.
        SAFE_BUNDLE_ID="$(printf '%s' "$BUNDLE_ID" | tr -c 'A-Za-z0-9._-' '-')"
        BACKEND_LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-${SAFE_BUNDLE_ID}-backend.XXXXXX")"
        chmod 700 "$BACKEND_LOG_DIR"
        BACKEND_LOG_FILE="$BACKEND_LOG_DIR/backend.log"

        step "Starting Rust backend ($RUST_BACKEND_PROFILE)..."
        "$RUST_BACKEND_BINARY" >>"$BACKEND_LOG_FILE" 2>&1 &
        BACKEND_PID=$!
        printf '%s\n' "$BACKEND_PID" > "$BACKEND_PIDFILE"
        substep "Backend log: $BACKEND_LOG_FILE"

        step "Waiting for backend to start..."
        BACKEND_READY=0
        for i in {1..30}; do
            if omi_rust_backend_health_check "$BACKEND_PORT"; then
                BACKEND_READY=1
                substep "Backend is ready!"
                break
            fi
            if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
                echo "ERROR: Backend failed to start. Check $BACKEND_DIR/.env and credentials."
                omi_rust_backend_stop_owned "$BACKEND_PIDFILE" "$BACKEND_METADATA"
                exit 1
            fi
            sleep 0.5
        done
        if [ "$BACKEND_READY" != "1" ]; then
            echo "ERROR: Backend did not become healthy on port $BACKEND_PORT. Check $BACKEND_LOG_FILE" >&2
            omi_rust_backend_stop_owned "$BACKEND_PIDFILE" "$BACKEND_METADATA"
            exit 1
        fi
        omi_rust_backend_write_metadata \
            "$BACKEND_METADATA" "$RUST_BACKEND_PROFILE" "$RUST_BACKEND_BINARY" "$BACKEND_PORT" "$BACKEND_PID"
    fi
    cd - > /dev/null
else
    substep "Skipping backend (OMI_SKIP_BACKEND=1) — using OMI_DESKTOP_API_URL"
fi

# Wait only for SwiftPM instances building THIS checkout. Parallel worktrees
# have their own .build scratch dirs and SwiftPM locks its shared caches, so
# other worktrees' builds (including SourceKit-LSP indexing builds, which
# respawn continuously and would starve a global wait forever) don't block us.
while true; do
    SWIFTPM_BLOCKING=""
    for _pid in $(pgrep -f "swift-build|swift-package" 2>/dev/null); do
        # SourceKit-LSP indexing builds use their own scratch dir
        # (.build/index-build) and respawn continuously — never wait on them.
        if ps -p "$_pid" -o command= 2>/dev/null | grep -q "prepare-for-indexing\|index-build"; then
            continue
        fi
        _pcwd=$(lsof -a -p "$_pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
        case "$_pcwd" in
            "$SCRIPT_DIR"*) SWIFTPM_BLOCKING="$_pid"; break ;;
        esac
    done
    if [ -z "$SWIFTPM_BLOCKING" ]; then
        break
    fi
    step "Waiting for this checkout's SwiftPM instance (pid $SWIFTPM_BLOCKING) to finish..."
    sleep 2
done

FAST_BUNDLE=0
FAST_BUNDLE_REASON=""

step "Checking reusable development bundle..."
resolve_signing_identity
FAST_BUNDLE_FINGERPRINT="$(fast_bundle_fingerprint)"
FAST_BUNDLE_REASON="$(omi_fast_bundle_eligibility_reason "$APP_PATH" "$FAST_BUNDLE_STAMP" "$FAST_BUNDLE_FINGERPRINT")"
if [ "$FORCE_FULL_BUNDLE" = "1" ]; then
    FAST_BUNDLE_REASON="full_requested"
    substep "Full bundle requested (--full or OMI_FORCE_FULL_BUNDLE=1)"
elif [ "$FAST_BUNDLE_REASON" != "reusable" ]; then
    substep "Fast bundle unavailable: $FAST_BUNDLE_REASON"
    if [ "$FAST_ONLY" = "1" ]; then
        fail_fast_only "$FAST_BUNDLE_REASON"
    fi
else
    FAST_BUNDLE=1
    substep "Fast path: reusing installed bundle at $APP_PATH"
fi

step "Building Rust agent runtime..."
cargo build --manifest-path "$SCRIPT_DIR/../Cargo.toml" -p omi-agent-runtime --locked
AGENT_RUNTIME_BINARY="$SCRIPT_DIR/../target/debug/omi-agent-runtime"
if [ ! -x "$AGENT_RUNTIME_BINARY" ]; then
    echo "ERROR: Rust agent runtime missing at $AGENT_RUNTIME_BINARY" >&2
    exit 1
fi

if [ "$FAST_BUNDLE" = "1" ]; then
    "$SCRIPT_DIR/scripts/generate-desktop-core-bindings.sh"
    step "Building Swift app (swift build -c debug)..."
    xcrun swift build -c debug --package-path Desktop -q

    step "Patching installed app executable..."
    PATCHED_BINARY="$(mktemp "$APP_PATH/Contents/MacOS/.omi-fast-executable.XXXXXX")"
    cp -f "Desktop/.build/debug/$BINARY_NAME" "$PATCHED_BINARY"
    chmod +x "$PATCHED_BINARY"
    install_name_tool -add_rpath "@executable_path/../Frameworks" "$PATCHED_BINARY" 2>/dev/null || true
    rewrite_bundled_dylib_load_path "$PATCHED_BINARY" "libwebp.7.dylib"
    mv -f "$PATCHED_BINARY" "$APP_PATH/Contents/MacOS/$BINARY_NAME"
    cp -f "$AGENT_RUNTIME_BINARY" "$APP_PATH/Contents/Resources/Omi Computer_Omi Computer.bundle/omi-agent-runtime"
    chmod +x "$APP_PATH/Contents/Resources/Omi Computer_Omi Computer.bundle/omi-agent-runtime"
    if [ "$LOCAL_PROFILE" = true ]; then
        EFFECTIVE_API_URL="$OMI_DESKTOP_API_URL"
        omi_write_local_profile_env "$APP_PATH/Contents/Resources/.env"
        substep "Refreshed local-profile bundle environment"
    else
        update_app_desktop_api_url "$APP_PATH/Contents/Resources/.env"
    fi

    step "Signing updated app with hardened runtime..."
    sign_app_bundle "$APP_PATH" false
    reset_local_profile_keychain_state
else
step "Checking schema docs..."
if [ -f scripts/check_schema_docs.sh ]; then
    bash scripts/check_schema_docs.sh || substep "Schema docs check failed (non-fatal)"
fi

"$SCRIPT_DIR/scripts/generate-desktop-core-bindings.sh"
step "Building Swift app (swift build -c debug)..."
xcrun swift build -c debug --package-path Desktop -q

auth_debug "AFTER swift build: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"

step "Creating app bundle..."
substep "Removing prior bundle (if any)"
rm -rf "$APP_BUNDLE"
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
    mkdir -p "$APP_BUNDLE/Contents/Frameworks"
    rm -f "$APP_BUNDLE/Contents/Frameworks/libwebp.7.dylib" "$APP_BUNDLE/Contents/Frameworks/libsharpyuv.0.dylib"
    cp -f "$WEBP_LIB" "$APP_BUNDLE/Contents/Frameworks/libwebp.7.dylib"
    # Find libsharpyuv (libwebp dependency)
    SHARPYUV_LIB="$(dirname "$WEBP_LIB")/libsharpyuv.0.dylib"
    if [ -f "$SHARPYUV_LIB" ]; then
        cp -f "$SHARPYUV_LIB" "$APP_BUNDLE/Contents/Frameworks/libsharpyuv.0.dylib"
        install_name_tool -id "@rpath/libsharpyuv.0.dylib" "$APP_BUNDLE/Contents/Frameworks/libsharpyuv.0.dylib"
    fi
    install_name_tool -id "@rpath/libwebp.7.dylib" "$APP_BUNDLE/Contents/Frameworks/libwebp.7.dylib"
    rewrite_bundled_dylib_load_path "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME" "libwebp.7.dylib"
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
if [ "$LOCAL_PROFILE" = true ] && [ -f "Desktop/Sources/GoogleService-Info-Local.plist" ]; then
    cp -f Desktop/Sources/GoogleService-Info-Local.plist "$APP_BUNDLE/Contents/Resources/GoogleService-Info.plist"
elif [ -f "Desktop/Sources/GoogleService-Info-Dev.plist" ]; then
    cp -f Desktop/Sources/GoogleService-Info-Dev.plist "$APP_BUNDLE/Contents/Resources/GoogleService-Info.plist"
else
    cp -f Desktop/Sources/GoogleService-Info.plist "$APP_BUNDLE/Contents/Resources/"
fi
/usr/libexec/PlistBuddy -c "Set :BUNDLE_ID $BUNDLE_ID" "$APP_BUNDLE/Contents/Resources/GoogleService-Info.plist" 2>/dev/null || true

# Copy resource bundle (contains app assets like permissions.gif, herologo.png, etc.)
RESOURCE_BUNDLE="Desktop/.build/arm64-apple-macosx/debug/Omi Computer_Omi Computer.bundle"
if [ -d "$RESOURCE_BUNDLE" ]; then
    substep "Copying resource bundle ($(du -sh "$RESOURCE_BUNDLE" 2>/dev/null | cut -f1))"
    macos_copy_tree "$RESOURCE_BUNDLE" "$APP_BUNDLE/Contents/Resources/$(basename "$RESOURCE_BUNDLE")"
fi

substep "Copying Rust agent runtime"
mkdir -p "$APP_BUNDLE/Contents/Resources/Omi Computer_Omi Computer.bundle"
cp -f "$AGENT_RUNTIME_BINARY" "$APP_BUNDLE/Contents/Resources/Omi Computer_Omi Computer.bundle/omi-agent-runtime"
chmod +x "$APP_BUNDLE/Contents/Resources/Omi Computer_Omi Computer.bundle/omi-agent-runtime"

substep "Copying .env.app"
if [ "$LOCAL_PROFILE" = true ]; then
    EFFECTIVE_API_URL="$OMI_DESKTOP_API_URL"
    omi_write_local_profile_env "$APP_BUNDLE/Contents/Resources/.env"
    substep "Omi Dev local harness .env contains localhost endpoints/Auth emulator bootstrap only"
else
if [ -f ".env.app.dev" ]; then
    cp -f .env.app.dev "$APP_BUNDLE/Contents/Resources/.env"
elif [ -f ".env.app" ]; then
    cp -f .env.app "$APP_BUNDLE/Contents/Resources/.env"
else
    touch "$APP_BUNDLE/Contents/Resources/.env"
fi
update_app_desktop_api_url "$APP_BUNDLE/Contents/Resources/.env"
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
# Bootstrap OMI_PYTHON_API_URL — main Omi Python backend (auth, subscriptions, payments, transcription).
# Do NOT fall back to OMI_DESKTOP_API_URL — that's the Rust desktop-backend which doesn't serve these routes.
# If the caller set OMI_PYTHON_API_URL (for example --yolo), it must override copied .env values.
PYTHON_API_URL="${OMI_PYTHON_API_URL:-}"
if [ -z "$PYTHON_API_URL" ] && [ -f "$BACKEND_DIR/.env" ]; then
    PYTHON_API_URL=$(grep "^OMI_PYTHON_API_URL=" "$BACKEND_DIR/.env" | head -1 | cut -d= -f2-)
fi
if [ -z "$PYTHON_API_URL" ]; then
    PYTHON_API_URL="https://api.omi.me"
    substep "OMI_PYTHON_API_URL not set — defaulting to production: $PYTHON_API_URL"
fi
if grep -q "^OMI_PYTHON_API_URL=" "$APP_BUNDLE/Contents/Resources/.env"; then
    sed -i '' "s|^OMI_PYTHON_API_URL=.*|OMI_PYTHON_API_URL=$PYTHON_API_URL|" "$APP_BUNDLE/Contents/Resources/.env"
else
    echo "OMI_PYTHON_API_URL=$PYTHON_API_URL" >> "$APP_BUNDLE/Contents/Resources/.env"
fi
substep "Set OMI_PYTHON_API_URL=$PYTHON_API_URL"
fi # end non-local .env.app merge

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

step "Preparing bundled native dependencies..."
"$(dirname "$0")/scripts/prepare-desktop-bundle-native-deps.sh" "$APP_BUNDLE"

step "Removing extended attributes (xattr -cr)..."
# SwiftPM copies some dylibs (libsharpyuv, libwebp) with read-only perms,
# which makes `xattr -cr` fail with EACCES. Make the bundle writable first.
chmod -R u+w "$APP_BUNDLE"
xattr -cr "$APP_BUNDLE"

step "Signing app with hardened runtime..."
sign_app_bundle "$APP_BUNDLE" true

step "Removing quarantine attributes..."
chmod -R u+w "$APP_BUNDLE"
xattr -cr "$APP_BUNDLE"

step "Auditing app bundle dependencies..."
"$(dirname "$0")/scripts/audit-desktop-bundle-deps.sh" "$APP_BUNDLE"

step "Installing to /Applications/..."
# Install to /Applications/ so "Quit & Reopen" (after granting screen recording
# permission) launches the correct binary instead of a stale copy elsewhere.
rm -rf "$APP_PATH"
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

# Agent preparation may stage the universal Node executable after the initial
# check. Stamp the completed packaged inputs, not the pre-bootstrap state.
FAST_BUNDLE_FINGERPRINT="$(fast_bundle_fingerprint)"
omi_fast_bundle_write_stamp "$FAST_BUNDLE_STAMP" "$FAST_BUNDLE_FINGERPRINT"
substep "Recorded reusable bundle fingerprint"

reset_local_profile_keychain_state

if [ "$IS_NAMED_BUNDLE" = true ] && [ "${OMI_SKIP_AUTH_SEED:-0}" != "1" ]; then
    step "Seeding auth from Omi Dev..."
    if AUTH_CACHE="$(mktemp "${TMPDIR:-/tmp}/omi-desktop-auth.XXXXXX")"; then
        if ./scripts/omi-auth-dump.sh com.omi.desktop-dev "$AUTH_CACHE"; then
            # Pass the just-installed app path so seed can resolve Team ID and
            # clear any prior CLI-written Keychain item (apple-tool: partition).
            # Tokens are seeded into UserDefaults; the app migrates them into
            # Keychain on launch with the correct teamid: partition (no prompt).
            if ./scripts/omi-auth-seed.sh "$BUNDLE_ID" "$AUTH_CACHE" "$APP_PATH"; then
                auth_debug "AFTER auth seed: auth_isSignedIn=$(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"
            else
                echo "Warning: could not seed auth into $BUNDLE_ID. Launching cold."
            fi
        else
            echo "Warning: could not seed auth from Omi Dev. Launching cold."
        fi
        rm -f "$AUTH_CACHE"
        AUTH_CACHE=""
    else
        echo "Warning: could not create temporary auth cache. Launching cold."
    fi
fi

if [ "$IS_NAMED_BUNDLE" = true ] && [ "${OMI_SKIP_SETTINGS_SEED:-0}" != "1" ]; then
    step "Seeding shortcuts/settings from Omi Dev..."
    if ./scripts/omi-settings-seed.sh "$BUNDLE_ID" com.omi.desktop-dev; then
        auth_debug "AFTER settings seed: shortcut_askOmiEnabled=$(defaults read "$BUNDLE_ID" shortcut_askOmiEnabled 2>&1 || true)"
        auth_debug "AFTER settings seed: devLazyPermissionsEnabled=$(defaults read "$BUNDLE_ID" devLazyPermissionsEnabled 2>&1 || true)"
    else
        echo "Warning: could not seed shortcuts/settings from Omi Dev. Continuing with bundle defaults."
    fi
fi

if [ "$IS_NAMED_BUNDLE" = true ] && [ "${OMI_SKIP_REWIND_SEED:-0}" != "1" ]; then
    step "Seeding Rewind history from Omi Dev..."
    if ! ./scripts/omi-rewind-seed.sh "$BUNDLE_ID"; then
        echo "Warning: could not seed Rewind history into $BUNDLE_ID. Launching with its existing local profile."
    fi
fi

fi # full bundle path

step "Starting app..."

# Print summary
NOW=$(date +%s.%N)
TOTAL_TIME=$(echo "$NOW - $SCRIPT_START_TIME" | bc)
printf "  └─ done (%.2fs)\n" "$(echo "$NOW - $STEP_START_TIME" | bc)"
echo ""
echo "=== Services Running (total: ${TOTAL_TIME%.*}s) ==="
if [ -n "$BACKEND_PID" ]; then
    echo "Backend:  http://localhost:$BACKEND_PORT (PID: $BACKEND_PID)"
elif [ -n "$BACKEND_REUSED_PID" ]; then
    echo "Backend:  http://localhost:$BACKEND_PORT (reused PID: $BACKEND_REUSED_PID)"
elif [ -n "${OMI_HARNESS_INSTANCE:-}" ] && [ "${OMI_SKIP_BACKEND:-0}" != "1" ]; then
    echo "Backend:  http://localhost:$BACKEND_PORT (reused harness instance: $OMI_HARNESS_INSTANCE)"
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

LAUNCH_MODE="full"
[ "$FAST_BUNDLE" = "1" ] && LAUNCH_MODE="fast"
PROFILE_ROOT="$HOME/Library/Application Support/Omi"
if [ "$IS_NAMED_BUNDLE" = true ]; then
    PROFILE_ROOT="$HOME/Library/Application Support/Omi Dev Bundles/$BUNDLE_ID"
fi
printf 'launch_mode=%s fast_reason=%s bundle_id=%s profile_root=%q\n' \
    "$LAUNCH_MODE" "$FAST_BUNDLE_REASON" "$BUNDLE_ID" "$PROFILE_ROOT"

auth_debug "BEFORE launch: $(defaults read "$BUNDLE_ID" auth_isSignedIn 2>&1 || true)"
if [ "${#AUTOMATION_ARGS[@]}" -gt 0 ]; then
    open "$APP_PATH" --args "${AUTOMATION_ARGS[@]}" || "$APP_PATH/Contents/MacOS/$BINARY_NAME" "${AUTOMATION_ARGS[@]}" &
else
    open "$APP_PATH" || "$APP_PATH/Contents/MacOS/$BINARY_NAME" &
fi

# Launch finished — free this worktree's lock so other checkouts (and a later
# rebuild here) are not blocked by the long-running wait below. Kept through
# open so a same-worktree contender cannot rm -rf $APP_PATH mid-launch.
omi_run_sh_release_build_lock
substep "Released per-worktree build lock"

if [ "$NO_WAIT" = "1" ]; then
    echo "Detached launch complete (backend and tunnel are externally owned)."
    exit 0
fi

# Keep script running until Ctrl+C
echo "Press Ctrl+C to stop all services..."
if [ -n "$BACKEND_PID" ]; then
    wait "$BACKEND_PID"
else
    # No backend — just wait for user to Ctrl+C
    while true; do sleep 60; done
fi
