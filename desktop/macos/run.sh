#!/bin/bash
set -e

# Force C locale for numeric formatting so `printf %f` accepts the
# dot-decimal values produced by `bc` even when the user's shell runs in
# a non-English locale (e.g. de_DE.UTF-8 expects a comma separator).
export LC_NUMERIC=C

# Codex, launchd, and other non-login shells may not inherit Homebrew's bin
# directory. Keep the launcher self-contained so tools such as pkg-config are
# discoverable on both Apple Silicon and Intel Macs.
# shellcheck source=launcher-bootstrap.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/launcher-bootstrap.sh"
omi_configure_homebrew_path

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
  OMI_SKIP_BACKEND=1      Skip starting Python backend (use remote backend via OMI_DESKTOP_API_URL)
  OMI_SKIP_TUNNEL=1        Skip Cloudflare tunnel (use OMI_DESKTOP_API_URL from .env directly)
  PORT=10201                Desktop backend port (default: 10201, never use 8080)
  OMI_APP_NAME="Omi Dev"   App name (default: "Omi Dev")
  OMI_SKIP_AUTH_SEED=1     Do not copy auth/onboarding from Omi Dev into named bundles
  OMI_SKIP_SETTINGS_SEED=1  Do not copy shortcuts/settings from Omi Dev into named bundles
  OMI_SKIP_REWIND_SEED=1    Do not copy the local Rewind history into a new named bundle
  OMI_FORCE_REWIND_SEED=1   Replace an existing named-bundle Rewind history with a fresh Omi Dev snapshot
  OMI_DEV_EAGER_PERMISSIONS=1  Preserve eager mic/screen/file startup behavior in named bundles
  OMI_PYTHON_API_URL="..."  Python backend URL (explicit override; named bundles default to dev)
  OMI_JIT_QA_TARGET="..."   omi-jit-qa only: local-dev-gcp, deployed-dev, or cloud-qa atomic endpoint tuple
  OMI_SIGN_IDENTITY="..."  Code signing identity (auto-detected if not set)
  OMI_FORCE_FULL_BUNDLE=1  Rebuild the complete app bundle on this launch
  OMI_SCAN_STALE_BUNDLES=1  Remove stale same-named app bundles under $HOME (recovery only)
  OMI_ENABLE_LOCAL_AUTOMATION=1   Force the automation bridge on (auto-on for non-prod bundles; see scripts/omi-ctl)
  OMI_DISABLE_LOCAL_AUTOMATION=1  Run a dev build "clean" with the bridge off
  OMI_AUTOMATION_PORT=47777       Bridge port (set per bundle when running several at once)
  OMI_AUTOMATION_UI_MODE=quiet    Window presentation for automation: quiet, interactive, or normal
  OMI_FORCE_CANONICAL_MEMORY_ATLAS=1  Non-production-only local QA override for the canonical atlas rollout gate
  OMI_DESKTOP_LOCAL_PROFILE=1     Local harness profile; localhost endpoints/Auth emulator only

Required files:
  ../../backend/.env         Environment variables (copy from ../../backend/.env.template)
  ../../backend/google-credentials.json  GCP service account key

Required tools:
  xcrun/swift, python3, uv, npm, node, codesign, cloudflared (unless skipped)

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
    # `--yolo` supplies remote-development defaults, but must not discard an
    # explicitly targeted backend. Named QA and fault-injection bundles use
    # these overrides to exercise a chosen service revision without requiring
    # a local desktop backend or .env file.
    export OMI_DESKTOP_API_URL="${OMI_DESKTOP_API_URL:-https://desktop-backend-dt5lrfkkoa-uc.a.run.app}"
    export OMI_PYTHON_API_URL="${OMI_PYTHON_API_URL:-https://api.omiapi.com}"
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
    echo "  No local Python backend, no local auth, no tunnel."
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
# shellcheck source=jit-qa-target.sh
source "$SCRIPT_DIR/scripts/jit-qa-target.sh"

# Reject an invalid reserved-bundle request before dev-instance creates a
# scratch directory or the launcher acquires a build lock.
REQUESTED_LOCAL_PROFILE=false
[ "${OMI_DESKTOP_LOCAL_PROFILE:-0}" = "1" ] && REQUESTED_LOCAL_PROFILE=true
omi_preflight_jit_qa_launch_request \
    "${OMI_APP_NAME:-}" "${OMI_BUNDLE_ID:-}" "$YOLO_MODE" "$REQUESTED_LOCAL_PROFILE" || exit $?
if [ -n "${OMI_JIT_QA_TARGET:-}" ]; then
    omi_jit_qa_set_exact_tuple || exit $?
fi

# The backend .env is shell-sourced later and the selected app env is copied
# into the bundle. Reject stale/mixed source tuples before dev-instance creates
# scratch state or the launcher acquires a build lock.
EARLY_BACKEND_DIR="$(cd "$SCRIPT_DIR/../../backend" && pwd)"
omi_preflight_jit_qa_config_file "$EARLY_BACKEND_DIR/.env" || exit $?
if [ -f "$SCRIPT_DIR/.env.app.dev" ]; then
    omi_preflight_jit_qa_config_file "$SCRIPT_DIR/.env.app.dev" || exit $?
elif [ -f "$SCRIPT_DIR/.env.app" ]; then
    omi_preflight_jit_qa_config_file "$SCRIPT_DIR/.env.app" || exit $?
fi

# shellcheck source=python-desktop-backend-dev.sh
source "$SCRIPT_DIR/scripts/python-desktop-backend-dev.sh"

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

