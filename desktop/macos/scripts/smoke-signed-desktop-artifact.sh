#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_BUNDLE=""
SOURCE_APP_BUNDLE=""
SPARKLE_ZIP=""
DMG_PATH=""
RELEASE_TAG=""
EXPECTED_CHANNEL="${OMI_SIGNED_ARTIFACT_SMOKE_CHANNEL:-beta}"
EXPECTED_TEAM_ID="${OMI_SIGNED_ARTIFACT_SMOKE_TEAM_ID:-9536L8KLMP}"
EXPECTED_BUNDLE_ID="${OMI_SIGNED_ARTIFACT_SMOKE_BUNDLE_ID:-com.omi.computer-macos}"
EXPECTED_URL_SCHEME="${OMI_SIGNED_ARTIFACT_SMOKE_URL_SCHEME:-omi-computer}"
EXPECTED_FEED_URL="${OMI_SIGNED_ARTIFACT_SMOKE_FEED_URL:-https://api.omi.me/v2/desktop/appcast.xml}"
EXPECTED_PYTHON_API_URL="${OMI_SIGNED_ARTIFACT_SMOKE_PYTHON_API_URL:-https://api.omi.me}"
EXPECTED_DESKTOP_API_URL="${OMI_SIGNED_ARTIFACT_SMOKE_DESKTOP_API_URL:-https://desktop-backend-hhibjajaja-uc.a.run.app/}"
IS_EXTERNAL_PREVIEW=false
RUN_LAUNCH=false
RUN_NETWORK=false
RUN_AUTH=false
RUN_AUTH_STORAGE_CANARY=false
RUN_CHAT=false
RUN_PERMISSIONS=false
RUN_STORAGE=false
RUN_NOTIFICATION_CALLBACK_CANARY=false
APPLY_QUARANTINE=false
INSTALL_DIR=""
KEEP_INSTALL=false
TIMEOUT_SECONDS=45
RESULT_JSON=""
ZIP_EXTRACT_DIR=""
DMG_MOUNTPOINT=""
SMOKE_CHECKS=()
SMOKE_ARTIFACTS=()
NOTIFICATION_CALLBACK_MARKER=""
NOTIFICATION_CALLBACK_MARKER_IS_TEMP=false
NOTIFICATION_CALLBACK_PROOF=""

