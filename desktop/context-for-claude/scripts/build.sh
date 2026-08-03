#!/bin/bash
#
# Builds, signs, and installs Context for Claude (menu-bar app + the context-for-claude-mcp stdio server).
#
# Idempotent: run it as often as you like. Every run rebuilds the bundle from scratch under
# build/, signs it with the local dev identity, and replaces /Applications/Context for Claude.app.
#
# Usage:
#   scripts/build.sh                 build, sign, install to /Applications, print the MCP path
#   scripts/build.sh --no-install    stop after the signed bundle in build/
#   scripts/build.sh --run           also launch the installed app
#   scripts/build.sh --clean         wipe .build/ and build/ first
#
# SAFETY: this script only ever touches Context for Claude. It never reads, writes, signs, launches, or kills
# /Applications/Omi.app, /Applications/Omi Beta.app, or any com.omi.computer-macos* bundle, and
# assert_not_production() below aborts the run if any path or identifier it is about to act on
# looks like one of them.

set -euo pipefail

# PATH gets clobbered in some agent shells; make the tools we call resolvable.
export PATH="/bin:/usr/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="Context for Claude"
BUNDLE_ID="com.omi.context-for-claude"
SIGN_IDENTITY="${CONTEXT_SIGN_IDENTITY:-Omi Local Dev Signing}"

BUILD_DIR="$PKG_DIR/build"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
INSTALL_PATH="/Applications/$APP_NAME.app"
INFO_PLIST_TEMPLATE="$PKG_DIR/Resources/Info.plist"
ENTITLEMENTS="$PKG_DIR/Resources/ContextForClaude.entitlements"
FONTS_DIR="$PKG_DIR/Resources/Fonts"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

DO_INSTALL=1
DO_RUN=0
DO_CLEAN=0

log()  { printf '\033[1m[context]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[context]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[context]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------------------------
# Production-app guard.
#
# Every destructive step (rm -rf, codesign, quit, lsregister, open) routes its target through
# this first. Matching is case-insensitive and substring-based so no spelling of the production
# bundles can slip past.
# ---------------------------------------------------------------------------------------------
assert_not_production() {
    local what="$1" value="$2"
    local matched=0
    shopt -s nocasematch
    if [[ "$value" == *"/Applications/Omi.app"* ]] \
        || [[ "$value" == *"/Applications/Omi Beta.app"* ]] \
        || [[ "$value" == "Omi" ]] || [[ "$value" == "Omi.app" ]] \
        || [[ "$value" == "Omi Beta" ]] || [[ "$value" == "Omi Beta.app" ]] \
        || [[ "$value" == *"Omi Computer"* ]] \
        || [[ "$value" == *"com.omi.computer-macos"* ]]; then
        matched=1
    fi
    shopt -u nocasematch
    if [[ "$matched" -eq 1 ]]; then
        die "refusing to continue: $what resolves to a production Omi target ('$value'). This script only ever touches Context for Claude."
    fi
}

# The guard the brief asks for, applied to the constants themselves before anything runs.
assert_not_production "APP_NAME" "$APP_NAME"
assert_not_production "APP_NAME bundle" "$APP_NAME.app"
assert_not_production "BUNDLE_ID" "$BUNDLE_ID"
assert_not_production "install path" "$INSTALL_PATH"
assert_not_production "build bundle" "$APP_BUNDLE"
[[ "$(basename "$INSTALL_PATH")" == "$APP_NAME.app" ]] \
    || die "install path basename must be $APP_NAME.app, got $(basename "$INSTALL_PATH")"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-install) DO_INSTALL=0 ;;
        --run)        DO_RUN=1 ;;
        --clean)      DO_CLEAN=1 ;;
        -h|--help)
            sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) die "unknown flag: $1 (see --help)" ;;
    esac
    shift
done

[[ -f "$INFO_PLIST_TEMPLATE" ]] || die "missing Info.plist template at $INFO_PLIST_TEMPLATE"
[[ -f "$ENTITLEMENTS" ]] || die "missing entitlements at $ENTITLEMENTS"