# Gate-G bundle routing is a whole-tuple authority. Revalidate the fully
# derived app identity, then reapply after .env loads below.
omi_prepare_jit_qa_target "$APP_NAME" "$BUNDLE_ID" "$YOLO_MODE" derived "$LOCAL_PROFILE" || exit $?

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
# after sourcing backend/.env below so repository-local defaults cannot
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
# Agent runtime source (staged into the app bundle at Resources/agent below).
# Without this, `[ -d "$AGENT_DIR/dist" ]` tests an empty path and the agent
# copy is silently skipped → app shows "AI components missing".
AGENT_DIR="$SCRIPT_DIR/agent"
AGENT_PACKAGED_NODE_MODULES="$SCRIPT_DIR/.harness/agent-runtime/agent-node_modules"
PI_MONO_PACKAGED_NODE_MODULES="$SCRIPT_DIR/.harness/agent-runtime/pi-mono-extension-node_modules"
APP_DESKTOP_PATH="$HOME/Desktop/$APP_NAME.app"
APP_DOWNLOADS_PATH="$HOME/Downloads/$APP_NAME.app"
SIGN_IDENTITY="${OMI_SIGN_IDENTITY:-}"
# Stable self-signed fallback identity for machines with no Apple certificate.
# See desktop/macos/AGENTS.md → Local Code Signing for how to create it.
OMI_LOCAL_DEV_SIGN_IDENTITY="Omi Local Dev Signing"
SIGN_IDENTITY_TEAM_ID=""
SIGN_IDENTITY_TEAM_ID_RESOLVED_FOR=""
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
AUTOMATION_UI_MODE="$(derive_omi_automation_ui_mode "$IS_NAMED_BUNDLE" "${OMI_AUTOMATION_UI_MODE:-}")" || exit 2
# An external harness may request an ownership proof for a detached `open`
# launch. The token is passed as an app argument (and therefore visible in the
# spawned process command) and copied into the owner-only launch signal. It is
# intentionally opt-in so ordinary local launches keep their existing behavior.
DESKTOP_LAUNCH_TOKEN="${OMI_DESKTOP_LAUNCH_TOKEN:-}"
if [[ -n "$DESKTOP_LAUNCH_TOKEN" && ! "$DESKTOP_LAUNCH_TOKEN" =~ ^[A-Za-z0-9_-]{16,128}$ ]]; then
    echo "ERROR: OMI_DESKTOP_LAUNCH_TOKEN must be 16-128 URL-safe characters" >&2
    exit 2
fi
AUTOMATION_ARGS=("--automation-port=$AUTOMATION_PORT" "--automation-capture-root=$AUTOMATION_CAPTURE_ROOT")
if [ "$AUTOMATION_UI_MODE" != "normal" ]; then
    AUTOMATION_ARGS+=("--automation-ui=$AUTOMATION_UI_MODE")
fi
if [ "${OMI_ENABLE_LOCAL_AUTOMATION:-0}" = "1" ]; then
    AUTOMATION_ARGS=(--automation-bridge "${AUTOMATION_ARGS[@]}")
fi

# Backend configuration
BACKEND_DIR="$(cd "$SCRIPT_DIR/../../backend" && pwd)"
BACKEND_PID=""
BACKEND_REUSED_PID=""
BACKEND_PIDFILE="$OMI_DEV_DIR/python-desktop-backend.pid"
BACKEND_METADATA="$OMI_DEV_DIR/python-desktop-backend.meta"
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

# The local self-signed identity, created without a GUI and without a password prompt.
#
# The documented way to make this identity is Keychain Access -> Certificate Assistant, which
# is a wizard: unusable from CI, from an agent, and from anyone who has not read the doc. The
# ingredients are all stock, so the wizard is not actually required -- /usr/bin/openssl is
# LibreSSL on every Mac and supports the legacy PKCS#12 encoding Apple's importer accepts
# (OpenSSL 3's AES/SHA256 default is rejected with "MAC verification failed").
#
# It lives in its own keychain rather than in login.keychain on purpose. We own that
# keychain's password, so we can unlock it and grant codesign a partition non-interactively --
# which is the entire point, since the login keychain is exactly what we cannot do that to.
# The password protects a throwaway self-signed certificate and nothing else, so it is a
# constant rather than a secret.
OMI_LOCAL_SIGN_KEYCHAIN="$HOME/Library/Keychains/omi-local-dev-signing.keychain-db"
OMI_LOCAL_SIGN_KEYCHAIN_PASSWORD="omi-local-dev"

# Whether an identity can actually be USED here, which is not the same question as whether it
# exists. `security find-identity` lists identities whose private key the keychain may still
# refuse to hand over -- and refuse instantly, with no prompt, in any session that cannot draw
# one. Probing costs one signature on a temp file and turns a failure that used to surface
# after the whole build into a fact known before it starts.
signing_identity_usable() {
    local identity="$1" probe status
    [ -n "$identity" ] || return 1
    probe="$(mktemp "${TMPDIR:-/tmp}/omi-sign-probe.XXXXXX")" || return 1
    cp /usr/bin/true "$probe" 2>/dev/null || { rm -f "$probe"; return 1; }
    codesign --force --sign "$identity" "$probe" >/dev/null 2>&1
    status=$?
    rm -f "$probe"
    return $status
}

# Make the keychain visible to codesign without disturbing the user's search list.
#
# `security list-keychains -s` REPLACES the list rather than appending, so the existing entries
# have to be read and passed back verbatim. They come back one per line, quoted and indented,
# and each path may contain spaces -- so they are collected into an array and re-quoted by the
# shell. Word-splitting them instead corrupts the list, which is not a theoretical concern:
# an earlier version of this function did exactly that and rewrote the user's login keychain
# entry into a nested-quoted path that no longer resolved.
add_keychain_to_search_list() {
    local keychain="$1" line
    local -a current=()
    while IFS= read -r line; do
        line="${line#"${line%%[![:space:]]*}"}"   # strip leading whitespace
        line="${line#\"}"
        line="${line%\"}"
        [ -n "$line" ] || continue
        [ "$line" = "$keychain" ] && return 0     # already present, nothing to do
        current+=("$line")
    done < <(security list-keychains -d user)
    security list-keychains -d user -s "${current[@]}" "$keychain" 2>/dev/null
}

