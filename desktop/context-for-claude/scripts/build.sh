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
#   scripts/build.sh --release       sign with release entitlements (no library-validation disable)
#
# Release-only environment:
#   CONTEXT_SPARKLE_PUBLIC_KEY       Context's 44-character Ed25519 public key
#   CONTEXT_VERSION                  version injected into the built Info.plist
#   CONTEXT_BUILD_NUMBER             numeric Sparkle build number injected into the built Info.plist
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

SIGN_IDENTITY="${CONTEXT_SIGN_IDENTITY:-Omi Local Dev Signing}"

# APP_NAME, BUNDLE_ID and the install path are derived from the signing identity below: a build
# that is not signed for release must not answer to the production identifiers. The template
# Info.plist is the release source of truth, so it is asserted against this value.
PRODUCTION_BUNDLE_ID="com.omi.context-for-claude"

BUILD_DIR="$PKG_DIR/build"
INFO_PLIST_TEMPLATE="$PKG_DIR/Resources/Info.plist"
ENTITLEMENTS_RELEASE="$PKG_DIR/Resources/ContextForClaude.entitlements"
ENTITLEMENTS_DEV="$PKG_DIR/Resources/ContextForClaudeDev.entitlements"
ENTITLEMENTS="$ENTITLEMENTS_DEV"
FONTS_DIR="$PKG_DIR/Resources/Fonts"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

DO_INSTALL=1
DO_RUN=0
DO_CLEAN=0
DO_RELEASE=0
CONTEXT_VERSION_VALUE="${CONTEXT_VERSION:-}"
CONTEXT_BUILD_NUMBER_VALUE="${CONTEXT_BUILD_NUMBER:-}"
SPARKLE_PUBLIC_KEY="${CONTEXT_SPARKLE_PUBLIC_KEY:-}"

log()  { printf '\033[1m[context]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[context]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[context]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------------------------
# Platform identity.
#
# Which identifiers this build claims follows from which certificate signs it. build-identity.sh
# owns that mapping and documents why a developer build must not share the production bundle id:
# macOS pins the signing certificate inside every TCC grant, so two differently-signed builds with
# one identifier write records neither can satisfy. It is a separate file so that
# scripts/test-build-identity.sh can drive the rule without a keychain or codesign.
# ---------------------------------------------------------------------------------------------
IDENTITY_ASSIGNMENTS="$("$SCRIPT_DIR/build-identity.sh" "$SIGN_IDENTITY")" \
    || die "refusing to build: no platform identity for signing identity '$SIGN_IDENTITY'"
eval "$IDENTITY_ASSIGNMENTS"

APP_NAME="$CFC_APP_NAME"
BUNDLE_ID="$CFC_BUNDLE_ID"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
INSTALL_PATH="/Applications/$APP_NAME.app"

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
        --release)    DO_RELEASE=1 ;;
        -h|--help)
            sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) die "unknown flag: $1 (see --help)" ;;
    esac
    shift
done

is_valid_sparkle_public_key() {
    local key="$1"
    [[ "$key" != "REPLACE_WITH_SUPublicEDKey_FROM_generate_keys" ]] \
        && [[ "$key" =~ ^[A-Za-z0-9+/]{43}=$ ]]
}

