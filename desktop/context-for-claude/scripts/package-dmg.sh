#!/bin/bash
#
# Builds a distributable, styled drag-to-install disk image of Context for Claude.
#
# Distribution is the whole point of this script, so it is honest about whether what it produced is
# actually distributable. A macOS app that other people can open must be signed with a **Developer
# ID Application** certificate and **notarized** by Apple. Neither can be faked locally: Gatekeeper
# checks the signature against Apple's roots and asks Apple's servers about the notarization ticket.
# Without both, a downloaded app is refused with "damaged and can't be opened" — the same message a
# corrupted download gets, which is why users read it as the app being broken rather than unsigned.
#
# So this script signs with a Developer ID when one exists, notarizes when credentials exist, and
# tells you exactly what Gatekeeper says about the result either way.
#
#   CFC_SIGN_IDENTITY      "Developer ID Application: Your Name (TEAMID)"  — required for release
#   CFC_NOTARY_PROFILE     a notarytool keychain profile name              — required for release
#
# Create those once with:
#   xcrun notarytool store-credentials "context-notary" \
#       --apple-id you@example.com --team-id TEAMID --password <app-specific-password>
#
# The window itself is styled the standard way, with no extra dependency (`create-dmg` is not
# installed and is not worth adding): a read/write UDRW image is attached, dressed, arranged by
# driving Finder over AppleScript, detached, and only then compressed to UDZO. Every number describing
# the window comes from scripts/make-dmg-background.sh --print-geometry, which also paints the art, so
# the painted arrow and Finder's icon positions cannot drift apart.
#
# Flags:
#   --app <path>   package an existing .app instead of building one (skips scripts/build.sh entirely)
#   --skip-build   package whatever is already at build/<app>, without rebuilding
#   --out <path>   write the .dmg here instead of dist/
#   --no-style     emit a plain unstyled UDZO (for a machine with no Finder to drive)
#   --release      require Developer ID signing, a real Context Sparkle key, and notarization
#
# Release-only environment:
#   CONTEXT_SPARKLE_PUBLIC_KEY       Context's 44-character Ed25519 public key
#   CFC_SIGN_IDENTITY                Developer ID Application identity
#   CFC_NOTARY_PROFILE               optional local notarytool keychain profile
#   CFC_ASC_PRIVATE_KEY              optional App Store Connect API private key
#   CFC_ASC_KEY_ID / CFC_ASC_ISSUER_ID  matching App Store Connect API credentials
#
# Safety: this script only ever touches Context for Claude. assert_not_production() below aborts the
# run if any path, identifier, device node or volume it is about to act on looks like a production Omi
# target, and every destructive step (rm, SetFile, hdiutil detach, the AppleScript's window) is routed
# through it. The image is detached by the device node this run attached and no other.
#
set -euo pipefail

# PATH gets clobbered in some agent shells; make the tools we call resolvable.
export PATH="/bin:/usr/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="Context for Claude"
BUNDLE_ID="com.omi.context-for-claude"
DIST_DIR="$PKG_DIR/dist"
APP_BUNDLE="$PKG_DIR/build/$APP_NAME.app"
STAGE="$DIST_DIR/stage"
ICNS="$PKG_DIR/Resources/ContextForClaude.icns"
BG_SCRIPT="$SCRIPT_DIR/make-dmg-background.sh"
BG_DIR="$PKG_DIR/Resources/DMG"

