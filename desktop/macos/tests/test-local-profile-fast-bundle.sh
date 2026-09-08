#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$MACOS_DIR/scripts/local-profile-env.sh"

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-local-profile-fast-bundle.XXXXXX")"
cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

export OMI_DESKTOP_API_URL="http://127.0.0.1:10201"
export OMI_PYTHON_API_URL="http://127.0.0.1:8080"
export OMI_LOCAL_PROFILE_STORAGE_NAME="omi-local-fast-contract"
export OMI_LOCAL_AUTH_USER="alice"
export OMI_LOCAL_AUTH_EMAIL="alice@local.omi.invalid"
export OMI_LOCAL_AUTH_PASSWORD="local-profile-password-only-in-bundle"
export OMI_LOCAL_AUTH_DISPLAY_NAME="Synthetic Alice"
export FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9099"
export FIREBASE_PROJECT_ID="demo-omi-local"
export FIREBASE_AUTH_PROJECT_ID="demo-omi-local"
export FIRESTORE_DATABASE_ID="(default)"
export FIREBASE_API_KEY="local-firebase-auth-emulator-api-key"

env_file="$TMP_ROOT/.env"
printf '%s\n' "stale=true" > "$env_file"
omi_write_local_profile_env "$env_file"

grep -qx 'OMI_DESKTOP_LOCAL_PROFILE=1' "$env_file"
grep -qx 'OMI_DESKTOP_API_URL=http://127.0.0.1:10201' "$env_file"
grep -qx 'OMI_LOCAL_AUTH_PASSWORD=local-profile-password-only-in-bundle' "$env_file"
grep -qx 'FIRESTORE_DATABASE_ID=(default)' "$env_file"
! grep -q '^stale=' "$env_file"

# A fast-only eligibility probe runs before any launch side effects. Local
# profiles must now reach the ordinary bundle eligibility result; the secret
# profile values are refreshed only when an already-installed bundle is patched.
probe_log="$TMP_ROOT/fast-only.log"
if HOME="$TMP_ROOT/home" \
  OMI_APP_NAME="omi-local-fast-contract" \
  OMI_DESKTOP_LOCAL_PROFILE=1 \
  OMI_SKIP_BACKEND=1 \
  OMI_SKIP_TUNNEL=1 \
  "$MACOS_DIR/run.sh" --fast-only >"$probe_log" 2>&1; then
  echo "local-profile --fast-only unexpectedly succeeded without an installed bundle" >&2
  exit 1
else
  probe_status=$?
fi

test "$probe_status" = "3"
grep -q 'launch_mode=failed fast_reason=no_installed_bundle' "$probe_log"
! grep -q 'local_profile_requires_full' "$probe_log"
if grep -qE 'Killing existing instances|Cleaning up conflicting app bundles|Starting Cloudflare|Starting Rust backend|Preparing agent runtime' "$probe_log"; then
  echo "local-profile --fast-only performed side effects before rejecting a missing bundle" >&2
  exit 1
fi

# Static fast-path contract: local-profile Keychain cleanup must be performed
# after the fast executable patch, not only in the complete-bundle branch.
fast_branch="$(sed -n '/if \[ "$FAST_BUNDLE" = "1" \]; then/,/^else$/p' "$MACOS_DIR/run.sh")"
if ! grep -q 'reset_local_profile_keychain_state' <<<"$fast_branch"; then
  echo "local-profile fast path no longer resets scoped Keychain state" >&2
  exit 1
fi

# Static fingerprint contract: endpoint changes are written into the local
# profile bundle during a patch, so they must not force a complete repackaging.
fingerprint_function="$(sed -n '/^fast_bundle_fingerprint()/,/^}/p' "$MACOS_DIR/run.sh")"
if ! grep -q 'desktop_api_fingerprint="local-profile-refreshed"' <<<"$fingerprint_function" \
  || ! grep -q 'python_api_fingerprint="local-profile-refreshed"' <<<"$fingerprint_function"; then
  echo "local-profile endpoint settings must remain eligible for fast patching" >&2
  exit 1
fi

echo "local-profile fast bundle tests passed"