if [[ -n "$CONTEXT_VERSION_VALUE" ]]; then
    [[ "$CONTEXT_VERSION_VALUE" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || die "CONTEXT_VERSION must be a stable semantic version (x.y.z), got '$CONTEXT_VERSION_VALUE'"
fi
if [[ -n "$CONTEXT_BUILD_NUMBER_VALUE" ]]; then
    [[ "$CONTEXT_BUILD_NUMBER_VALUE" =~ ^[1-9][0-9]*$ ]] \
        || die "CONTEXT_BUILD_NUMBER must be a positive integer"
fi

if [[ "$DO_RELEASE" -eq 1 ]]; then
    [[ "$SIGN_IDENTITY" == *"Developer ID Application:"* ]] \
        || die "--release requires a Developer ID Application identity; local signing is for development only"
    [[ -n "$SPARKLE_PUBLIC_KEY" ]] \
        || die "--release requires CONTEXT_SPARKLE_PUBLIC_KEY; refusing to ship the placeholder Sparkle key"
    is_valid_sparkle_public_key "$SPARKLE_PUBLIC_KEY" \
        || die "CONTEXT_SPARKLE_PUBLIC_KEY is invalid; refusing to ship the placeholder Sparkle key"
fi

if [[ "$CFC_IS_DEVELOPMENT" -eq 0 ]]; then
    ENTITLEMENTS="$ENTITLEMENTS_RELEASE"
    log "using release entitlements: $ENTITLEMENTS"
else
    log "building as $BUNDLE_ID ($APP_NAME) — a developer identity, separate from any installed release"
    log "using development entitlements: $ENTITLEMENTS"
fi

[[ -f "$ENTITLEMENTS" ]] || die "missing entitlements at $ENTITLEMENTS"

[[ -f "$INFO_PLIST_TEMPLATE" ]] || die "missing Info.plist template at $INFO_PLIST_TEMPLATE"
[[ -f "$ENTITLEMENTS" ]] || die "missing entitlements at $ENTITLEMENTS"

# The template is the source of truth for the *release* identifier. A developer build gets its own
# identifier written into the built copy further down, never into the template — a template that
# already said `.dev` would ship a developer identity in a release.
TEMPLATE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$INFO_PLIST_TEMPLATE" 2>/dev/null || true)"
assert_not_production "Info.plist CFBundleIdentifier" "$TEMPLATE_ID"
[[ "$TEMPLATE_ID" == "$PRODUCTION_BUNDLE_ID" ]] \
    || die "Info.plist CFBundleIdentifier is '$TEMPLATE_ID', expected '$PRODUCTION_BUNDLE_ID'"

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
# ---------------------------------------------------------------------------------------------
# Every dependency this package has is a public repository or a public release asset, so SwiftPM has
# no credential to look up — but it searches the login keychain anyway, and on a CI machine that
# search fails with errSecInteractionNotAllowed (-25308) and takes the whole resolve down with it.
# Disabling the search is therefore a statement of fact about this package, not a workaround: there
# are no private dependencies for a keychain lookup to help with.
SWIFT_AUTH_FLAGS=(--disable-keychain)

log "building ContextApp (release)"
# Host architecture (no arm64-only triple): Intel Macs get an x86_64 binary; Silicon gets arm64.
swift build -c release --package-path "$PKG_DIR" "${SWIFT_AUTH_FLAGS[@]}" --product ContextApp

log "building context-for-claude-mcp (release)"
swift build -c release --package-path "$PKG_DIR" "${SWIFT_AUTH_FLAGS[@]}" --product context-for-claude-mcp

BIN_DIR="$(swift build -c release --package-path "$PKG_DIR" "${SWIFT_AUTH_FLAGS[@]}" --show-bin-path)"
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

# The app binary is installed under $APP_NAME, and CFBundleExecutable is set to match when a
# developer build renames it; context-for-claude-mcp rides along in the same directory because
# Claude launches it by absolute path.
cp -f "$BIN_DIR/ContextApp" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
cp -f "$BIN_DIR/context-for-claude-mcp" "$APP_BUNDLE/Contents/MacOS/context-for-claude-mcp"
chmod +x "$APP_BUNDLE/Contents/MacOS/$APP_NAME" "$APP_BUNDLE/Contents/MacOS/context-for-claude-mcp"

# ---------------------------------------------------------------------------------------------
# Sparkle
#
# The app's only embedded framework, and the one that turns a mistake in this script into an app
# that does not launch at all. Two things have to be true or dyld refuses the process outright:
# the framework is inside Contents/Frameworks, and the executable carries an rpath that resolves
# `@rpath/Sparkle.framework/Versions/B/Sparkle` to it. There is no partial success here — the app
# either starts or dies before `main`, with a crash log nobody reads as "the build script skipped
# a step". So this section dies loudly rather than warning, unlike the fonts and the icon above,
# whose absence only degrades what the app looks like.
#
# `context-for-claude-mcp` deliberately does not get the rpath: only ContextApp links Sparkle, and
# an MCP server that could not start because of a missing updater framework would be a very odd
# failure to debug.
# ---------------------------------------------------------------------------------------------
SPARKLE_SRC=""
for candidate in \
    "$BIN_DIR/Sparkle.framework" \
    "$PKG_DIR/.build/$(uname -m)-apple-macosx/release/Sparkle.framework"
do
    if [[ -d "$candidate" ]]; then SPARKLE_SRC="$candidate"; break; fi
done
[[ -n "$SPARKLE_SRC" ]] \
    || die "Sparkle.framework is not in the build output (looked in $BIN_DIR).
SwiftPM copies it there when the Sparkle binary target resolves. Run:
  swift package --package-path \"$PKG_DIR\" resolve
and build again. Shipping without it produces a bundle that dyld refuses to launch."

log "embedding $(basename "$SPARKLE_SRC") ($(du -sh "$SPARKLE_SRC" 2>/dev/null | cut -f1))"
mkdir -p "$APP_BUNDLE/Contents/Frameworks"
rm -rf "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
# `ditto`, not `cp -R`: a framework is a symlink farm (Versions/Current, and the top-level aliases
# into it) plus extended attributes, and ditto is the one tool that reproduces all of it exactly.
ditto "$SPARKLE_SRC" "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"

# Idempotent: `install_name_tool` errors if the rpath is already there, and a binary that was just
# copied over never is — but the check costs nothing and makes a re-run of this script safe.
#
# It also has to stay *above* the signing section: rewriting a Mach-O invalidates its signature, so
# an rpath added after signing produces a bundle macOS kills on launch. Nothing is signed yet here,
# which is the point.
if ! otool -l "$APP_BUNDLE/Contents/MacOS/$APP_NAME" | grep -q "@executable_path/../Frameworks"; then
    install_name_tool -add_rpath "@executable_path/../Frameworks" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
fi

cp -f "$INFO_PLIST_TEMPLATE" "$APP_BUNDLE/Contents/Info.plist"

# A developer build claims its own identity. All four keys move together by necessity: the binary
# was copied to Contents/MacOS/$APP_NAME above, so CFBundleExecutable has to follow it or macOS
# cannot launch the bundle at all, and CFBundleName is the name macOS shows in the Screen Recording
# and Microphone prompts — leaving it as the release name would put two indistinguishable
# "Context for Claude" rows in System Settings for two different identifiers.
if [[ "$CFC_IS_DEVELOPMENT" -eq 1 ]]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$APP_BUNDLE/Contents/Info.plist"
    /usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
    /usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
    /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
fi

# Release metadata belongs to the immutable built bundle, not the source template. This lets a tag
# select the version in CI without making a release worker edit Info.plist in the shared checkout.
if [[ -n "$CONTEXT_VERSION_VALUE" ]]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $CONTEXT_VERSION_VALUE" \
        "$APP_BUNDLE/Contents/Info.plist"
fi
if [[ -n "$CONTEXT_BUILD_NUMBER_VALUE" ]]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $CONTEXT_BUILD_NUMBER_VALUE" \
        "$APP_BUNDLE/Contents/Info.plist"
fi
if [[ -n "$SPARKLE_PUBLIC_KEY" ]]; then
    is_valid_sparkle_public_key "$SPARKLE_PUBLIC_KEY" \
        || die "CONTEXT_SPARKLE_PUBLIC_KEY is invalid; refusing to write it to the built Info.plist"
    /usr/libexec/PlistBuddy -c "Set :SUPublicEDKey $SPARKLE_PUBLIC_KEY" \
        "$APP_BUNDLE/Contents/Info.plist"
elif [[ "$DO_RELEASE" -eq 1 ]]; then
    die "--release requires CONTEXT_SPARKLE_PUBLIC_KEY; refusing to write a placeholder key"
else
    warn "no CONTEXT_SPARKLE_PUBLIC_KEY set — local build retains the source placeholder and cannot auto-update"
fi

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
#
# Sparkle makes "nested code" mean more than it used to. The framework contains four separately
# sealed pieces of its own — two XPC services, the Updater.app that draws the update sheet, and the
# Autoupdate helper that outlives this process to swap the bundle — and they arrive signed by the
# Sparkle project, not by us. `codesign` does not descend into them, so re-signing only the
# framework leaves four foreign signatures inside a bundle that claims to be ours. Locally that
# produces a `--deep --strict` verification failure; at release time it produces a notarization
# rejection, which is a far more expensive place to learn it. Hence sign_code(), applied
# innermost-first.
#
# Deliberately no `--entitlements` on any Sparkle code. The app's entitlements ask for microphone
# and screen capture, and the development pair also disables library validation; none of that
# belongs on a downloader or on an installer helper, and granting it would widen the attack surface
# of the one component whose whole job is to execute code it fetched from the internet.
# ---------------------------------------------------------------------------------------------
[[ "$SIGN_IDENTITY" != "-" ]] || die "ad-hoc signing is forbidden — it resets Screen Recording consent for every Omi app"
assert_not_production "signing target" "$APP_BUNDLE"

# Signs one piece of nested code with no entitlements. A secure timestamp is added only for a real
# Developer ID: notarization requires one, and it costs a round trip to Apple that a local dev build
# should not have to make (and cannot, offline).
sign_code() {
    local target="$1"
    assert_not_production "signing target" "$target"
    if [[ "$SIGN_IDENTITY" == *"Developer ID"* ]]; then
        codesign --force --options runtime --timestamp --sign "$SIGN_IDENTITY" "$target"
    else
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$target"
    fi
}

SPARKLE_FW="$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
SPARKLE_VERSION_DIR="$SPARKLE_FW/Versions/Current"
[[ -d "$SPARKLE_VERSION_DIR" ]] || SPARKLE_VERSION_DIR="$SPARKLE_FW/Versions/B"
[[ -d "$SPARKLE_VERSION_DIR" ]] \
    || die "Sparkle.framework has no versioned directory at $SPARKLE_FW/Versions — the copy above is broken"

log "signing Sparkle's nested code"
for nested in \
    "$SPARKLE_VERSION_DIR/XPCServices/Downloader.xpc" \
    "$SPARKLE_VERSION_DIR/XPCServices/Installer.xpc" \
    "$SPARKLE_VERSION_DIR/Updater.app" \
    "$SPARKLE_VERSION_DIR/Autoupdate"
do
    # Sparkle's layout has changed across major versions and will again. Skip what is not there
    # rather than pinning this script to one release's file list — but the framework itself, below,
    # is not optional.
    [[ -e "$nested" ]] || continue
    sign_code "$nested"
done
sign_code "$SPARKLE_FW"

log "signing nested context-for-claude-mcp"
codesign --force --options runtime --entitlements "$ENTITLEMENTS" \
    --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/MacOS/context-for-claude-mcp"

log "signing $APP_NAME.app with '$SIGN_IDENTITY'"
if [[ "$SIGN_IDENTITY" == *"Developer ID"* ]]; then
    codesign --force --options runtime --timestamp --entitlements "$ENTITLEMENTS" \
        --sign "$SIGN_IDENTITY" "$APP_BUNDLE"
else
    codesign --force --options runtime --entitlements "$ENTITLEMENTS" \
        --sign "$SIGN_IDENTITY" "$APP_BUNDLE"
fi

# `--deep`, which the old line did not have. Without it verification stops at the app's own seal and
# says nothing about the framework inside — which is the only part of this bundle that has ever been
# signed by somebody else.
codesign --verify --deep --strict "$APP_BUNDLE" \
    || die "signature verification failed for $APP_BUNDLE (run: codesign --verify --deep --strict --verbose=4 '$APP_BUNDLE')"

# The two facts an update has to preserve, printed every build so they are familiar before they
# matter. macOS keys Screen Recording, Microphone and System Audio consent on the signature — the
# authority and the Team ID below — so a release signed with a different identity than the release
# before it silently revokes every grant its users have given. `docs/releasing.md` makes checking
# these a release step; printing them here is what makes the release step readable.
log "signing identity of the bundle just built:"
codesign -dv --verbose=2 "$APP_BUNDLE" 2>&1 \
    | grep -E '^(Authority|TeamIdentifier|Identifier)=' \
    | sed 's/^/    /' || true

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