log()  { printf '\033[1m[dmg]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[dmg]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[dmg]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- the production guard
#
# Same guard as build.sh. Anything that names a shipping Omi bundle stops the run dead, so no rm,
# SetFile, hdiutil detach or Finder command in this script can ever be aimed at one.
assert_not_production() {
    local what="$1" value="$2"
    local matched=0
    shopt -s nocasematch
    if [[ "$value" == *"/Applications/Omi.app"* ]] \
        || [[ "$value" == *"/Applications/Omi Beta.app"* ]] \
        || [[ "$value" == "Omi" ]] || [[ "$value" == "Omi.app" ]] \
        || [[ "$value" == "Omi Beta" ]] || [[ "$value" == "Omi Beta.app" ]] \
        || [[ "$value" == *"Omi Computer"* ]] \
        || [[ "$value" == *"com.omi.computer-macos"* ]] \
        || [[ "$value" == *"/Volumes/Omi"* ]]; then
        matched=1
    fi
    shopt -u nocasematch
    if [[ "$matched" -eq 1 ]]; then
        die "refusing to continue: $what resolves to a production Omi target ('$value'). This script only ever touches Context for Claude."
    fi
}

assert_not_production "APP_NAME" "$APP_NAME"
assert_not_production "APP_NAME bundle" "$APP_NAME.app"
assert_not_production "BUNDLE_ID" "$BUNDLE_ID"
assert_not_production "build bundle" "$APP_BUNDLE"
assert_not_production "stage" "$STAGE"

# ---------------------------------------------------------------- arguments

SOURCE_APP=""
DO_BUILD=1
DO_STYLE=1
OUT_DMG=""
DO_RELEASE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --app)        SOURCE_APP="${2:?--app needs a path}"; DO_BUILD=0; shift 2 ;;
        --skip-build) DO_BUILD=0; shift ;;
        --out)        OUT_DMG="${2:?--out needs a path}"; shift 2 ;;
        --no-style)   DO_STYLE=0; shift ;;
        --release)    DO_RELEASE=1; shift ;;
        -h|--help)    sed -n '2,36p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *)            die "unknown argument: $1" ;;
    esac
done

is_valid_sparkle_public_key() {
    local key="$1"
    [[ "$key" != "REPLACE_WITH_SUPublicEDKey_FROM_generate_keys" ]] \
        && [[ "$key" =~ ^[A-Za-z0-9+/]{43}=$ ]]
}

VERSION="${CONTEXT_VERSION:-$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PKG_DIR/Resources/Info.plist" 2>/dev/null || echo 1.0.0)}"
DMG="${OUT_DMG:-$DIST_DIR/ContextForClaude-$VERSION.dmg}"
assert_not_production "output image" "$DMG"

# ---------------------------------------------------------------- build + sign

RELEASE_IDENTITY="${CFC_SIGN_IDENTITY:-}"
RELEASE_MODE=0
if [[ "$DO_RELEASE" -eq 1 || -n "$RELEASE_IDENTITY" ]]; then
    RELEASE_MODE=1
fi
if [[ "$RELEASE_MODE" -eq 1 ]]; then
    [[ -n "$RELEASE_IDENTITY" ]] \
        || die "--release requires CFC_SIGN_IDENTITY"
    [[ "$RELEASE_IDENTITY" == *"Developer ID Application:"* ]] \
        || die "release packaging requires a Developer ID Application identity"
    [[ -n "${CONTEXT_SPARKLE_PUBLIC_KEY:-}" ]] \
        || die "release packaging requires CONTEXT_SPARKLE_PUBLIC_KEY; refusing to ship the placeholder Sparkle key"
    is_valid_sparkle_public_key "$CONTEXT_SPARKLE_PUBLIC_KEY" \
        || die "CONTEXT_SPARKLE_PUBLIC_KEY is invalid; refusing to ship the placeholder Sparkle key"
fi
if [[ -n "$SOURCE_APP" ]]; then
    # An explicit bundle. It still has to be *our* bundle: same name, same identifier.
    assert_not_production "--app" "$SOURCE_APP"
    [[ -d "$SOURCE_APP" ]] || die "no app bundle at $SOURCE_APP"
    [[ "$(basename "$SOURCE_APP")" == "$APP_NAME.app" ]] \
        || die "--app must point at '$APP_NAME.app', got '$(basename "$SOURCE_APP")'"
    GOT_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$SOURCE_APP/Contents/Info.plist" 2>/dev/null || echo '')"
    assert_not_production "--app CFBundleIdentifier" "$GOT_ID"
    [[ "$GOT_ID" == "$BUNDLE_ID" ]] || die "--app has CFBundleIdentifier '$GOT_ID', expected '$BUNDLE_ID'"
    APP_BUNDLE="$SOURCE_APP"
    log "packaging the existing bundle at $APP_BUNDLE (no build)"
elif [[ "$DO_BUILD" -eq 0 ]]; then
    [[ -d "$APP_BUNDLE" ]] || die "no app bundle at $APP_BUNDLE — drop --skip-build or pass --app"
    log "packaging the existing bundle at $APP_BUNDLE (no build)"
elif [[ -n "$RELEASE_IDENTITY" ]]; then
    security find-identity -v -p codesigning 2>/dev/null | grep -q "$RELEASE_IDENTITY" \
        || die "CFC_SIGN_IDENTITY '$RELEASE_IDENTITY' is not in the keychain"
    log "signing for distribution as: $RELEASE_IDENTITY"
    CONTEXT_SIGN_IDENTITY="$RELEASE_IDENTITY" "$SCRIPT_DIR/build.sh" --no-install --release