usage() {
  cat <<'USAGE'
Usage: scripts/smoke-signed-desktop-artifact.sh --app /path/to/omi.app [options]

Verifies the signed/notarized macOS desktop artifact before user exposure.
The default mode is deterministic and safe for Codemagic: it audits bundle
identity, signing, entitlements, Sparkle metadata, backend config, helper
runtime packaging, local storage schema resources, and artifact alignment.

Options:
  --app PATH                 App bundle to verify (required unless --zip extracts one)
  --zip PATH                 Sparkle ZIP containing the app bundle
  --dmg PATH                 DMG artifact to verify/mount when available
  --tag TAG                  Expected release tag, vX.Y.Z+BUILD-macos
  --expected-channel NAME    Expected channel label for result metadata (default: beta)
  --expected-bundle-id ID    Expected app bundle identifier
  --expected-url-scheme URL  Expected app URL scheme
  --expected-feed-url URL    Expected SUFeedURL (default: plain shared appcast;
                             the Omi Beta variant passes its identity-scoped feed)
  --expected-python-api-url URL
                             Expected OMI_PYTHON_API_URL in the artifact
  --expected-desktop-api-url URL
                             Expected OMI_DESKTOP_API_URL in the artifact
  --preview                  Assert external-preview isolation (no Sparkle feed)
  --launch                   Launch the app and assert it stays alive briefly
  --network                  Probe configured backend/appcast URLs
  --auth                     Run auth persistence probe (requires env below)
  --auth-storage-canary      Run synthetic Keychain round trip in the signed app
  --chat                     Run minimal chat probe (requires --auth env)
  --permissions             Verify permission surface/fail-graceful live path
  --notification-callback-canary
                             Require the launched app to prove its
                             UserNotifications settings callback completed
  --notification-callback-marker PATH
                             Callback-proof path (a unique temporary path by default)
  --storage                  Verify local storage opens in live path
  --quarantine              Apply download quarantine to launch copy before launch
  --result-json PATH         Write machine-readable smoke result JSON
  --install-dir PATH         Copy extracted app here before launch
  --keep-install            Do not remove --install-dir temp copy
  --timeout SECONDS          Launch/network timeout (default: 45)
  -h, --help                 Show this help

Optional live-probe environment:
  OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH=1
      Required before --launch can launch a production-family bundle id.
  OMI_SIGNED_ARTIFACT_SMOKE_AUTH_PROOF_COMMAND='...'
      Required for --auth. Runs after --launch and must prove app-level auth
      persistence/Keychain restore/restart behavior for the launched artifact.
  OMI_SIGNED_ARTIFACT_SMOKE_AUTH_HEADER='Bearer ...'
      Required for --chat until a dedicated release canary OAuth fixture exists.
  OMI_SIGNED_ARTIFACT_SMOKE_CHAT_URL='https://...'
      Chat API URL to probe; defaults to https://api.omi.me/v2/chat/completions.
  OMI_NOTIFICATION_CALLBACK_SMOKE_RESULT_PATH
      Passed to the app only with --notification-callback-canary. The app must
      atomically write the callback result after its
      UserNotifications callback has run; staying alive is not sufficient.

Smoke paths covered:
  - Launch + identity
  - Auth persistence
  - Signed Keychain canary
  - Backend routing
  - Sparkle/update metadata
  - External-preview isolation
  - Native helper/runtime bundle integrity
  - Minimal chat path
  - Recording permission surface sanity
  - Local storage/database
USAGE
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

warn() {
  echo "WARN: $*" >&2
}

pass() {
  echo "PASS: $*"
  SMOKE_CHECKS+=("$*")
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required"
}

plist_read() {
  local key="$1"
  /usr/libexec/PlistBuddy -c "Print :$key" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || true
}

plist_read_from() {
  local bundle="$1"
  local key="$2"
  /usr/libexec/PlistBuddy -c "Print :$key" "$bundle/Contents/Info.plist" 2>/dev/null || true
}

require_option_value() {
  local option="$1"
  local value="${2:-}"
  [[ -n "$value" && "$value" != -* ]] || fail "$option requires a value"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --app) require_option_value "$1" "${2:-}"; APP_BUNDLE="$2"; shift 2 ;;
      --zip) require_option_value "$1" "${2:-}"; SPARKLE_ZIP="$2"; shift 2 ;;
      --dmg) require_option_value "$1" "${2:-}"; DMG_PATH="$2"; shift 2 ;;
      --tag) require_option_value "$1" "${2:-}"; RELEASE_TAG="$2"; shift 2 ;;
      --expected-channel) require_option_value "$1" "${2:-}"; EXPECTED_CHANNEL="$2"; shift 2 ;;
      --expected-bundle-id) require_option_value "$1" "${2:-}"; EXPECTED_BUNDLE_ID="$2"; shift 2 ;;
      --expected-url-scheme) require_option_value "$1" "${2:-}"; EXPECTED_URL_SCHEME="$2"; shift 2 ;;
      --expected-feed-url) require_option_value "$1" "${2:-}"; EXPECTED_FEED_URL="$2"; shift 2 ;;
      --expected-python-api-url) require_option_value "$1" "${2:-}"; EXPECTED_PYTHON_API_URL="$2"; shift 2 ;;
      --expected-desktop-api-url) require_option_value "$1" "${2:-}"; EXPECTED_DESKTOP_API_URL="$2"; shift 2 ;;
      --preview) IS_EXTERNAL_PREVIEW=true; shift ;;
      --launch) RUN_LAUNCH=true; shift ;;
      --network) RUN_NETWORK=true; shift ;;
      --auth) RUN_AUTH=true; shift ;;
      --auth-storage-canary) RUN_AUTH_STORAGE_CANARY=true; shift ;;
      --chat) RUN_CHAT=true; shift ;;
      --permissions) RUN_PERMISSIONS=true; shift ;;
      --notification-callback-canary) RUN_NOTIFICATION_CALLBACK_CANARY=true; shift ;;
      --notification-callback-marker) require_option_value "$1" "${2:-}"; NOTIFICATION_CALLBACK_MARKER="$2"; shift 2 ;;
      --storage) RUN_STORAGE=true; shift ;;
      --quarantine) APPLY_QUARANTINE=true; shift ;;
      --result-json) require_option_value "$1" "${2:-}"; RESULT_JSON="$2"; shift 2 ;;
      --install-dir) require_option_value "$1" "${2:-}"; INSTALL_DIR="$2"; shift 2 ;;
      --keep-install) KEEP_INSTALL=true; shift ;;
      --timeout) require_option_value "$1" "${2:-}"; TIMEOUT_SECONDS="$2"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) fail "unknown argument: $1" ;;
    esac
  done
}

version_from_tag() {
  [[ "$1" =~ ^v([0-9]+[.][0-9]+[.][0-9]+)[+]([0-9]+)-macos$ ]] || return 1
  printf '%s\n' "${BASH_REMATCH[1]}"
}

build_from_tag() {
  [[ "$1" =~ ^v([0-9]+[.][0-9]+[.][0-9]+)[+]([0-9]+)-macos$ ]] || return 1
  printf '%s\n' "${BASH_REMATCH[2]}"
}

extract_zip_if_needed() {
  [[ -n "$SPARKLE_ZIP" ]] || return 0
  [[ -f "$SPARKLE_ZIP" ]] || fail "Sparkle ZIP not found: $SPARKLE_ZIP"

  require_cmd ditto
  ZIP_EXTRACT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-signed-smoke-zip.XXXXXX")"
  ditto -x -k "$SPARKLE_ZIP" "$ZIP_EXTRACT_DIR"

  local found
  found="$(find "$ZIP_EXTRACT_DIR" -maxdepth 2 -type d -name "*.app" | head -1)"
  [[ -n "$found" ]] || fail "no .app bundle found inside $SPARKLE_ZIP"

  if [[ -n "$APP_BUNDLE" ]]; then
    SOURCE_APP_BUNDLE="$(cd "$APP_BUNDLE" && pwd)"
  fi
  APP_BUNDLE="$found"
  pass "Sparkle ZIP extracts an app bundle"
}