# The template is the source of truth for the identifier; make sure it agrees with the guard.
TEMPLATE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$INFO_PLIST_TEMPLATE" 2>/dev/null || true)"
assert_not_production "Info.plist CFBundleIdentifier" "$TEMPLATE_ID"
[[ "$TEMPLATE_ID" == "$BUNDLE_ID" ]] \
    || die "Info.plist CFBundleIdentifier is '$TEMPLATE_ID', expected '$BUNDLE_ID'"

if ! security find-identity -v -p codesigning 2>/dev/null | grep -q "$SIGN_IDENTITY"; then
  # Any self-signed codesigning certificate works. What must not happen is ad-hoc signing: the
  # signature changes on every build, so macOS treats each build as a new app and Screen Recording
  # and microphone consent are revoked every time — for every Omi app on the machine, not just this
  # one. A stable identity is what makes the grants stick.
  die "signing identity '$SIGN_IDENTITY' is not in your keychain.

Create one once (30 seconds, no Apple Developer account needed):
  1. Open Keychain Access → menu Keychain Access → Certificate Assistant →
     Create a Certificate…
  2. Name: $SIGN_IDENTITY
     Identity Type: Self Signed Root
     Certificate Type: Code Signing
  3. Create, then re-run this script.

Or point at a certificate you already have:
  CONTEXT_SIGN_IDENTITY='Your Identity Name' $0

Do not ad-hoc sign ('-'): the signature changes every build, so macOS revokes
Screen Recording and microphone consent each time."
fi

# ---------------------------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------------------------
if [[ "$DO_CLEAN" -eq 1 ]]; then
    assert_not_production "clean target" "$PKG_DIR/.build"
    assert_not_production "clean target" "$BUILD_DIR"
    log "cleaning $PKG_DIR/.build and $BUILD_DIR"
    rm -rf "$PKG_DIR/.build" "$BUILD_DIR"
fi

# ---------------------------------------------------------------------------------------------
# Build
#
# Plain `swift build` on the host architecture — no `--triple arm64-…` hardcode. That keeps
# Intel Macs able to produce a native x86_64 binary for local QA. Release builds that must run
# on both Apple Silicon and Intel should lipo a universal binary (or ship per-arch artifacts);
# this script intentionally stays host-native.
# ---------------------------------------------------------------------------------------------
log "building ContextApp (release)"
swift build -c release --package-path "$PKG_DIR" --product ContextApp

log "building context-for-claude-mcp (release)"
swift build -c release --package-path "$PKG_DIR" --product context-for-claude-mcp

BIN_DIR="$(swift build -c release --package-path "$PKG_DIR" --show-bin-path)"
[[ -n "$BIN_DIR" && -d "$BIN_DIR" ]] || die "could not resolve the SPM bin path"
[[ -x "$BIN_DIR/ContextApp" ]] || die "ContextApp binary missing at $BIN_DIR/ContextApp"
[[ -x "$BIN_DIR/context-for-claude-mcp" ]] || die "context-for-claude-mcp binary missing at $BIN_DIR/context-for-claude-mcp"

# ---------------------------------------------------------------------------------------------
# Assemble build/Context for Claude.app
# ---------------------------------------------------------------------------------------------
assert_not_production "bundle staging path" "$APP_BUNDLE"
log "assembling $APP_BUNDLE"
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

# CFBundleExecutable is "Context for Claude", so the app binary is installed under that name; context-for-claude-mcp
# rides along in the same directory because Claude launches it by absolute path.
cp -f "$BIN_DIR/ContextApp" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
cp -f "$BIN_DIR/context-for-claude-mcp" "$APP_BUNDLE/Contents/MacOS/context-for-claude-mcp"
chmod +x "$APP_BUNDLE/Contents/MacOS/$APP_NAME" "$APP_BUNDLE/Contents/MacOS/context-for-claude-mcp"

cp -f "$INFO_PLIST_TEMPLATE" "$APP_BUNDLE/Contents/Info.plist"