else
    warn "no CFC_SIGN_IDENTITY set — building with the local development identity."
    warn "The result will NOT open on anyone else's Mac. See the verdict at the end."
    "$SCRIPT_DIR/build.sh" --no-install
    # A build signed with the local development identity carries the *developer* bundle name and
    # identifier — it must not claim the production ones, because macOS pins the signing
    # certificate inside every TCC grant. So the bundle just built is not $APP_BUNDLE.
    # See scripts/build-identity.sh.
    eval "$("$SCRIPT_DIR/build-identity.sh" --kind development)"
    APP_BUNDLE="$PKG_DIR/build/$CFC_APP_NAME.app"
fi
[[ -d "$APP_BUNDLE" ]] || die "no app bundle at $APP_BUNDLE"

if [[ "$RELEASE_MODE" -eq 1 ]]; then
    BUNDLE_KEY="$(/usr/libexec/PlistBuddy -c 'Print :SUPublicEDKey' "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || true)"
    is_valid_sparkle_public_key "$BUNDLE_KEY" \
        || die "built app does not contain a valid Context Sparkle public key; refusing to package a placeholder"
fi

# ---------------------------------------------------------------- the updater, before anything else
#
# The app now embeds Sparkle, which is the first and only framework inside this bundle and therefore
# the first thing in it that can be wrong in a way the DMG cannot show you. A bundle whose framework
# is missing does not launch; a bundle whose framework carries somebody else's signature launches
# locally and is rejected by notarization, or worse, passes notarization and fails Gatekeeper on the
# user's machine. Both are cheap to detect here and expensive to detect after publishing, so the
# image is not built at all until both are ruled out. `--app` makes this more than paranoia: that
# flag packages a bundle this script did not build and cannot make assumptions about.
[[ -d "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework" ]] \
    || die "no Sparkle.framework in $APP_BUNDLE — that bundle cannot launch and must not be shipped. Rebuild with scripts/build.sh."
codesign --verify --deep --strict "$APP_BUNDLE" \
    || die "the app's signature does not verify with --deep (a nested Sparkle component is unsigned or signed by somebody else). Run: codesign --verify --deep --strict --verbose=4 '$APP_BUNDLE'"

# ---------------------------------------------------------------------------------------------
# The certificate, not its name.
#
# Every other release gate in this pipeline tests the *name* of the signing identity — `[[ ... ==
# *"Developer ID Application:"* ]]` here at the top, in build.sh, and in codemagic.yaml's
# find-identity grep. A self-signed certificate can be given any name its creator likes, so all of
# them are satisfied by a certificate Apple never issued. That matters more than it looks: macOS
# pins the signing certificate inside every TCC permission grant, so a build signed by the wrong
# certificate but carrying the production bundle identifier writes permission records the real
# release can never satisfy — the switch reads ON in System Settings and the app is denied anyway,
# with `tccutil reset` the only way out. This app shipped that state to a user for days.
#
# `codesign --verify` above proves the signature is *internally consistent*, not that Apple issued
# it. Only the authority chain does that, so read it off the bundle that is about to be shipped.
# ---------------------------------------------------------------------------------------------
assert_release_signing_authority() {
    local bundle="$1" authorities
    authorities="$(codesign -dv --verbose=4 "$bundle" 2>&1 | grep '^Authority=' || true)"

    local required=(
        "Authority=Developer ID Application:"
        "Authority=Developer ID Certification Authority"
        "Authority=Apple Root CA"
    )
    local needle
    for needle in "${required[@]}"; do
        [[ "$authorities" == *"$needle"* ]] || die "refusing to ship $bundle: its signature does not chain to Apple.

Expected an authority line containing '$needle'. The signature actually carries:
${authorities:-  (no Authority lines at all — the bundle is ad-hoc signed or unsigned)}

A certificate merely *named* 'Developer ID Application: ...' passes every other check in this
pipeline but is not one. Shipping it under $BUNDLE_ID would write TCC permission records pinned to
a certificate no future release can match, permanently breaking Screen Recording and Microphone for
every user who installs it. Import the real Developer ID Application certificate and rebuild."
    done
}

if [[ "$RELEASE_MODE" -eq 1 ]]; then
    assert_release_signing_authority "$APP_BUNDLE"
    log "signing authority verified: chains to Apple Root CA"