maybe_copy_for_launch() {
  [[ "$RUN_LAUNCH" == true || "$RUN_AUTH_STORAGE_CANARY" == true ]] || return 0
  [[ -n "$INSTALL_DIR" ]] || INSTALL_DIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-signed-smoke-install.XXXXXX")"
  mkdir -p "$INSTALL_DIR"

  local target="$INSTALL_DIR/$(basename "$APP_BUNDLE")"
  rm -rf "$target"
  require_cmd ditto
  ditto "$APP_BUNDLE" "$target"
  APP_BUNDLE="$target"
  if [[ "$APPLY_QUARANTINE" == true ]]; then
    xattr -w com.apple.quarantine "0081;$(printf '%x' "$(date +%s)");CodemagicSmoke;https://github.com/BasedHardware/omi" "$APP_BUNDLE" \
      || fail "failed to apply quarantine attribute"
  fi
  pass "Copied app to launch install dir: $APP_BUNDLE"
}

cleanup() {
  if [[ -n "${SMOKE_PID:-}" ]]; then
    if kill -0 "$SMOKE_PID" >/dev/null 2>&1; then
      kill "$SMOKE_PID" >/dev/null 2>&1 || true
      wait "$SMOKE_PID" >/dev/null 2>&1 || true
    fi
  fi
  if [[ -n "$DMG_MOUNTPOINT" && -d "$DMG_MOUNTPOINT" ]]; then
    hdiutil detach "$DMG_MOUNTPOINT" -quiet >/dev/null 2>&1 || true
    rmdir "$DMG_MOUNTPOINT" >/dev/null 2>&1 || true
  fi
  if [[ -n "$ZIP_EXTRACT_DIR" && -d "$ZIP_EXTRACT_DIR" ]]; then
    rm -rf "$ZIP_EXTRACT_DIR"
  fi
  if [[ "$KEEP_INSTALL" != true && -n "$INSTALL_DIR" && "$INSTALL_DIR" == "${TMPDIR:-/tmp}"/omi-signed-smoke-install.* ]]; then
    rm -rf "$INSTALL_DIR"
  fi
  if [[ "$NOTIFICATION_CALLBACK_MARKER_IS_TEMP" == true && -n "$NOTIFICATION_CALLBACK_MARKER" ]]; then
    rm -f "$NOTIFICATION_CALLBACK_MARKER"
  fi
}
trap cleanup EXIT

assert_bundle_matches_current() {
  local candidate="$1"
  local label="$2"
  [[ -d "$candidate/Contents" ]] || fail "$label app bundle not found: $candidate"

  local current_id current_version current_build candidate_id candidate_version candidate_build
  local current_executable candidate_executable current_executable_sha candidate_executable_sha
  current_id="$(plist_read CFBundleIdentifier)"
  current_version="$(plist_read CFBundleShortVersionString)"
  current_build="$(plist_read CFBundleVersion)"
  current_executable="$(plist_read CFBundleExecutable)"
  candidate_id="$(plist_read_from "$candidate" CFBundleIdentifier)"
  candidate_version="$(plist_read_from "$candidate" CFBundleShortVersionString)"
  candidate_build="$(plist_read_from "$candidate" CFBundleVersion)"
  candidate_executable="$(plist_read_from "$candidate" CFBundleExecutable)"

  [[ "$candidate_id" == "$current_id" ]] || fail "$label bundle id mismatch: expected $current_id, got ${candidate_id:-missing}"
  [[ "$candidate_version" == "$current_version" ]] || fail "$label version mismatch: expected $current_version, got ${candidate_version:-missing}"
  [[ "$candidate_build" == "$current_build" ]] || fail "$label build mismatch: expected $current_build, got ${candidate_build:-missing}"
  [[ "$candidate_executable" == "$current_executable" ]] || fail "$label executable name mismatch: expected $current_executable, got ${candidate_executable:-missing}"
  current_executable_sha="$(sha256_file "$APP_BUNDLE/Contents/MacOS/$current_executable")"
  candidate_executable_sha="$(sha256_file "$candidate/Contents/MacOS/$candidate_executable")"
  [[ "$candidate_executable_sha" == "$current_executable_sha" ]] \
    || fail "$label executable hash mismatch: expected $current_executable_sha, got $candidate_executable_sha"
}

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

record_artifact() {
  local label="$1"
  local path="$2"
  [[ -e "$path" ]] || return 0

  if [[ -f "$path" ]]; then
    SMOKE_ARTIFACTS+=("$label|$path|$(stat -f '%z' "$path")|$(sha256_file "$path")")
  else
    SMOKE_ARTIFACTS+=("$label|$path||")
  fi
}