ensure_local_dev_signing_identity() {
    if signing_identity_usable "$OMI_LOCAL_DEV_SIGN_IDENTITY"; then
        return 0
    fi
    if [ -f "$OMI_LOCAL_SIGN_KEYCHAIN" ]; then
        # Present but unusable almost always means "locked since reboot".
        security unlock-keychain -p "$OMI_LOCAL_SIGN_KEYCHAIN_PASSWORD" "$OMI_LOCAL_SIGN_KEYCHAIN" 2>/dev/null
        add_keychain_to_search_list "$OMI_LOCAL_SIGN_KEYCHAIN"
        signing_identity_usable "$OMI_LOCAL_DEV_SIGN_IDENTITY" && return 0
    fi

    step "Creating local signing identity ($OMI_LOCAL_DEV_SIGN_IDENTITY)..."
    local work
    work="$(mktemp -d "${TMPDIR:-/tmp}/omi-local-sign.XXXXXX")" || return 1

    # codeSigning EKU and CA:false are both required, or codesign declines the identity.
    cat > "$work/openssl.cnf" <<EOF
[req]
distinguished_name = dn
x509_extensions = v3
prompt = no
[dn]
CN = $OMI_LOCAL_DEV_SIGN_IDENTITY
[v3]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
EOF

    if ! /usr/bin/openssl req -x509 -newkey rsa:2048 -keyout "$work/key.pem" -out "$work/cert.pem" \
            -days 3650 -nodes -config "$work/openssl.cnf" >/dev/null 2>&1; then
        rm -rf "$work"; return 1
    fi
    if ! /usr/bin/openssl pkcs12 -export -inkey "$work/key.pem" -in "$work/cert.pem" \
            -out "$work/identity.p12" -passout "pass:$OMI_LOCAL_SIGN_KEYCHAIN_PASSWORD" \
            -name "$OMI_LOCAL_DEV_SIGN_IDENTITY" \
            -certpbe PBE-SHA1-3DES -keypbe PBE-SHA1-3DES -macalg sha1 >/dev/null 2>&1; then
        rm -rf "$work"; return 1
    fi

    if [ ! -f "$OMI_LOCAL_SIGN_KEYCHAIN" ]; then
        security create-keychain -p "$OMI_LOCAL_SIGN_KEYCHAIN_PASSWORD" "$OMI_LOCAL_SIGN_KEYCHAIN" 2>/dev/null || { rm -rf "$work"; return 1; }
        # No idle timeout and no lock-on-sleep: a keychain that relocks mid-build reintroduces
        # exactly the interactive prompt this exists to avoid.
        security set-keychain-settings "$OMI_LOCAL_SIGN_KEYCHAIN" 2>/dev/null
    fi
    security unlock-keychain -p "$OMI_LOCAL_SIGN_KEYCHAIN_PASSWORD" "$OMI_LOCAL_SIGN_KEYCHAIN" 2>/dev/null
    security import "$work/identity.p12" -k "$OMI_LOCAL_SIGN_KEYCHAIN" \
        -P "$OMI_LOCAL_SIGN_KEYCHAIN_PASSWORD" -T /usr/bin/codesign -T /usr/bin/security >/dev/null 2>&1
    # The partition list is what lets codesign use the key with no dialog. We can set it here
    # only because this keychain's password is ours.
    security set-key-partition-list -S apple-tool:,apple:,codesign: -s \
        -k "$OMI_LOCAL_SIGN_KEYCHAIN_PASSWORD" "$OMI_LOCAL_SIGN_KEYCHAIN" >/dev/null 2>&1
    add_keychain_to_search_list "$OMI_LOCAL_SIGN_KEYCHAIN"
    rm -rf "$work"

    if signing_identity_usable "$OMI_LOCAL_DEV_SIGN_IDENTITY"; then
        substep "Created $OMI_LOCAL_DEV_SIGN_IDENTITY (self-signed, stable, no prompt)"
        return 0
    fi
    return 1
}

# Which identity this bundle was signed with last time.
#
# **TCC binds every grant to the code requirement at the moment it was granted**, and that
# requirement names the signing certificate. So changing a bundle's signing identity silently
# revokes its Microphone, Screen Recording and Files permissions -- the app then re-prompts on
# every launch and looks broken, with nothing in its own logs to explain why.
#
# That is easy to do by accident: an Apple Development identity that the keychain refuses in one
# session (see the errSecInternalComponent notes) falls back to the self-signed identity, and the
# next build silently switches the bundle over. Remembering the last identity makes the switch
# deliberate rather than accidental, and loud when it has to happen anyway.
signing_identity_stamp_path() {
    [ "$IS_NAMED_BUNDLE" = true ] || return 1
    printf '%s/Library/Application Support/Omi Dev Bundles/%s/.signing-identity\n' "$HOME" "$BUNDLE_ID"
}

remembered_signing_identity() {
    local stamp
    stamp="$(signing_identity_stamp_path)" || return 1
    [ -f "$stamp" ] || return 1
    cat "$stamp"
}

remember_signing_identity() {
    local stamp
    stamp="$(signing_identity_stamp_path)" || return 0
    mkdir -p "$(dirname "$stamp")" 2>/dev/null
    printf '%s' "$1" > "$stamp" 2>/dev/null || true
}

resolve_signing_identity() {
    if [ -n "$SIGN_IDENTITY" ]; then
        return
    fi
    local candidate
    # An identity this bundle already wears wins over a "better" one, because switching costs the
    # user every permission they have granted it.
    local remembered
    if remembered="$(remembered_signing_identity)" && [ -n "$remembered" ]; then
        if signing_identity_usable "$remembered"; then
            SIGN_IDENTITY="$remembered"
            substep "Reusing this bundle's existing identity: $SIGN_IDENTITY"
            return
        fi
        echo ""
        echo "  WARNING: this bundle was last signed with \"$remembered\", which is not usable"
        echo "           here. Signing it with anything else RESETS ITS PERMISSIONS: macOS binds"
        echo "           Microphone, Screen Recording and Files grants to the signing certificate,"
        echo "           so the app will prompt for all of them again on next launch."
        echo "           The remedy is the same one printed below."
    fi

    # Prefer a real Apple identity so local permissions stay stable AND the bundle carries a
    # Team ID. Each candidate is probed rather than merely found: an Apple Development identity
    # whose key the keychain will not release is worse than useless, because picking it makes
    # the build fail an hour of work later instead of falling back now.
    for candidate in \
        "$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | sed 's/.*"\(.*\)"/\1/')" \
        "$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | sed 's/.*"\(.*\)"/\1/')"
    do
        [ -n "$candidate" ] || continue
        if signing_identity_usable "$candidate"; then
            SIGN_IDENTITY="$candidate"
            return
        fi
        # Authorization can be granted between one call and the next -- clicking "Allow" on the
        # SecurityAgent dialog authorizes a single use, so a refusal is not necessarily a
        # standing state. Probe once more before writing the identity off, or a dialog answered
        # a moment too late silently costs the build its Team ID.
        sleep 1
        if signing_identity_usable "$candidate"; then
            SIGN_IDENTITY="$candidate"
            return
        fi
        echo ""
        echo "  WARNING: $candidate is present but the keychain refused its key."
        echo "           Falling back to a teamless identity, which is a DOWNGRADE:"
        echo "           the bundle gets no Team ID, so it cannot share Keychain items or"
        echo "           entitlements with the team-scoped builds (Omi Dev, beta, prod) and"
        echo "           needs library validation relaxed to launch."
        echo "           If a keychain dialog is appearing, answer it with \"Always Allow\"."
        echo "           To stop it recurring, grant codesign a standing partition once:"
        echo ""
        echo "             security set-key-partition-list -S apple-tool:,apple:,codesign: -s \\"
        echo "               -l \"$candidate\" ~/Library/Keychains/login.keychain-db"
        echo ""
        echo "           Or force it for this build: OMI_SIGN_IDENTITY=\"$candidate\" ./run.sh"
        echo ""
    done

    # A stable self-signed identity keeps this bundle's own TCC grants, because its designated
    # requirement pins that certificate. Ad-hoc signing has no such requirement and silently
    # drops Screen Recording, so this is preferred over ad-hoc always -- and created on demand
    # rather than waiting for someone to run a GUI wizard.
    if [ "${OMI_SKIP_LOCAL_SIGN_IDENTITY:-0}" != "1" ] && ensure_local_dev_signing_identity; then
        SIGN_IDENTITY="$OMI_LOCAL_DEV_SIGN_IDENTITY"
        substep "Using local self-signed identity: $SIGN_IDENTITY"
        return
    fi

    if [ "${OMI_ALLOW_ADHOC_SIGN:-0}" = "1" ] && [ "$IS_NAMED_BUNDLE" = true ]; then
        SIGN_IDENTITY="-"
        substep "Using ad-hoc signing for named test bundle ($BUNDLE_ID)"
    fi
}