fi

# ---------------------------------------------------------------- notarize

NOTARY_PROFILE="${CFC_NOTARY_PROFILE:-}"
ASC_PRIVATE_KEY="${CFC_ASC_PRIVATE_KEY:-}"
ASC_KEY_ID="${CFC_ASC_KEY_ID:-}"
ASC_ISSUER_ID="${CFC_ASC_ISSUER_ID:-}"

has_notary_credentials() {
    [[ -n "$NOTARY_PROFILE" ]] \
        || [[ -n "$ASC_PRIVATE_KEY" && -n "$ASC_KEY_ID" && -n "$ASC_ISSUER_ID" ]]
}

notarize_path() {
    local target="$1"
    local payload="$target"
    local key_path=""
    local temporary_payload=0
    local created_key=0

    # Apple accepts an app only inside a ZIP for notarization, while the DMG must be submitted as
    # the disk image itself so the stapled ticket belongs to the downloadable DMG.
    if [[ "$target" == *.app ]]; then
        payload="${target}.notarize.zip"
        /usr/bin/ditto -c -k --keepParent "$target" "$payload"
        temporary_payload=1
    fi
    if [[ -n "$NOTARY_PROFILE" ]]; then
        if ! xcrun notarytool submit "$payload" --keychain-profile "$NOTARY_PROFILE" --wait; then
            [[ "$temporary_payload" -eq 0 ]] || rm -f "$payload"
            die "notarization failed for $(basename "$target")"
        fi
    else
        # The App Store Connect key arrives in one of three shapes, and every working Omi
        # notarization step in codemagic.yaml handles all three: a filesystem path, an `@file:` path,
        # or the PEM body itself — stored with *literal* `\n` escapes rather than real newlines, which
        # is why those steps use `echo -e` and this one must not use `printf '%s'`. Writing an
        # unexpanded single-line key here failed only when `notarytool` rejected it, roughly forty
        # minutes into a release, after the app had already been built and signed.
        if [[ "$ASC_PRIVATE_KEY" == /* ]] || [[ "$ASC_PRIVATE_KEY" == @file:* ]]; then
            key_path="${ASC_PRIVATE_KEY#@file:}"
            [[ -r "$key_path" ]] \
                || die "CFC_ASC_PRIVATE_KEY names a key file that cannot be read: $key_path"
        else
            key_path="$(mktemp /tmp/context-app-store-connect-key.XXXXXX)"
            chmod 600 "$key_path"
            created_key=1
            # %b expands the `\n` escapes; a PEM that already has real newlines passes through
            # unchanged, because a base64 key body carries no other backslash sequences.
            printf '%b\n' "$ASC_PRIVATE_KEY" > "$key_path"
        fi
        # Fail on a malformed key now rather than after the submission round-trip. Both conditions
        # matter: the header proves it is a key at all, and the line count proves the newlines
        # survived — a PEM collapsed onto one line still contains "PRIVATE KEY" and is still rejected
        # by notarytool, which is the exact failure this branch exists to prevent.
        if ! grep -q 'BEGIN .*PRIVATE KEY' "$key_path" || [[ "$(wc -l < "$key_path")" -lt 2 ]]; then
            [[ "$created_key" -eq 0 ]] || rm -f "$key_path"
            [[ "$temporary_payload" -eq 0 ]] || rm -f "$payload"
            die "the App Store Connect key is not a usable multi-line PEM; check how $([[ -n "${CFC_ASC_PRIVATE_KEY:-}" ]] && echo CFC_ASC_PRIVATE_KEY || echo 'the key') is stored (literal \\n escapes, real newlines, or a file path are all accepted)"
        fi
        if ! xcrun notarytool submit "$payload" \
            --key "$key_path" \
            --key-id "$ASC_KEY_ID" \
            --issuer "$ASC_ISSUER_ID" \
            --wait; then
            [[ "$created_key" -eq 0 ]] || rm -f "$key_path"
            [[ "$temporary_payload" -eq 0 ]] || rm -f "$payload"
            die "notarization failed for $(basename "$target")"
        fi
        [[ "$created_key" -eq 0 ]] || rm -f "$key_path"
    fi
    [[ "$temporary_payload" -eq 0 ]] || rm -f "$payload"
}

if [[ -n "$RELEASE_IDENTITY" ]]; then
  if [[ "$RELEASE_MODE" -eq 1 ]]; then
    has_notary_credentials \
      || die "release packaging requires CFC_NOTARY_PROFILE or the CFC_ASC_* App Store Connect credentials"
    log "notarizing the app — this uploads it to Apple and usually takes a few minutes"
    notarize_path "$APP_BUNDLE"
    # Stapling puts the ticket inside the bundle so a first launch works offline.
    xcrun stapler staple "$APP_BUNDLE" || die "app stapling failed"
    xcrun stapler validate "$APP_BUNDLE" || die "app staple validation failed"
    log "app notarized and stapled"
  elif has_notary_credentials; then
    log "notarizing the app — this uploads it to Apple and usually takes a few minutes"
    notarize_path "$APP_BUNDLE"
    xcrun stapler staple "$APP_BUNDLE" || die "app stapling failed"
    xcrun stapler validate "$APP_BUNDLE" || die "app staple validation failed"
    log "app notarized and stapled"
  else
    warn "signed for distribution but NOT notarized (no Context notary credentials)."
    warn "Gatekeeper will still refuse it on a machine that has not seen it before."
  fi
fi

# ---------------------------------------------------------------- window geometry + background art
#
# One source of truth: make-dmg-background.sh both paints the art and reports the numbers, so the
# arrow it draws between the two slots always lands between the icons Finder is told to place.
eval "$("$BG_SCRIPT" --print-geometry)"
: "${DMG_WIN_W:?}" "${DMG_WIN_H:?}" "${DMG_TITLEBAR_H:?}" "${DMG_WIN_X:?}" "${DMG_WIN_Y:?}"
: "${DMG_ICON_SIZE:?}" "${DMG_APP_X:?}" "${DMG_APP_Y:?}" "${DMG_LINK_X:?}" "${DMG_LINK_Y:?}"

# `background.png` is the 2x raster tagged 144 ppi so Finder lays it out at 1x points and draws it
# sharp on Retina. CFC_DMG_BACKGROUND_1X=1 falls back to the plain 72 ppi 1x render.
BG_FILE="$BG_DIR/background.png"
if [[ "${CFC_DMG_BACKGROUND_1X:-0}" == "1" ]]; then
    BG_FILE="$BG_DIR/background@1x.png"
fi

if [[ "$DO_STYLE" -eq 1 ]]; then
    # Repaint when the art is missing or older than its own renderer. The art used to be rebuilt when
    # the .icns changed too, because it lifted the app's glyph out of it for the top-left mark. That
    # mark is gone — the only icon the window shows is the app bundle Finder places in it — so the art
    # no longer reads the .icns and that dependency would only cause pointless repaints.
    if [[ ! -f "$BG_FILE" || "$BG_SCRIPT" -nt "$BG_FILE" ]]; then
        log "rendering the background art"
        "$BG_SCRIPT"
    fi
    [[ -f "$BG_FILE" ]] || die "no background art at $BG_FILE"
fi

# ---------------------------------------------------------------- driving Finder, safely
#
# osascript talking to Finder needs Automation permission for whatever is running this script
# (Terminal, iTerm, an agent shell...). Without it macOS either returns -1743 or puts up a consent
# dialog — and an unanswered dialog blocks osascript forever, which is how these scripts classically
# hang in CI. So: every osascript call gets a watchdog, and a cheap probe runs first so the failure
# arrives before an image has been built rather than after.
OSA_OUT=""
run_osascript() {   # run_osascript <timeout-seconds> <osascript args...>
    local limit="$1" rc=0 waited=0 pid
    shift
    local out; out="$(mktemp /tmp/cfc-osa.XXXXXX)"
    osascript "$@" >"$out" 2>&1 &
    pid=$!
    while kill -0 "$pid" 2>/dev/null; do
        if (( waited >= limit )); then
            kill -9 "$pid" 2>/dev/null || true
            set +e; wait "$pid" 2>/dev/null; set -e
            OSA_OUT="osascript did not return within ${limit}s"
            rm -f "$out"
            return 124
        fi
        sleep 1
        waited=$((waited + 1))
    done
    set +e; wait "$pid"; rc=$?; set -e
    OSA_OUT="$(cat "$out")"
    rm -f "$out"
    return "$rc"
}

automation_help() {
    warn "This script could not drive Finder over AppleScript."
    warn "  $OSA_OUT"
    warn "macOS gates Apple events behind Automation permission, per calling app:"
    warn "  System Settings > Privacy & Security > Automation > <your terminal> > Finder"
    warn "Grant it and re-run, or run with --no-style for a plain unstyled image."
}

if [[ "$DO_STYLE" -eq 1 ]]; then
    if ! run_osascript 20 -e 'tell application "Finder" to count of windows'; then
        automation_help
        die "no Automation permission for Finder (refusing to hang waiting for the consent dialog)"
    fi
fi

# ---------------------------------------------------------------- the image

MOUNT_POINT=""
ATTACHED_DEV=""

# Only ever detach the device node this run attached, and only while it is still mounted where we
# mounted it. Nothing here can reach a volume the script did not create.
detach_ours() {
    local dev="$ATTACHED_DEV"
    [[ -n "$dev" ]] || return 0
    assert_not_production "detach device" "$dev"
    assert_not_production "detach mount point" "$MOUNT_POINT"
    local live
    live="$(diskutil info "$dev" 2>/dev/null | awk -F': +' '/^ *Mount Point/{print $2; exit}')"
    if [[ -n "$live" && "$live" != "$MOUNT_POINT" ]]; then
        warn "refusing to detach $dev: it is mounted at '$live', not the '$MOUNT_POINT' this run attached"
        return 1
    fi
    local tries=0
    while (( tries < 8 )); do
        if hdiutil detach "$dev" >/dev/null 2>&1; then ATTACHED_DEV=""; MOUNT_POINT=""; return 0; fi
        tries=$((tries + 1))
        sleep 2
    done
    warn "$dev would not detach cleanly (Finder or Spotlight still holding it); forcing"
    hdiutil detach "$dev" -force >/dev/null 2>&1 || return 1
    ATTACHED_DEV=""; MOUNT_POINT=""
    return 0
}

TMP_DIR="$(mktemp -d /tmp/cfc-dmg.XXXXXX)"
cleanup() {
    detach_ours || true
    assert_not_production "stage cleanup" "$STAGE"
    rm -rf "$STAGE"
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

log "building $DMG"
mkdir -p "$DIST_DIR"
assert_not_production "stage" "$STAGE"
rm -rf "$STAGE"
assert_not_production "existing image" "$DMG"
rm -f "$DMG"
mkdir -p "$STAGE"
/usr/bin/ditto "$APP_BUNDLE" "$STAGE/$APP_NAME.app"
# The drag-to-install convention. Without the symlink people run the app from the mounted image,
# where it cannot be updated and its permissions are attached to a read-only volume path.
ln -s /Applications "$STAGE/Applications"

if [[ "$DO_STYLE" -eq 0 ]]; then
    hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
else
    # A styled image has to be writable while it is dressed, so it starts life as UDRW with enough
    # slack for the background art and the .DS_Store, and is compressed at the very end.
    STAGE_KB="$(du -sk "$STAGE" | cut -f1)"
    SIZE_MB=$(( STAGE_KB / 1024 + 60 ))
    RW_DMG="$TMP_DIR/rw.dmg"
    # HFS+, not APFS: the custom-volume-icon bit and the relative background alias are HFS conventions,
    # and SetFile only speaks to HFS. An APFS disk image also will not mount on older macOS.
    hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" \
        -fs HFS+ -fsargs "-c c=64,a=16,e=16" \
        -format UDRW -size "${SIZE_MB}m" -ov "$RW_DMG" >/dev/null

    # A leftover volume of the same name would make `tell disk "Context for Claude"` ambiguous, and
    # would tempt this script into touching a volume it did not attach. Refuse instead.
    if [[ -e "/Volumes/$APP_NAME" ]]; then
        die "'/Volumes/$APP_NAME' is already mounted. Eject it and re-run — this script will not style, arrange or detach a volume it did not attach itself."
    fi

    log "attaching the read/write image"
    hdiutil attach "$RW_DMG" -readwrite -noverify -noautoopen -plist > "$TMP_DIR/attach.plist"
    i=0
    while (( i < 32 )); do
        dev="$(/usr/libexec/PlistBuddy -c "Print :system-entities:$i:dev-entry" "$TMP_DIR/attach.plist" 2>/dev/null)" || break
        mp="$(/usr/libexec/PlistBuddy -c "Print :system-entities:$i:mount-point" "$TMP_DIR/attach.plist" 2>/dev/null)" || mp=""
        if [[ -n "$mp" ]]; then ATTACHED_DEV="$dev"; MOUNT_POINT="$mp"; fi
        i=$((i + 1))
    done
    [[ -n "$ATTACHED_DEV" && -n "$MOUNT_POINT" ]] || die "could not work out what hdiutil attached"
    assert_not_production "attached device" "$ATTACHED_DEV"
    assert_not_production "attached mount point" "$MOUNT_POINT"
    # Belt and braces: it must be the volume we just asked for, at exactly the path we expect.
    [[ "$MOUNT_POINT" == "/Volumes/$APP_NAME" ]] \
        || die "expected our image at '/Volumes/$APP_NAME', hdiutil mounted it at '$MOUNT_POINT'"
    [[ -d "$MOUNT_POINT/$APP_NAME.app" ]] || die "$MOUNT_POINT does not contain $APP_NAME.app"
    log "attached $ATTACHED_DEV at $MOUNT_POINT"

    # Dress the volume: the art, the volume icon, and the /Applications symlink (already carried over
    # from the stage — recreated here only if hdiutil dropped it).
    mkdir -p "$MOUNT_POINT/.background"
    /bin/cp "$BG_FILE" "$MOUNT_POINT/.background/background.png"
    /bin/cp "$ICNS" "$MOUNT_POINT/.VolumeIcon.icns"
    [[ -e "$MOUNT_POINT/Applications" ]] || ln -s /Applications "$MOUNT_POINT/Applications"
    # The 'C' attribute is what makes Finder use .VolumeIcon.icns for the mounted volume.
    assert_not_production "SetFile target" "$MOUNT_POINT"
    SetFile -a C "$MOUNT_POINT" || warn "SetFile -a C failed — the volume will mount with the generic icon"

    APP_BOUNDS_X2=$(( DMG_WIN_X + DMG_WIN_W ))
    # Finder's `bounds` covers the whole frame including the title bar, while the background picture
    # only fills the icon view below it. Add the title bar or the art gets clipped at the bottom.
    APP_BOUNDS_Y2=$(( DMG_WIN_Y + DMG_WIN_H + DMG_TITLEBAR_H ))

    cat > "$TMP_DIR/style.applescript" <<APPLESCRIPT
tell application "Finder"
    tell disk "$APP_NAME"
        -- The volume must be OPEN in Finder, not merely mounted: item positions and icon view options
        -- are properties of a real container window. With no window there is nothing to set, and
        -- nothing gets written to the .DS_Store that ships inside the image.
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {$DMG_WIN_X, $DMG_WIN_Y, $APP_BOUNDS_X2, $APP_BOUNDS_Y2}
        set viewOptions to the icon view options of container window
        -- Anything other than 'not arranged' makes Finder re-snap the icons to its own grid and throw
        -- the explicit positions below away.
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to $DMG_ICON_SIZE
        set text size of viewOptions to 12
        -- A RELATIVE alias, resolved against this disk. An absolute POSIX path bakes this machine's
        -- /Volumes/... into the .DS_Store, and the background then silently fails on every other Mac.
        set background picture of viewOptions to file ".background:background.png"

        -- On a volume Finder has never seen before, its own first layout pass can land *after* ours
        -- and nudge the icons a few points off what we asked for (measured: 178,246 stored as
        -- 169,241). So place, update, read back, and repeat until Finder agrees.
        set converged to false
        repeat with attempt from 1 to 5
            set position of item "$APP_NAME.app" of container window to {$DMG_APP_X, $DMG_APP_Y}
            set position of item "Applications" of container window to {$DMG_LINK_X, $DMG_LINK_Y}
            -- 'without registering applications' keeps Launch Services from indexing the mounted copy
            -- as an installed app.
            update without registering applications
            delay 1
            set p1 to position of item "$APP_NAME.app" of container window
            set p2 to position of item "Applications" of container window
            if (item 1 of p1) = $DMG_APP_X and (item 2 of p1) = $DMG_APP_Y ¬
                and (item 1 of p2) = $DMG_LINK_X and (item 2 of p2) = $DMG_LINK_Y then
                set converged to true
                exit repeat
            end if
        end repeat

        -- Finder writes the .DS_Store lazily; without this pause it is closed before it lands.
        delay 3
        close
        -- Reopen once and report what actually got stored, so the caller can refuse to ship a window
        -- whose icons do not sit where the background art was painted for them.
        delay 1
        open
        delay 2
        set q1 to position of item "$APP_NAME.app" of container window
        set q2 to position of item "Applications" of container window
        close
        delay 1
        return "app=" & (item 1 of q1) & "," & (item 2 of q1) ¬
            & " link=" & (item 1 of q2) & "," & (item 2 of q2) ¬
            & " converged=" & converged
    end tell
end tell
APPLESCRIPT

    log "arranging the window in Finder"
    if ! run_osascript 180 "$TMP_DIR/style.applescript"; then
        automation_help
        die "styling the window failed"
    fi
    log "finder: $OSA_OUT"
    WANT="app=$DMG_APP_X,$DMG_APP_Y link=$DMG_LINK_X,$DMG_LINK_Y converged=true"
    [[ "$OSA_OUT" == "$WANT" ]] \
        || die "Finder did not keep the layout. wanted '$WANT', got '$OSA_OUT'. The arrow in the background art points at fixed slots, so a nudged icon is a visibly wrong window — not shipping it."

    # Give Finder a moment to flush the .DS_Store, then get everything on disk before detaching: the
    # arrangement lives in that file and convert only sees what has actually been written.
    sleep 3
    sync
    [[ -f "$MOUNT_POINT/.DS_Store" ]] \
        || warn "no .DS_Store on the volume — the window arrangement may not have been saved"

    log "detaching before converting (convert cannot see a mounted image consistently)"
    detach_ours || die "could not detach $ATTACHED_DEV — refusing to convert a mounted image"

    log "compressing to UDZO"
    hdiutil convert "$RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG" >/dev/null
fi

assert_not_production "stage cleanup" "$STAGE"
rm -rf "$STAGE"

if [[ -n "$RELEASE_IDENTITY" ]]; then
  codesign --force --sign "$RELEASE_IDENTITY" "$DMG"
  if [[ "$RELEASE_MODE" -eq 1 ]]; then
    # The image is notarized separately from the app inside it.
    notarize_path "$DMG"
    xcrun stapler staple "$DMG" || die "DMG stapling failed"
    xcrun stapler validate "$DMG" || die "DMG staple validation failed"
  elif has_notary_credentials; then
    notarize_path "$DMG"
    xcrun stapler staple "$DMG" || die "DMG stapling failed"
    xcrun stapler validate "$DMG" || die "DMG staple validation failed"
  fi
fi

# ---------------------------------------------------------------- the Sparkle enclosure
#
# The DMG is what a person downloads; the zip is what the *app* downloads. They are different
# artifacts on purpose. A DMG has to be mounted and dragged, which Sparkle cannot do unattended, so
# the release body's structured metadata points at a zip of the same bundle — the same one that was
# signed, notarized and stapled above, so the copy the updater installs is byte-identical to the copy
# a human would install by hand.
#
# `ditto -c -k --keepParent` and nothing else: it is the only zipper on macOS that preserves symlinks
# and extended attributes, and Sparkle.framework is a symlink farm. A `zip -r` archive of this bundle
# unpacks into an app that does not launch.
ZIP="${DMG%.dmg}.zip"
assert_not_production "sparkle enclosure" "$ZIP"
rm -f "$ZIP"
/usr/bin/ditto -c -k --keepParent "$APP_BUNDLE" "$ZIP"
log "sparkle enclosure: $ZIP ($(du -h "$ZIP" | cut -f1))"

# ---------------------------------------------------------------- the verdict

echo
log "built: $DMG ($(du -h "$DMG" | cut -f1))"
echo
log "Sparkle ZIP ready: $(basename "$ZIP")"
log "release-context.sh signs the ZIP and publishes both artifacts to the Context GitHub release"
echo
VERDICT="$(spctl --assess --type execute --verbose=2 "$APP_BUNDLE" 2>&1 || true)"
if grep -q "accepted" <<<"$VERDICT"; then
  log "Gatekeeper: ACCEPTED — this will open on other Macs."
elif [[ "$RELEASE_MODE" -eq 1 ]]; then
  die "Gatekeeper rejected the release bundle; refusing to ship"
else
  warn "Gatekeeper: REJECTED. This will NOT open on anyone else's Mac."
  warn "  $(head -2 <<<"$VERDICT" | tr '\n' ' ')"
  echo
  warn "To make it distributable you need, from an Apple Developer account (\$99/yr):"
  warn "  1. A 'Developer ID Application' certificate in your keychain"
  warn "  2. A notarytool credential profile"
  warn "Then re-run:"
  warn "  CFC_SIGN_IDENTITY='Developer ID Application: NAME (TEAMID)' \\"
  warn "  CFC_NOTARY_PROFILE='context-notary' $0"
fi