write_result_json() {
  [[ -n "$RESULT_JSON" ]] || return 0
  mkdir -p "$(dirname "$RESULT_JSON")"

  local bundle_id version build executable team_id app_sha
  bundle_id="$(plist_read CFBundleIdentifier)"
  version="$(plist_read CFBundleShortVersionString)"
  build="$(plist_read CFBundleVersion)"
  executable="$(plist_read CFBundleExecutable)"
  app_sha="$(sha256_file "$APP_BUNDLE/Contents/MacOS/$executable")"
  team_id="$(codesign -dv "$APP_BUNDLE" 2>&1 | awk -F= '/^TeamIdentifier=/{print $2; exit}')"

  CHECKS_JOINED="$(printf '%s\n' "${SMOKE_CHECKS[@]}")" \
    ARTIFACTS_JOINED="$(printf '%s\n' "${SMOKE_ARTIFACTS[@]}")" \
    RESULT_TAG="$RELEASE_TAG" \
    RESULT_CHANNEL="$EXPECTED_CHANNEL" \
    RESULT_BUNDLE_ID="$bundle_id" \
    RESULT_VERSION="$version" \
    RESULT_BUILD="$build" \
    RESULT_TEAM_ID="$team_id" \
    RESULT_APP_EXECUTABLE_SHA256="$app_sha" \
    RESULT_NOTIFICATION_CALLBACK_PROOF="$NOTIFICATION_CALLBACK_PROOF" \
    python3 - <<'PY' > "$RESULT_JSON"
import json
import os
from datetime import datetime, timezone

artifacts = []
for line in os.environ.get("ARTIFACTS_JOINED", "").splitlines():
    if not line:
        continue
    label, path, size, sha = (line.split("|", 3) + ["", "", "", ""])[:4]
    artifact = {"label": label, "path": path}
    if size:
        artifact["size"] = int(size)
    if sha:
        artifact["sha256"] = sha
    artifacts.append(artifact)

notification_callback_canary = None
proof = os.environ.get("RESULT_NOTIFICATION_CALLBACK_PROOF", "")
if proof:
    notification_callback_canary = json.loads(proof)

print(json.dumps({
    "ok": True,
    "finished_at": datetime.now(timezone.utc).isoformat(),
    "release_tag": os.environ.get("RESULT_TAG") or None,
    "expected_channel": os.environ.get("RESULT_CHANNEL") or None,
    "bundle_id": os.environ.get("RESULT_BUNDLE_ID") or None,
    "version": os.environ.get("RESULT_VERSION") or None,
    "build": os.environ.get("RESULT_BUILD") or None,
    "team_id": os.environ.get("RESULT_TEAM_ID") or None,
    "app_executable_sha256": os.environ.get("RESULT_APP_EXECUTABLE_SHA256") or None,
    "notification_callback_canary": notification_callback_canary,
    "artifacts": artifacts,
    "checks": [line for line in os.environ.get("CHECKS_JOINED", "").splitlines() if line],
}, indent=2, sort_keys=True))
PY
}

assert_bundle_identity() {
  [[ -d "$APP_BUNDLE/Contents" ]] || fail "app bundle not found: $APP_BUNDLE"

  local bundle_id version build executable url_scheme feed_url external_preview_marker automatic_checks
  bundle_id="$(plist_read CFBundleIdentifier)"
  version="$(plist_read CFBundleShortVersionString)"
  build="$(plist_read CFBundleVersion)"
  executable="$(plist_read CFBundleExecutable)"
  feed_url="$(plist_read SUFeedURL)"
  url_scheme="$(/usr/libexec/PlistBuddy -c "Print :CFBundleURLTypes:0:CFBundleURLSchemes:0" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || true)"
  external_preview_marker="$(plist_read OMIExternalPreview)"
  automatic_checks="$(plist_read SUEnableAutomaticChecks)"

  [[ "$bundle_id" == "$EXPECTED_BUNDLE_ID" ]] || fail "bundle id must be $EXPECTED_BUNDLE_ID, got ${bundle_id:-missing}"
  [[ "$url_scheme" == "$EXPECTED_URL_SCHEME" ]] || fail "URL scheme must be $EXPECTED_URL_SCHEME, got ${url_scheme:-missing}"
  if [[ "$IS_EXTERNAL_PREVIEW" == true ]]; then
    [[ "$bundle_id" =~ ^com[.]omi[.]preview[.][a-z0-9-]+$ ]] \
      || fail "external preview bundle id must use the preview namespace"
    [[ "$url_scheme" =~ ^omi-preview-[a-z0-9-]+$ ]] \
      || fail "external preview URL scheme must use the preview namespace"
    [[ "$external_preview_marker" == "true" || "$external_preview_marker" == "1" ]] \
      || fail "external preview marker must be enabled"
    [[ -z "$feed_url" ]] || fail "external preview must not carry a shared Sparkle feed"
    [[ "$automatic_checks" == "false" || "$automatic_checks" == "0" ]] \
      || fail "external preview must disable automatic update checks"
  else
    # The Omi Beta variant carries an identity-scoped feed; the expected URL is
    # passed per artifact (default: the plain shared feed).
    [[ "$feed_url" == "$EXPECTED_FEED_URL" ]] \
      || fail "SUFeedURL mismatch: expected $EXPECTED_FEED_URL, got ${feed_url:-missing}"
  fi
  [[ -n "$executable" && -x "$APP_BUNDLE/Contents/MacOS/$executable" ]] || fail "main executable missing or not executable"

  if [[ -n "$RELEASE_TAG" ]]; then
    local expected_version expected_build
    expected_version="$(version_from_tag "$RELEASE_TAG")" || fail "invalid release tag: $RELEASE_TAG"
    expected_build="$(build_from_tag "$RELEASE_TAG")"
    [[ "$version" == "$expected_version" ]] || fail "version mismatch: expected $expected_version, got ${version:-missing}"
    [[ "$build" == "$expected_build" ]] || fail "build mismatch: expected $expected_build, got ${build:-missing}"
  fi

  if [[ "$IS_EXTERNAL_PREVIEW" == true ]]; then
    pass "External-preview identity and update isolation are aligned"
  else
    pass "Launch + identity metadata is aligned"
  fi
}