# The Team ID codesign will stamp for the resolved identity ("" when the
# identity carries none). Resolved once per identity: it costs a probe
# signature, and sign_app_bundle runs on both the fast and full lanes.
resolve_signing_identity_team_id() {
    if [ -n "$SIGN_IDENTITY" ] && [ "$SIGN_IDENTITY_TEAM_ID_RESOLVED_FOR" = "$SIGN_IDENTITY" ]; then
        return
    fi
    SIGN_IDENTITY_TEAM_ID="$("$SCRIPT_DIR/scripts/prepare-local-dev-entitlements.sh" \
        --identity-team-id "$SIGN_IDENTITY")"
    SIGN_IDENTITY_TEAM_ID_RESOLVED_FOR="$SIGN_IDENTITY"
}

# Which entitlements a local signature must use. Prints the reason the
# generated local entitlements are required, or nothing when the checked-in
# Desktop/Omi.entitlements are correct as they stand.
#
# Pure decision over already-gathered metadata so it can be exercised directly;
# see tests/test-prepare-local-dev-entitlements.sh.
local_entitlements_fallback_reason() {
    local signing_mode="$1"
    local is_named_bundle="$2"
    local profile_present="$3"
    local profile_team_id="$4"
    local identity_team_id="$5"

    if [ "$signing_mode" = "teamless" ]; then
        # Hardened-runtime library validation cannot match the bundled
        # frameworks without a Team ID, so this bundle needs the generated
        # entitlements whether or not it is a named bundle.
        printf '%s\n' "signing identity has no Team ID; library validation would block the bundled frameworks"
        return 0
    fi
    if [ "$is_named_bundle" = true ]; then
        printf '%s\n' "named bundle IDs are not covered by Omi Dev's provisioning profile"
        return 0
    fi
    if [ "$profile_present" != true ]; then
        return 0
    fi
    if [ -z "$profile_team_id" ]; then
        printf '%s\n' "could not extract profile team ID (security cms failed)"
        return 0
    fi
    if [ "$profile_team_id" != "$identity_team_id" ]; then
        printf '%s\n' "profile team ($profile_team_id) != identity team ($identity_team_id)"
    fi
    return 0
}