# Firebase Web API key for project `based-hardware`. This is a public client key by design — it
# identifies the project to identitytoolkit/securetoken and grants nothing on its own; the user's
# actual credential is the OAuth code they get in the browser. It is injected at build time rather
# than committed to this package so there is exactly one copy of it on disk, in the Omi checkout
# that already ships it.
# Found relative to this checkout: Context for Claude lives at desktop/context-for-claude inside the Omi repo, and the
# plist ships at desktop/macos. `OMI_GOOGLE_SERVICE_PLIST` overrides it for a checkout laid out
# differently. An absolute path to somebody's home directory would build only on their machine.
GS_PLIST="${OMI_GOOGLE_SERVICE_PLIST:-$PKG_DIR/../macos/Desktop/Sources/GoogleService-Info.plist}"
if [[ -f "$GS_PLIST" ]]; then
  FB_KEY="$(/usr/libexec/PlistBuddy -c 'Print :API_KEY' "$GS_PLIST" 2>/dev/null || true)"
  if [[ -n "$FB_KEY" ]]; then
    /usr/libexec/PlistBuddy -c "Add :OmiFirebaseAPIKey string $FB_KEY" "$APP_BUNDLE/Contents/Info.plist" >/dev/null 2>&1 \
      || /usr/libexec/PlistBuddy -c "Set :OmiFirebaseAPIKey $FB_KEY" "$APP_BUNDLE/Contents/Info.plist" >/dev/null
    log "injected Firebase web API key (project based-hardware)"
  else
    warn "could not read API_KEY from $GS_PLIST — sign-in will fail"
  fi
else
  warn "$GS_PLIST not found — sign-in will fail without FIREBASE_API_KEY in the environment"
fi

plutil -lint "$APP_BUNDLE/Contents/Info.plist" >/dev/null || die "generated Info.plist is not valid"
printf 'APPL????' > "$APP_BUNDLE/Contents/PkgInfo"

if [[ -d "$FONTS_DIR" ]]; then
    mkdir -p "$APP_BUNDLE/Contents/Resources/Fonts"
    FONT_COUNT=0
    # zsh does not word-split unquoted variables; read the list explicitly so this behaves the
    # same under either shell.
    while IFS= read -r font; do
        [[ -n "$font" ]] || continue
        cp -f "$font" "$APP_BUNDLE/Contents/Resources/Fonts/"
        FONT_COUNT=$((FONT_COUNT + 1))
    # Open Runde ships as OpenType/CFF, so both extensions travel — a `.ttf`-only glob would leave
    # the bundle with no faces at all and every role falling back to the system font.
    done < <(find "$FONTS_DIR" -maxdepth 1 -type f \( -name '*.otf' -o -name '*.ttf' \) | sort)
    log "copied $FONT_COUNT font(s)"

# The app icon. Without it macOS shows a blank generic tile wherever the app is named — Finder,
# Login Items, and the Screen Recording pane the user grants permission in, which is the first
# place they ever see this app identified.
ICON_SRC="$PKG_DIR/Resources/ContextForClaude.icns"
if [[ -f "$ICON_SRC" ]]; then
  cp -f "$ICON_SRC" "$APP_BUNDLE/Contents/Resources/ContextForClaude.icns"
  log "copied app icon"
else
  warn "no app icon at $ICON_SRC — the app will show a blank tile"
fi
else
    warn "no Fonts directory at $FONTS_DIR — the app will fall back to system fonts"
fi

# SPM emits one resource bundle per target that declares resources; the app looks them up in
# Contents/Resources at runtime.
BUNDLE_COUNT=0
while IFS= read -r res; do
    [[ -n "$res" ]] || continue
    rm -rf "$APP_BUNDLE/Contents/Resources/$(basename "$res")"
    cp -R "$res" "$APP_BUNDLE/Contents/Resources/"
    BUNDLE_COUNT=$((BUNDLE_COUNT + 1))
done < <(find "$BIN_DIR" -maxdepth 1 -name '*.bundle' | sort)
log "copied $BUNDLE_COUNT SPM resource bundle(s)"