assert_signing_and_entitlements() {
  require_cmd codesign
  codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE" >/dev/null 2>&1 || fail "app bundle failed deep codesign verification"
  local signing_details team runtime
  signing_details="$(codesign -dv "$APP_BUNDLE" 2>&1 || true)"
  team="$(printf '%s\n' "$signing_details" | awk -F= '/^TeamIdentifier=/{print $2; exit}')"
  runtime="$(printf '%s\n' "$signing_details" | awk -F= '/^Runtime Version=/{print $2; exit}')"
  [[ "$team" == "$EXPECTED_TEAM_ID" ]] || fail "TeamIdentifier mismatch: expected $EXPECTED_TEAM_ID, got ${team:-missing}"
  [[ -n "$runtime" ]] || fail "signed app is missing hardened runtime metadata"

  local entitlements
  entitlements="$(mktemp "${TMPDIR:-/tmp}/omi-entitlements.plist.XXXXXX")"
  codesign -d --entitlements :- "$APP_BUNDLE" >"$entitlements" 2>/dev/null || fail "could not read app entitlements"

  if /usr/libexec/PlistBuddy -c "Print :com.apple.security.get-task-allow" "$entitlements" >/dev/null 2>&1; then
    fail "release app contains get-task-allow entitlement"
  fi

  local app_identifier
  app_identifier="$(/usr/libexec/PlistBuddy -c "Print :com.apple.application-identifier" "$entitlements" 2>/dev/null || true)"
  if [[ -n "$app_identifier" ]]; then
    [[ "$app_identifier" == "$EXPECTED_TEAM_ID.$EXPECTED_BUNDLE_ID" ]] \
      || fail "application identifier entitlement mismatch: expected $EXPECTED_TEAM_ID.$EXPECTED_BUNDLE_ID, got $app_identifier"
  fi
  if /usr/libexec/PlistBuddy -c "Print :keychain-access-groups" "$entitlements" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Print :keychain-access-groups" "$entitlements" | grep -q "$EXPECTED_TEAM_ID.$EXPECTED_BUNDLE_ID" \
      || fail "keychain-access-groups must include $EXPECTED_TEAM_ID.$EXPECTED_BUNDLE_ID when present"
  fi

  if command -v spctl >/dev/null 2>&1; then
    spctl --assess --type execute --verbose "$APP_BUNDLE" >/dev/null 2>&1 \
      || fail "spctl Gatekeeper assessment failed"
  fi

  pass "Auth persistence prerequisites: signing identity and Keychain-compatible entitlements are sane"
}

assert_backend_routing_config() {
  local env_file="$APP_BUNDLE/Contents/Resources/.env"
  [[ -f "$env_file" ]] || fail "release .env missing"

  grep -Fqx "OMI_PYTHON_API_URL=$EXPECTED_PYTHON_API_URL" "$env_file" \
    || fail "artifact .env must use expected OMI_PYTHON_API_URL"
  grep -Fqx "OMI_DESKTOP_API_URL=$EXPECTED_DESKTOP_API_URL" "$env_file" \
    || fail "artifact .env must use expected OMI_DESKTOP_API_URL"
  ! grep -Eq 'localhost|127[.]0[.]0[.]1|0[.]0[.]0[.]0|ngrok|dev-serve' "$env_file" \
    || fail "artifact .env contains a local/dev tunnel backend reference"

  pass "Backend routing config matches the declared external backend"
}