fast_bundle_fingerprint() {
    local desktop_api_fingerprint="${OMI_DESKTOP_API_URL:-}"
    local python_api_fingerprint="${OMI_PYTHON_API_URL:-}"
    local auth_api_fingerprint="${OMI_AUTH_API_URL:-}"
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
        "auth-api-url=$auth_api_fingerprint" \
        "jit-qa-target=${OMI_JIT_QA_TARGET:-}" \
        "env-stage=${OMI_ENV_STAGE:-}" \
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
    omi_prepare_jit_qa_target "$APP_NAME" "$BUNDLE_ID" "$YOLO_MODE" refresh "$LOCAL_PROFILE" || exit $?
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


# Every codesign call in this file goes through here.
#
# When signing fails because the *keychain* refused to hand over the private key, the raw
# message is `errSecInternalComponent` — six syllables of nothing, and the failure looks
# identical to a corrupt bundle or a bad identity. It sent one agent down a rabbit hole that
# ended in ad-hoc signing, which is the one fix that silently breaks Rewind capture.
#
# The actual cause is almost always the session, not the certificate: a process launched
# outside the GUI login session (`launchctl managername` reports `Background` rather than
# `Aqua` — CI, an ssh shell, an agent harness, a LaunchDaemon) has no window server, so
# SecurityAgent cannot draw the "codesign wants to use key X" dialog. Rather than hang, the
# Security framework fails the call immediately. The key is present, the keychain is unlocked,
# and the caller is the right user; only the authorization is missing.
#
# So say that, and say the one command that fixes it for good.
omi_codesign() {
    local output status
    output="$(codesign "$@" 2>&1)"
    status=$?
    [ -n "$output" ] && printf '%s\n' "$output"
    if [ $status -ne 0 ] && printf '%s' "$output" | grep -qE 'errSecInternalComponent|interaction is not allowed|User interaction'; then
        echo ""
        echo "ERROR: the keychain refused the signing key (not a bad bundle, not a bad identity)."
        echo ""
        echo "  identity: $SIGN_IDENTITY"
        echo "  session : $(launchctl managername 2>/dev/null || echo unknown)   <- must be Aqua to show a keychain prompt"
        echo ""
        echo "  This shell cannot display the SecurityAgent dialog that would authorize the key,"
        echo "  so macOS fails the request instead of asking. Grant codesign a standing partition"
        echo "  on the key once, from a terminal in the GUI session:"
        echo ""
        echo "    security set-key-partition-list -S apple-tool:,apple:,codesign: -s \\"
        echo "      -l \"$SIGN_IDENTITY\" ~/Library/Keychains/login.keychain-db"
        echo ""
        echo "  Omit -k so it prompts for the keychain password instead of putting it in history."
        echo "  After that this build works from any session, including this one."
        echo ""
        echo "  DO NOT reach for OMI_ALLOW_ADHOC_SIGN=1 here. An ad-hoc signature has no"
        echo "  designated requirement, so the bundle loses its own Screen Recording grant and"
        echo "  Rewind captures nothing — which reads as a broken feature, not a signing problem."
        echo "  See desktop/macos/docs/local-code-signing.md."
        echo ""
        exit 1
    fi
    return $status
}

sign_app_bundle() {
    local bundle="$1"
    local sign_nested="$2"
    local effective_entitlements="Desktop/Omi.entitlements"
    local profile_path="$bundle/Contents/embedded.provisionprofile"
    local local_signing_mode
    local fallback_reason

    resolve_signing_identity

    if [ -z "$SIGN_IDENTITY" ]; then
        echo ""
        echo "ERROR: No signing identity found. Ad-hoc signing causes macOS to reset"
        echo "       Screen Recording permissions for ALL Omi apps (including prod/beta)."
        echo ""
        echo "  Fix: Install an Apple Development certificate in Keychain Access,"
        echo "       or set OMI_SIGN_IDENTITY to a valid identity:"
        echo "       OMI_SIGN_IDENTITY=\"Apple Development: you@example.com\" ./run.sh"
        echo ""
        echo "       With no Apple certificate, create the stable self-signed local"
        echo "       identity once (see desktop/macos/AGENTS.md → Local Code Signing):"
        echo "       \"$OMI_LOCAL_DEV_SIGN_IDENTITY\" is picked up automatically."
        echo ""
        echo "       For named throwaway bundles only, tests may opt into ad-hoc signing."
        echo "       It invalidates that bundle's own Screen Recording grant, so Rewind"
        echo "       captures nothing:"
        echo "       OMI_APP_NAME=\"omi-my-test\" OMI_ALLOW_ADHOC_SIGN=1 ./run.sh"
        echo ""
        exit 1
    fi

    resolve_signing_identity_team_id
    # One authority for both the launch-safety gate and the entitlement choice:
    # a configuration that validates is exactly the one whose mode is used.
    local_signing_mode="$("$SCRIPT_DIR/scripts/prepare-local-dev-entitlements.sh" \
        --validate-identity \
        "$SIGN_IDENTITY" \
        "$SIGN_IDENTITY_TEAM_ID" \
        "$IS_NAMED_BUNDLE" \
        "${OMI_ALLOW_ADHOC_SIGN:-0}")"

    substep "Using identity: $SIGN_IDENTITY (team=${SIGN_IDENTITY_TEAM_ID:-none}, mode=$local_signing_mode)"
    if [ "$sign_nested" = true ]; then
        if [ -d "$bundle/Contents/Frameworks/Sparkle.framework" ]; then
            substep "Signing Sparkle framework"
            omi_codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/Sparkle.framework"
        fi
        if [ -d "$bundle/Contents/Frameworks/Sentry.framework" ]; then
            substep "Signing Sentry framework"
            omi_codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/Sentry.framework"
        fi
        if [ -d "$bundle/Contents/Frameworks/onnxruntime.framework" ]; then
            substep "Signing onnxruntime framework"
            omi_codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/onnxruntime.framework"
        fi
        if [ -f "$bundle/Contents/Frameworks/libsharpyuv.0.dylib" ]; then
            substep "Signing libsharpyuv"
            omi_codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/libsharpyuv.0.dylib"
        fi
        if [ -f "$bundle/Contents/Frameworks/libwebp.7.dylib" ]; then
            substep "Signing libwebp"
            omi_codesign --force --options runtime --sign "$SIGN_IDENTITY" "$bundle/Contents/Frameworks/libwebp.7.dylib"
        fi
        local node_bin="$bundle/Contents/Resources/Omi Computer_Omi Computer.bundle/Contents/Resources/node"
        if [ -f "$node_bin" ]; then
            substep "Signing bundled node binary"
            omi_codesign --force --options runtime --entitlements Desktop/Node.entitlements --sign "$SIGN_IDENTITY" "$node_bin"
        fi
    fi

    # Named bundles deliberately omit Sign in with Apple because their bundle
    # IDs are not covered by Omi Dev's provisioning profile, and a teamless
    # identity additionally needs library validation relaxed.
    local profile_present=false profile_team_id="" profile_plist
    if [ -f "$profile_path" ]; then
        profile_present=true
        profile_plist=$(mktemp /tmp/omi-dev-profile.XXXXXX)
        profile_team_id=$(security cms -D -i "$profile_path" > "$profile_plist" 2>/dev/null && \
            /usr/libexec/PlistBuddy -c "Print :TeamIdentifier:0" "$profile_plist" 2>/dev/null || true)
        rm -f "$profile_plist"
    fi

    fallback_reason="$(local_entitlements_fallback_reason \
        "$local_signing_mode" \
        "$IS_NAMED_BUNDLE" \
        "$profile_present" \
        "$profile_team_id" \
        "$SIGN_IDENTITY_TEAM_ID")"

    if [ -n "$fallback_reason" ]; then
        substep "Local entitlements fallback: $fallback_reason"
        effective_entitlements="$("$SCRIPT_DIR/scripts/prepare-local-dev-entitlements.sh" \
            Desktop/Omi.entitlements \
            "$OMI_DEV_DIR" \
            "$BUNDLE_ID" \
            "$local_signing_mode")"
        rm -f "$profile_path"
    fi

    substep "Signing app bundle"
    omi_codesign --force --options runtime --entitlements "$effective_entitlements" --sign "$SIGN_IDENTITY" "$bundle"
    remember_signing_identity "$SIGN_IDENTITY"
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
# Keep an owned local Python backend alive until a replacement has started. The
# backend startup path refreshes Firebase keys before it binds, so restarting it
# for a Swift-only edit adds network-dependent delay and makes a compiler error
# take down an otherwise healthy development server.
if [ -n "${OMI_HARNESS_INSTANCE:-}" ]; then
    substep "Keeping harness desktop-backend (OMI_HARNESS_INSTANCE=${OMI_HARNESS_INSTANCE})"
elif omi_python_desktop_backend_pid_is_alive "$BACKEND_PIDFILE"; then
    OLD_BACKEND_PID="$(omi_python_desktop_backend_read_pid "$BACKEND_PIDFILE")"
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
# machine-global log here: another named QA bundle may still be running.

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
    substep "Omi Dev local harness: skipping backend/.env copy/source and google-credentials bootstrap"
else
if [ ! -f ".env" ] && [ "$YOLO_MODE" != "1" ] && [ "$NAMED_BUNDLE_DEFAULT_DEV_BACKEND" != true ] \
    && { [ "${OMI_SKIP_BACKEND:-0}" != "1" ] || [ -z "${OMI_DESKTOP_API_URL:-}" ]; }; then
    echo ""
    echo "=== First-time setup ==="
    echo "No .env file found at $BACKEND_DIR/.env"
    echo ""
    echo "Quick start:"
    echo "  1. cp .env.template .env"
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

# Read environment from .env (skip if missing — yolo mode doesn't need it)
if [ -f "$BACKEND_DIR/.env" ]; then
    set -a; source "$BACKEND_DIR/.env"; set +a
fi
omi_prepare_jit_qa_target "$APP_NAME" "$BUNDLE_ID" "$YOLO_MODE" refresh "$LOCAL_PROFILE" || exit $?
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

# ─── Start Python backend ─────────────────────────────────────────────
if [ "${OMI_SKIP_BACKEND:-0}" != "1" ]; then
    cd "$BACKEND_DIR"
    PYTHON_BACKEND_BINARY="$(omi_python_desktop_backend_binary "$BACKEND_DIR")"
    OLD_BACKEND_PID=""
    if omi_python_desktop_backend_pid_is_alive "$BACKEND_PIDFILE"; then
        OLD_BACKEND_PID="$(omi_python_desktop_backend_read_pid "$BACKEND_PIDFILE")"
        # A pidfile alone is never authority to signal a process: PIDs can be
        # reused after a crash. Require the recorded process-start identity
        # before a later replacement may stop it. This intentionally does not
        # require the requested profile/configuration to match: a known-owned
        # debug process must be safely replaceable by an explicit release run.
        if ! omi_python_desktop_backend_pid_matches_metadata "$BACKEND_METADATA" "$OLD_BACKEND_PID"; then
            substep "Ignoring unverified Python backend pidfile (PID: $OLD_BACKEND_PID)"
            rm -f "$BACKEND_PIDFILE" "$BACKEND_METADATA"
            OLD_BACKEND_PID=""
        fi
    fi

    # The local harness already owns an isolated debug backend. Do not compete
    # for its port or replace its process from the app launcher.
    if [ -n "${OMI_HARNESS_INSTANCE:-}" ]; then
        substep "Reusing harness desktop-backend (instance $OMI_HARNESS_INSTANCE)"
    elif [ -n "$OLD_BACKEND_PID" ] \
        && omi_python_desktop_backend_metadata_matches "$BACKEND_METADATA" "$BACKEND_PORT" \
        && ! omi_python_desktop_backend_sources_are_stale "$BACKEND_DIR" "$BACKEND_PIDFILE" \
        && ! omi_python_desktop_backend_config_is_newer "$BACKEND_DIR" "$BACKEND_PIDFILE" \
        && omi_python_desktop_backend_pid_listens_on_port "$OLD_BACKEND_PID" "$BACKEND_PORT" \
        && omi_python_desktop_backend_health_check "$BACKEND_PORT"; then
        BACKEND_REUSED_PID="$OLD_BACKEND_PID"
        substep "Reusing healthy Python backend (PID: $BACKEND_REUSED_PID, port $BACKEND_PORT)"
    else
        if [ ! -x "$PYTHON_BACKEND_BINARY" ]; then
            echo "ERROR: Python backend dependencies are not synced. Run: (cd backend && ./scripts/sync-python-deps.sh)" >&2
            exit 1
        fi

        if [ -n "$OLD_BACKEND_PID" ]; then
            substep "Replacing owned Python backend (PID: $OLD_BACKEND_PID)"
            omi_python_desktop_backend_stop_owned "$BACKEND_PIDFILE" "$BACKEND_METADATA"
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

        step "Starting Python backend..."
        "$PYTHON_BACKEND_BINARY" desktop_backend:app --host 127.0.0.1 --port "$BACKEND_PORT" >>"$BACKEND_LOG_FILE" 2>&1 &
        BACKEND_PID=$!
        printf '%s\n' "$BACKEND_PID" > "$BACKEND_PIDFILE"
        substep "Backend log: $BACKEND_LOG_FILE"

        step "Waiting for backend to start..."
        BACKEND_READY=0
        for i in {1..30}; do
            if omi_python_desktop_backend_health_check "$BACKEND_PORT"; then
                BACKEND_READY=1
                substep "Backend is ready!"
                break
            fi
            if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
                echo "ERROR: Backend failed to start. Check $BACKEND_DIR/.env and credentials."
                omi_python_desktop_backend_stop_owned "$BACKEND_PIDFILE" "$BACKEND_METADATA"
                exit 1
            fi
            sleep 0.5
        done
        if [ "$BACKEND_READY" != "1" ]; then
            echo "ERROR: Backend did not become healthy on port $BACKEND_PORT. Check $BACKEND_LOG_FILE" >&2
            omi_python_desktop_backend_stop_owned "$BACKEND_PIDFILE" "$BACKEND_METADATA"
            exit 1
        fi
        omi_python_desktop_backend_write_metadata \
            "$BACKEND_METADATA" "$BACKEND_PORT" "$BACKEND_PID"
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

if [ "$FAST_BUNDLE" = "1" ]; then
    step "Building Swift app (swift build -c debug)..."
    xcrun swift build -c debug --package-path Desktop

    step "Patching installed app executable..."
    PATCHED_BINARY="$(mktemp "$APP_PATH/Contents/MacOS/.omi-fast-executable.XXXXXX")"
    cp -f "Desktop/.build/debug/$BINARY_NAME" "$PATCHED_BINARY"
    chmod +x "$PATCHED_BINARY"
    install_name_tool -add_rpath "@executable_path/../Frameworks" "$PATCHED_BINARY" 2>/dev/null || true
    rewrite_bundled_dylib_load_path "$PATCHED_BINARY" "libwebp.7.dylib"
    mv -f "$PATCHED_BINARY" "$APP_PATH/Contents/MacOS/$BINARY_NAME"
    if [ "$LOCAL_PROFILE" = true ]; then
        EFFECTIVE_API_URL="$OMI_DESKTOP_API_URL"
        omi_write_local_profile_env "$APP_PATH/Contents/Resources/.env"
        substep "Refreshed local-profile bundle environment"
    else
        update_app_desktop_api_url "$APP_PATH/Contents/Resources/.env"
        omi_write_jit_qa_bundle_env "$APP_PATH/Contents/Resources/.env" || exit $?
    fi

    step "Signing updated app with hardened runtime..."
    sign_app_bundle "$APP_PATH" false
    reset_local_profile_keychain_state
else
step "Preparing agent runtime..."
"$(dirname "$0")/scripts/prepare-agent-runtime.sh" --universal-node

step "Generating tool surfaces..."
(
  cd agent
  NODE_BIN=""
  for candidate in \
    "../Desktop/Sources/Resources/node" \
    "/opt/homebrew/opt/node@22/bin/node" \
    "/usr/local/opt/node@22/bin/node" \
    "$(command -v node 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" --experimental-strip-types -e '0' >/dev/null 2>&1; then
      NODE_BIN="$candidate"
      break
    fi
  done
  if [[ -z "$NODE_BIN" ]]; then
    echo "ERROR: Node.js 22.6+ with --experimental-strip-types required for tool surface generation." >&2
    exit 1
  fi
  "$NODE_BIN" --experimental-strip-types scripts/generate-tool-surfaces.mjs
)

step "Checking schema docs..."
if [ -f scripts/check_schema_docs.sh ]; then
    bash scripts/check_schema_docs.sh || substep "Schema docs check failed (non-fatal)"
fi

step "Building Swift app (swift build -c debug)..."
xcrun swift build -c debug --package-path Desktop

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
SWIFTPM_DEBUG_PRODUCTS_DIR="Desktop/.build/debug"
SPARKLE_FRAMEWORK="$SWIFTPM_DEBUG_PRODUCTS_DIR/Sparkle.framework"
if [ -d "$SPARKLE_FRAMEWORK" ]; then
    substep "Copying Sparkle framework ($(du -sh "$SPARKLE_FRAMEWORK" 2>/dev/null | cut -f1))"
    rm -rf "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
    cp -R "$SPARKLE_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
fi

# Copy Sentry framework
SENTRY_FRAMEWORK="$SWIFTPM_DEBUG_PRODUCTS_DIR/Sentry.framework"
if [ -d "$SENTRY_FRAMEWORK" ]; then
    substep "Copying Sentry framework"
    rm -rf "$APP_BUNDLE/Contents/Frameworks/Sentry.framework"
    cp -R "$SENTRY_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
fi

# Copy onnxruntime framework
ONNX_FRAMEWORK="$SWIFTPM_DEBUG_PRODUCTS_DIR/onnxruntime.framework"
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
RESOURCE_BUNDLE="$SWIFTPM_DEBUG_PRODUCTS_DIR/Omi Computer_Omi Computer.bundle"
if [ -d "$RESOURCE_BUNDLE" ]; then
    substep "Copying resource bundle ($(du -sh "$RESOURCE_BUNDLE" 2>/dev/null | cut -f1))"
    macos_copy_tree "$RESOURCE_BUNDLE" "$APP_BUNDLE/Contents/Resources/$(basename "$RESOURCE_BUNDLE")"
    # SwiftPM places Resources/node at the resource-bundle root, while the
    # app runtime and signed-artifact audit use the app-style nested layout.
    # Move the universal runtime within the disposable bundle so we do not
    # package a second 200+ MiB copy.
    omi_normalize_packaged_resource_bundle \
        "$APP_BUNDLE/Contents/Resources/$(basename "$RESOURCE_BUNDLE")"
fi

substep "Copying agent"
if [ ! -d "$AGENT_DIR/dist" ]; then
    echo "ERROR: built agent runtime missing at $AGENT_DIR/dist"
    echo "       Run scripts/prepare-agent-runtime.sh before bundling."
    exit 1
fi
mkdir -p "$APP_BUNDLE/Contents/Resources/agent"
macos_copy_tree "$AGENT_DIR/dist" "$APP_BUNDLE/Contents/Resources/agent/dist"
cp -f "$AGENT_DIR/package.json" "$APP_BUNDLE/Contents/Resources/agent/"
if [ ! -d "$AGENT_PACKAGED_NODE_MODULES" ]; then
    echo "ERROR: packaged agent dependencies missing at $AGENT_PACKAGED_NODE_MODULES"
    echo "       Run scripts/prepare-agent-runtime.sh before bundling."
    exit 1
fi
macos_copy_tree "$AGENT_PACKAGED_NODE_MODULES" "$APP_BUNDLE/Contents/Resources/agent/node_modules"

substep "Copying pi-mono-extension (registers the omi provider)"
PI_MONO_EXT_DIR="$SCRIPT_DIR/pi-mono-extension"
if [ ! -d "$PI_MONO_EXT_DIR" ]; then
    echo "ERROR: pi-mono-extension source missing at $PI_MONO_EXT_DIR"
    echo "       Without it the packaged runtime cannot resolve the omi provider and"
    echo "       pi-mono exits 1 on every chat turn."
    exit 1
fi
if [ ! -d "$PI_MONO_EXT_DIR/node_modules" ]; then
    substep "Installing pi-mono-extension dependencies"
    (cd "$PI_MONO_EXT_DIR" && npm ci --no-fund --no-audit)
fi
mkdir -p "$APP_BUNDLE/Contents/Resources/pi-mono-extension"
cp -f "$PI_MONO_EXT_DIR/index.ts" "$APP_BUNDLE/Contents/Resources/pi-mono-extension/"
cp -f "$PI_MONO_EXT_DIR/package.json" "$APP_BUNDLE/Contents/Resources/pi-mono-extension/"
cp -f "$PI_MONO_EXT_DIR/package-lock.json" "$APP_BUNDLE/Contents/Resources/pi-mono-extension/"
if [ ! -d "$PI_MONO_PACKAGED_NODE_MODULES" ]; then
    echo "ERROR: packaged pi-mono-extension dependencies missing at $PI_MONO_PACKAGED_NODE_MODULES"
    echo "       Run scripts/prepare-agent-runtime.sh before bundling."
    exit 1
fi
macos_copy_tree "$PI_MONO_PACKAGED_NODE_MODULES" "$APP_BUNDLE/Contents/Resources/pi-mono-extension/node_modules"

substep "Verifying agent runtime payload"
omi_assert_agent_runtime_payload "$APP_BUNDLE" "bundle assembly"

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
# Do NOT fall back to OMI_DESKTOP_API_URL — that is the Python desktop backend, which does not serve these routes.
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
omi_write_jit_qa_bundle_env "$APP_BUNDLE/Contents/Resources/.env" || exit $?
fi # end non-local .env.app merge

copy_app_icon() {
    local icon_source="$SCRIPT_DIR/omi_icon.icns"
    if [ ! -s "$icon_source" ]; then
        echo "ERROR: missing app icon at $icon_source" >&2
        return 1
    fi
    cp -f "$icon_source" "$APP_BUNDLE/Contents/Resources/OmiIcon.icns"
}

substep "Copying app icon"
copy_app_icon

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
# The fast lane trusts the installed bundle on later launches, and it only ever
# records the fingerprint of a bundle that passed here. Prove the copy landed
# before that stamp makes this bundle reusable.
omi_assert_agent_runtime_payload "$APP_PATH" "install"

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

if [ "$IS_NAMED_BUNDLE" = true ] && [ "${OMI_SKIP_REWIND_SEED:-0}" != "1" ]; then
    step "Seeding Rewind history from Omi Dev..."
    if ! ./scripts/omi-rewind-seed.sh "$BUNDLE_ID"; then
        echo "Warning: could not seed Rewind history into $BUNDLE_ID. Launching with its existing local profile."
    fi
fi

fi # full bundle path

# Curated preferences are launch configuration, not bundle contents. Re-sync
# them after both full installs and executable-only fast rebuilds so a reused
# named bundle cannot retain hotkeys/settings that diverged from Omi Dev.
if [ "$IS_NAMED_BUNDLE" = true ] && [ "${OMI_SKIP_SETTINGS_SEED:-0}" != "1" ]; then
    step "Seeding shortcuts/settings from Omi Dev..."
    if ! ./scripts/omi-settings-seed.sh "$BUNDLE_ID" com.omi.desktop-dev; then
        echo "ERROR: could not mirror shortcuts/settings from Omi Dev." >&2
        echo "Set OMI_SKIP_SETTINGS_SEED=1 only when intentionally testing bundle-local settings." >&2
        exit 1
    fi
    auth_debug "AFTER settings seed: shortcut_askOmiEnabled=$(defaults read "$BUNDLE_ID" shortcut_askOmiEnabled 2>&1 || true)"
    auth_debug "AFTER settings seed: devLazyPermissionsEnabled=$(defaults read "$BUNDLE_ID" devLazyPermissionsEnabled 2>&1 || true)"
fi

signal_desktop_launch() {
    local signal_file="${OMI_DESKTOP_LAUNCH_SIGNAL_FILE:-}"
    local launch_transport="${1:-unknown}"
    local signal_dir signal_tmp
    [ -n "$signal_file" ] || return 0
    signal_dir="$(dirname "$signal_file")"
    if [ ! -d "$signal_dir" ]; then
        echo "ERROR: desktop launch signal directory does not exist: $signal_dir" >&2
        return 1
    fi
    signal_tmp="${signal_file}.tmp.$$"
    # A harness cleanup proof is valid only when this token has also been
    # passed to the process launched by `open`. Do not emit half a proof.
    if [ -n "$DESKTOP_LAUNCH_TOKEN" ]; then
        umask 077
        printf 'schema_version=1\nbundle_id=%s\napp_path=%s\nexecutable_path=%s\nlaunch_token=%s\nlaunch_transport=%s\n' \
            "$BUNDLE_ID" "$APP_PATH" "$APP_PATH/Contents/MacOS/$BINARY_NAME" \
            "$DESKTOP_LAUNCH_TOKEN" "$launch_transport" > "$signal_tmp"
        chmod 600 "$signal_tmp"
    else
        printf 'bundle_id=%s\napp_path=%s\n' "$BUNDLE_ID" "$APP_PATH" > "$signal_tmp"
    fi
    mv -f "$signal_tmp" "$signal_file"
}

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
    echo "Automation UI:     $AUTOMATION_UI_MODE"
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

# `open` starts the app from launchd, not this shell, so documented QA
# overrides must be forwarded explicitly or they silently do nothing. Only the
# direct-exec fallback below inherits this shell's environment.
build_launch_env_args() {
    LAUNCH_ENV_ARGS=()
    if [ -n "${OMI_JIT_QA_TARGET:-}" ]; then
        LAUNCH_ENV_ARGS+=(
            --env "OMI_PYTHON_API_URL=$OMI_PYTHON_API_URL"
            --env "OMI_DESKTOP_API_URL=$OMI_DESKTOP_API_URL"
            --env "OMI_AUTH_API_URL=$OMI_AUTH_API_URL"
            --env "OMI_ENV_STAGE=$OMI_ENV_STAGE"
        )
    fi
    if [ -n "${OMI_FORCE_CANONICAL_MEMORY_ATLAS:-}" ]; then
        LAUNCH_ENV_ARGS+=(--env "OMI_FORCE_CANONICAL_MEMORY_ATLAS=$OMI_FORCE_CANONICAL_MEMORY_ATLAS")
    fi
    if [ -n "${OMI_FORCE_CONTEXT_BUCKETS:-}" ]; then
        LAUNCH_ENV_ARGS+=(--env "OMI_FORCE_CONTEXT_BUCKETS=$OMI_FORCE_CONTEXT_BUCKETS")
    fi
    if [ -n "${OMI_FORCE_MEETING_NOTE_SCREENSHOTS:-}" ]; then
        LAUNCH_ENV_ARGS+=(--env "OMI_FORCE_MEETING_NOTE_SCREENSHOTS=$OMI_FORCE_MEETING_NOTE_SCREENSHOTS")
    fi
    # Forward automation token overrides when the caller already pinned them
    # (e.g. desktop-core-harness.sh). Default token discovery prefers Darwin
    # user temp in harness clients, matching NSTemporaryDirectory().
    if [ -n "${OMI_AUTOMATION_TOKEN_FILE:-}" ]; then
        LAUNCH_ENV_ARGS+=(--env "OMI_AUTOMATION_TOKEN_FILE=$OMI_AUTOMATION_TOKEN_FILE")
    fi
    if [ -n "${OMI_AUTOMATION_TOKEN:-}" ]; then
        LAUNCH_ENV_ARGS+=(--env "OMI_AUTOMATION_TOKEN=$OMI_AUTOMATION_TOKEN")
    fi
}

build_launch_env_args || exit $?

LAUNCH_TRANSPORT="open"
if [ -n "$DESKTOP_LAUNCH_TOKEN" ]; then
    # `-n` guarantees this invocation creates a process carrying the capability
    # token instead of focusing an existing instance of the same app.
    LAUNCH_ARGS=("${AUTOMATION_ARGS[@]}" "--omi-launch-token=$DESKTOP_LAUNCH_TOKEN")
    OPEN_BACKGROUND_ARGS=()
    [ "$AUTOMATION_UI_MODE" = "quiet" ] && OPEN_BACKGROUND_ARGS=(-g)
    if ! open -n "${OPEN_BACKGROUND_ARGS[@]}" ${LAUNCH_ENV_ARGS[@]+"${LAUNCH_ENV_ARGS[@]}"} "$APP_PATH" --args "${LAUNCH_ARGS[@]}"; then
        LAUNCH_TRANSPORT="direct"
        "$APP_PATH/Contents/MacOS/$BINARY_NAME" "${LAUNCH_ARGS[@]}" &
    fi
elif [ "${#AUTOMATION_ARGS[@]}" -gt 0 ]; then
    OPEN_BACKGROUND_ARGS=()
    [ "$AUTOMATION_UI_MODE" = "quiet" ] && OPEN_BACKGROUND_ARGS=(-g)
    if ! open "${OPEN_BACKGROUND_ARGS[@]}" ${LAUNCH_ENV_ARGS[@]+"${LAUNCH_ENV_ARGS[@]}"} "$APP_PATH" --args "${AUTOMATION_ARGS[@]}"; then
        LAUNCH_TRANSPORT="direct"
        "$APP_PATH/Contents/MacOS/$BINARY_NAME" "${AUTOMATION_ARGS[@]}" &
    fi
else
    if ! open ${LAUNCH_ENV_ARGS[@]+"${LAUNCH_ENV_ARGS[@]}"} "$APP_PATH"; then
        LAUNCH_TRANSPORT="direct"
        "$APP_PATH/Contents/MacOS/$BINARY_NAME" &
    fi
fi
signal_desktop_launch "$LAUNCH_TRANSPORT"

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