# ---------------------------------------------------------------------------------------------
# Sign
#
# Never ad-hoc ('-'): the runbook records that ad-hoc signing resets Screen Recording consent for
# every Omi app on this machine. Nested code is signed before the enclosing bundle, otherwise the
# outer seal is computed over an unsigned nested binary and codesign rejects it.
# ---------------------------------------------------------------------------------------------
[[ "$SIGN_IDENTITY" != "-" ]] || die "ad-hoc signing is forbidden — it resets Screen Recording consent for every Omi app"
assert_not_production "signing target" "$APP_BUNDLE"

log "signing nested context-for-claude-mcp"
codesign --force --options runtime --entitlements "$ENTITLEMENTS" \
    --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/MacOS/context-for-claude-mcp"

log "signing $APP_NAME.app with '$SIGN_IDENTITY'"
codesign --force --options runtime --entitlements "$ENTITLEMENTS" \
    --sign "$SIGN_IDENTITY" "$APP_BUNDLE"

codesign --verify --strict "$APP_BUNDLE" \
    || die "signature verification failed for $APP_BUNDLE"

if [[ "$DO_INSTALL" -eq 0 ]]; then
    log "built (not installed): $APP_BUNDLE"
    log "MCP binary: $APP_BUNDLE/Contents/MacOS/context-for-claude-mcp"
    if [[ "$DO_RUN" -eq 1 ]]; then
        assert_not_production "launch target" "$APP_BUNDLE"
        log "launching $APP_BUNDLE"
        # Full path, never `open -b`: by bundle id LaunchServices can resurrect a stale cached
        # signature that lacks the entitlements and dyld-crashes.
        open -a "$APP_BUNDLE"
    fi
    exit 0
fi

# ---------------------------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------------------------
assert_not_production "install target" "$INSTALL_PATH"

# Quit only a running Context for Claude, matched on its exact executable path, and re-checked per pid.
if [[ -d "$INSTALL_PATH" ]]; then
    RUNNING_EXEC="$INSTALL_PATH/Contents/MacOS/$APP_NAME"
    assert_not_production "quit target" "$RUNNING_EXEC"
    while IFS= read -r pid; do
        [[ -n "$pid" ]] || continue
        cmd="$(ps -o command= -p "$pid" 2>/dev/null || true)"
        [[ -n "$cmd" ]] || continue
        assert_not_production "process to quit (pid $pid)" "$cmd"
        [[ "$cmd" == "$RUNNING_EXEC"* ]] || continue
        log "quitting running $APP_NAME (pid $pid)"
        kill "$pid" 2>/dev/null || true
    done < <(pgrep -f "^$RUNNING_EXEC" 2>/dev/null || true)
fi

log "installing to $INSTALL_PATH"
rm -rf "$INSTALL_PATH"
ditto "$APP_BUNDLE" "$INSTALL_PATH"

# Register both copies. A self-relaunch (e.g. after granting Screen Recording) can pick the
# build-dir copy, so LaunchServices must hold a fresh signature for each.
if [[ -x "$LSREGISTER" ]]; then
    assert_not_production "lsregister target" "$INSTALL_PATH"
    assert_not_production "lsregister target" "$APP_BUNDLE"
    "$LSREGISTER" -f "$APP_BUNDLE" "$INSTALL_PATH" || warn "lsregister returned non-zero (continuing)"
else
    warn "lsregister not found at $LSREGISTER — skipping LaunchServices refresh"
fi

MCP_PATH="$INSTALL_PATH/Contents/MacOS/context-for-claude-mcp"

if [[ "$DO_RUN" -eq 1 ]]; then
    assert_not_production "launch target" "$INSTALL_PATH"
    log "launching $INSTALL_PATH"
    # Full path, never `open -b`.
    open -a "$INSTALL_PATH"
fi

echo
log "installed: $INSTALL_PATH"
log "MCP binary (register this absolute path with Claude):"
echo "$MCP_PATH"
echo
echo "  claude mcp add context-for-claude \"$MCP_PATH\""