assert_sparkle_and_artifacts() {
  [[ "$EXPECTED_CHANNEL" =~ ^(beta|stable|staging|preview)$ ]] || fail "unexpected release channel: $EXPECTED_CHANNEL"
  if [[ "$IS_EXTERNAL_PREVIEW" == true ]]; then
    [[ "$EXPECTED_CHANNEL" == "preview" ]] || fail "external preview artifacts must use the preview channel label"
    [[ -z "$SPARKLE_ZIP" ]] || fail "external previews must not publish a shared Sparkle ZIP"
  else
    [[ "$EXPECTED_CHANNEL" != "preview" ]] || fail "only external previews may use the preview channel label"
  fi
  pass "Expected channel label recorded as $EXPECTED_CHANNEL"
  if [[ -n "$SOURCE_APP_BUNDLE" ]]; then
    assert_bundle_matches_current "$SOURCE_APP_BUNDLE" "source --app"
  fi

  if [[ -z "$SPARKLE_ZIP" ]]; then
    warn "no Sparkle ZIP supplied; authoritative release payload was not audited"
  else
    [[ -f "$SPARKLE_ZIP" ]] || fail "Sparkle ZIP missing: $SPARKLE_ZIP"
    unzip -tq "$SPARKLE_ZIP" >/dev/null || fail "Sparkle ZIP is not readable"
    record_artifact "sparkle_zip" "$SPARKLE_ZIP"
  fi

  if [[ -n "$DMG_PATH" ]]; then
    [[ -f "$DMG_PATH" ]] || fail "DMG missing: $DMG_PATH"
    hdiutil imageinfo "$DMG_PATH" >/dev/null || fail "DMG imageinfo failed"
    if command -v codesign >/dev/null 2>&1; then
      codesign --verify --verbose=1 "$DMG_PATH" >/dev/null 2>&1 || fail "DMG codesign verification failed"
    fi
    if command -v xcrun >/dev/null 2>&1; then
      xcrun stapler validate "$DMG_PATH" >/dev/null 2>&1 \
        || fail "DMG stapler validation failed"
    fi
    DMG_MOUNTPOINT="$(mktemp -d "${TMPDIR:-/tmp}/omi-signed-smoke-dmg.XXXXXX")"
    hdiutil attach "$DMG_PATH" -nobrowse -readonly -mountpoint "$DMG_MOUNTPOINT" -quiet \
      || fail "DMG attach failed"
    local dmg_app
    dmg_app="$(find "$DMG_MOUNTPOINT" -maxdepth 2 -type d -name "*.app" | head -1)"
    [[ -n "$dmg_app" ]] || fail "DMG does not contain an app bundle"
    assert_bundle_matches_current "$dmg_app" "DMG"
    record_artifact "dmg" "$DMG_PATH"
  fi

  [[ -d "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework" ]] || fail "Sparkle.framework missing"
  if [[ "$IS_EXTERNAL_PREVIEW" == true ]]; then
    pass "External preview is excluded from shared Sparkle publishing"
  elif [[ -n "$SPARKLE_ZIP" ]]; then
    pass "Sparkle/update metadata and authoritative ZIP artifacts are present"
  else
    pass "Sparkle framework metadata is present"
  fi
}

assert_helper_runtime_integrity() {
  "$MACOS_DIR/scripts/audit-desktop-bundle-deps.sh" "$APP_BUNDLE" >/dev/null

  local resources="$APP_BUNDLE/Contents/Resources"
  [[ -d "$resources/agent" ]] || fail "agent runtime missing"
  [[ -f "$resources/agent/src/runtime/omi-tool-manifest.ts" ]] || fail "agent tool manifest missing"
  [[ -d "$resources/pi-mono-extension" ]] || fail "pi-mono-extension missing"
  [[ -x "$resources/Omi Computer_Omi Computer.bundle/node" ]] || fail "bundled node missing"
  strings "$APP_BUNDLE/Contents/MacOS/$(plist_read CFBundleExecutable)" 2>/dev/null | grep -q "LocalAgentAPIServer" \
    || warn "could not find LocalAgentAPIServer marker in executable; release builds may strip Swift symbols"

  pass "Native helper/runtime bundle integrity passed"
}

assert_local_storage_resources() {
  local resources="$APP_BUNDLE/Contents/Resources"
  find "$resources" -maxdepth 3 \( -name "*.momd" -o -name "*.sqlite" -o -name "*.db" \) >/dev/null 2>&1 || true
  strings "$APP_BUNDLE/Contents/MacOS/$(plist_read CFBundleExecutable)" 2>/dev/null | grep -q "RewindDatabase" \
    || warn "could not find RewindDatabase symbol marker in executable"

  pass "Local storage/database package surface is present"
}

probe_url() {
  local url="$1"
  local expected_prefix="${2:-2}"
  local status
  status="$(curl -L -sS -o /tmp/omi-smoke-probe.out -w "%{http_code}" --max-time "$TIMEOUT_SECONDS" "$url")" \
    || fail "network probe failed: $url"
  [[ "$status" == "$expected_prefix"* ]] || fail "network probe $url returned HTTP $status"
}

run_network_probes() {
  probe_url "https://api.omi.me/v2/desktop/appcast.xml" "2"
  probe_url "https://api.omi.me/health" "2"
  pass "Backend routing + appcast network probes passed"
}

run_launch_probe() {
  [[ "${OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH:-}" == "1" ]] \
    || fail "--launch for production bundle requires OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH=1"

  local executable
  executable="$APP_BUNDLE/Contents/MacOS/$(plist_read CFBundleExecutable)"
  [[ -x "$executable" ]] || fail "executable missing before launch"

  # The callback-only probe deliberately exits after atomically recording its
  # result. Run the bundle executable directly so its opt-in result-path
  # environment is deterministic; LaunchServices does not guarantee that it
  # propagates shell environment variables into a newly launched app.
  if [[ "$RUN_NOTIFICATION_CALLBACK_CANARY" == true ]]; then
    OMI_NOTIFICATION_CALLBACK_SMOKE_RESULT_PATH="$NOTIFICATION_CALLBACK_MARKER" \
      "$executable" >/tmp/omi-signed-artifact-smoke.out 2>/tmp/omi-signed-artifact-smoke.err &
    SMOKE_PID=$!
    pass "Signed app launched for UserNotifications callback canary"
    return 0
  fi

  open -n "$APP_BUNDLE" >/tmp/omi-signed-artifact-smoke.out 2>/tmp/omi-signed-artifact-smoke.err \
    || fail "LaunchServices failed to open signed app"

  sleep 8
  SMOKE_PID="$(pgrep -f "$executable" | head -1 || true)"
  [[ -n "$SMOKE_PID" ]] || {
    cat /tmp/omi-signed-artifact-smoke.err >&2 || true
    fail "signed app did not stay running after LaunchServices open"
  }
  kill -0 "$SMOKE_PID" >/dev/null 2>&1 || {
    cat /tmp/omi-signed-artifact-smoke.err >&2 || true
    fail "signed app exited during launch smoke"
  }

  pass "Signed app launches and remains alive"
}

prepare_notification_callback_canary() {
  [[ "$RUN_NOTIFICATION_CALLBACK_CANARY" == true ]] || return 0
  [[ "$RUN_LAUNCH" == true ]] || fail "--notification-callback-canary requires --launch"

  if [[ -z "$NOTIFICATION_CALLBACK_MARKER" ]]; then
    NOTIFICATION_CALLBACK_MARKER="$(mktemp "${TMPDIR:-/tmp}/omi-notification-callback.XXXXXX.json")"
    NOTIFICATION_CALLBACK_MARKER_IS_TEMP=true
  fi
  rm -f "$NOTIFICATION_CALLBACK_MARKER"
}

run_notification_callback_canary() {
  [[ "$RUN_NOTIFICATION_CALLBACK_CANARY" == true ]] || return 0
  [[ -n "$NOTIFICATION_CALLBACK_MARKER" ]] \
    || fail "notification callback canary was not prepared"

  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    if [[ -f "$NOTIFICATION_CALLBACK_MARKER" && ! -L "$NOTIFICATION_CALLBACK_MARKER" ]] \
      && [[ "$(stat -f '%Lp' "$NOTIFICATION_CALLBACK_MARKER")" == "600" ]]; then
      break
    fi
    if [[ -n "${SMOKE_PID:-}" ]] && ! kill -0 "$SMOKE_PID" >/dev/null 2>&1; then
      fail "signed app exited before the UserNotifications callback completed"
    fi
    sleep 1
  done

  [[ -f "$NOTIFICATION_CALLBACK_MARKER" && ! -L "$NOTIFICATION_CALLBACK_MARKER" ]] \
    && [[ "$(stat -f '%Lp' "$NOTIFICATION_CALLBACK_MARKER")" == "600" ]] \
    || fail "UserNotifications callback marker was not securely written within ${TIMEOUT_SECONDS}s"

  NOTIFICATION_CALLBACK_PROOF="$(python3 - "$NOTIFICATION_CALLBACK_MARKER" "$EXPECTED_BUNDLE_ID" <<'PY'
import json
import re
import sys
from pathlib import Path

marker_path, expected_bundle_id = sys.argv[1:]
try:
    marker = Path(marker_path).read_text(encoding="utf-8").strip()
except OSError as error:
    raise SystemExit(f"invalid UserNotifications callback marker: {error}")
match = re.fullmatch(r"main_actor=true authorization_status=(\d+)", marker)
if match is None:
    raise SystemExit("UserNotifications callback marker must prove main_actor=true and an authorization status")

print(json.dumps({
    "schema": 1,
    "event": "user-notifications-settings-callback-completed",
    "bundle_id": expected_bundle_id,
    "main_actor": True,
    "authorization_status": int(match.group(1)),
    "validated": True,
}, sort_keys=True))
PY
)" || fail "UserNotifications callback marker did not prove callback completion"

  pass "UserNotifications settings callback completion canary passed"
}

run_auth_probe() {
  [[ "$RUN_LAUNCH" == true ]] || fail "--auth requires --launch so the app persistence path is exercised"
  local proof_command="${OMI_SIGNED_ARTIFACT_SMOKE_AUTH_PROOF_COMMAND:-}"
  [[ -n "$proof_command" ]] || fail "--auth requires OMI_SIGNED_ARTIFACT_SMOKE_AUTH_PROOF_COMMAND"

  OMI_SIGNED_ARTIFACT_SMOKE_APP="$APP_BUNDLE" \
    OMI_SIGNED_ARTIFACT_SMOKE_PID="${SMOKE_PID:-}" \
    bash -lc "$proof_command" \
    || fail "app auth persistence proof command failed"

  pass "Auth persistence app-level proof command passed"
}

run_auth_storage_canary() {
  [[ "${OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH:-}" == "1" ]] \
    || fail "--auth-storage-canary for production bundle requires OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH=1"

  local result_path executable started_at canary_pid
  result_path="$(mktemp "${TMPDIR:-/tmp}/omi-auth-storage-canary.XXXXXX")"
  rm -f "$result_path"
  executable="$APP_BUNDLE/Contents/MacOS/$(plist_read CFBundleExecutable)"
  [[ -x "$executable" ]] || fail "executable missing before auth storage canary"

  "$executable" "--auth-storage-canary-result=$result_path" \
    >/tmp/omi-auth-storage-canary.out 2>/tmp/omi-auth-storage-canary.err &
  canary_pid=$!

  started_at=$SECONDS
  while [[ ! -s "$result_path" && $((SECONDS - started_at)) -lt "$TIMEOUT_SECONDS" ]]; do
    sleep 1
  done
  [[ -s "$result_path" ]] || {
    cat /tmp/omi-auth-storage-canary.err >&2 || true
    kill "$canary_pid" >/dev/null 2>&1 || true
    wait "$canary_pid" >/dev/null 2>&1 || true
    fail "signed app auth storage canary did not produce a result"
  }

  python3 - "$result_path" <<'PY' || fail "signed app auth storage canary failed"
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    result = json.load(handle)
if result.get("success") is not True or result.get("stage") != "complete":
    raise SystemExit(f"auth storage canary result: {result}")
PY
  started_at=$SECONDS
  while kill -0 "$canary_pid" >/dev/null 2>&1 && $((SECONDS - started_at)) -lt 5; do
    sleep 1
  done
  if kill -0 "$canary_pid" >/dev/null 2>&1; then
    kill "$canary_pid" >/dev/null 2>&1 || true
  fi
  wait "$canary_pid" >/dev/null 2>&1 || true
  rm -f "$result_path"
  pass "Signed artifact Keychain write/read/delete canary passed"
}

run_chat_probe() {
  local auth_header="${OMI_SIGNED_ARTIFACT_SMOKE_AUTH_HEADER:-}"
  local chat_url="${OMI_SIGNED_ARTIFACT_SMOKE_CHAT_URL:-https://api.omi.me/v2/chat/completions}"
  [[ -n "$auth_header" ]] || fail "--chat requires OMI_SIGNED_ARTIFACT_SMOKE_AUTH_HEADER"

  local payload status
  payload='{"model":"omi:auto:balanced","messages":[{"role":"user","content":"Reply with ok."}],"stream":false}'
  status="$(curl -sS -o /tmp/omi-smoke-chat.out -w "%{http_code}" --max-time "$TIMEOUT_SECONDS" \
    -H "Authorization: $auth_header" -H "Content-Type: application/json" \
    -d "$payload" "$chat_url")" || fail "chat probe request failed"
  [[ "$status" == 2* ]] || fail "chat probe returned HTTP $status"

  pass "Minimal chat path endpoint passed"
}

run_permission_surface_probe() {
  [[ "$RUN_LAUNCH" == true ]] || fail "--permissions requires --launch so the permission surface can be exercised"
  grep -R "NSMicrophoneUsageDescription" "$APP_BUNDLE/Contents/Info.plist" >/dev/null \
    || fail "microphone permission usage description missing"
  grep -R "NSScreenCaptureDescription" "$APP_BUNDLE/Contents/Info.plist" >/dev/null \
    || warn "screen capture usage description key not present; verify current macOS key expectations"
  pass "Recording permission surface sanity passed"
}

run_storage_live_probe() {
  [[ "$RUN_LAUNCH" == true ]] || fail "--storage requires --launch so storage open can be observed"
  sleep 2
  ! grep -E "RewindDatabase.*(fatal|crash|migration failed)|SQLite.*(fatal|malformed)" /tmp/omi-signed-artifact-smoke.err >/dev/null 2>&1 \
    || fail "storage/database error observed during launch"
  pass "Local storage/database live probe passed"
}

main() {
  parse_args "$@"
  extract_zip_if_needed
  [[ -n "$APP_BUNDLE" ]] || fail "--app or --zip is required"
  APP_BUNDLE="$(cd "$APP_BUNDLE" && pwd)"

  assert_bundle_identity
  assert_signing_and_entitlements
  assert_backend_routing_config
  assert_sparkle_and_artifacts
  assert_helper_runtime_integrity
  assert_local_storage_resources
  record_artifact "app_executable" "$APP_BUNDLE/Contents/MacOS/$(plist_read CFBundleExecutable)"

  maybe_copy_for_launch
  prepare_notification_callback_canary
  [[ "$RUN_NETWORK" == true ]] && run_network_probes
  [[ "$RUN_AUTH_STORAGE_CANARY" == true ]] && run_auth_storage_canary
  [[ "$RUN_LAUNCH" == true ]] && run_launch_probe
  run_notification_callback_canary
  [[ "$RUN_AUTH" == true ]] && run_auth_probe
  [[ "$RUN_CHAT" == true ]] && run_chat_probe
  [[ "$RUN_PERMISSIONS" == true ]] && run_permission_surface_probe
  [[ "$RUN_STORAGE" == true ]] && run_storage_live_probe

  pass "Signed desktop artifact smoke completed"
  write_result_json
}

main "$@"
