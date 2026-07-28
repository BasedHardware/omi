#!/bin/bash
#
# Builds a distributable disk image of Context for Claude.
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
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="Context for Claude"
BUNDLE_ID="com.omi.context-for-claude"
DIST_DIR="$PKG_DIR/dist"
APP_BUNDLE="$PKG_DIR/build/$APP_NAME.app"
STAGE="$DIST_DIR/stage"

log()  { printf '\033[1m[dmg]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[dmg]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[dmg]\033[0m %s\n' "$*" >&2; exit 1; }

# Same guard as build.sh: never let this touch a production Omi bundle.
case "$(printf '%s' "$APP_NAME" | tr '[:upper:]' '[:lower:]')" in
  omi|omi.app|"omi beta"|"omi beta.app"|*"omi computer"*)
    die "refusing to package '$APP_NAME'" ;;
esac

VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$PKG_DIR/Resources/Info.plist" 2>/dev/null || echo 1.0.0)"
DMG="$DIST_DIR/ContextForClaude-$VERSION.dmg"

# ---------------------------------------------------------------- build + sign

RELEASE_IDENTITY="${CFC_SIGN_IDENTITY:-}"
if [[ -n "$RELEASE_IDENTITY" ]]; then
  security find-identity -v -p codesigning 2>/dev/null | grep -q "$RELEASE_IDENTITY" \
    || die "CFC_SIGN_IDENTITY '$RELEASE_IDENTITY' is not in the keychain"
  log "signing for distribution as: $RELEASE_IDENTITY"
  CONTEXT_SIGN_IDENTITY="$RELEASE_IDENTITY" "$SCRIPT_DIR/build.sh" --no-install
else
  warn "no CFC_SIGN_IDENTITY set — building with the local development identity."
  warn "The result will NOT open on anyone else's Mac. See the verdict at the end."
  "$SCRIPT_DIR/build.sh" --no-install
fi
[[ -d "$APP_BUNDLE" ]] || die "no app bundle at $APP_BUNDLE"

# ---------------------------------------------------------------- notarize

NOTARY_PROFILE="${CFC_NOTARY_PROFILE:-}"
if [[ -n "$NOTARY_PROFILE" && -n "$RELEASE_IDENTITY" ]]; then
  log "notarizing — this uploads the app to Apple and usually takes a few minutes"
  ZIP="$DIST_DIR/notarize.zip"
  mkdir -p "$DIST_DIR"
  /usr/bin/ditto -c -k --keepParent "$APP_BUNDLE" "$ZIP"
  xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait \
    || die "notarization failed — run 'xcrun notarytool log' with the submission id for the reason"
  # Stapling puts the ticket inside the bundle so a first launch works offline.
  xcrun stapler staple "$APP_BUNDLE" || die "stapling failed"
  rm -f "$ZIP"
  log "notarized and stapled"
elif [[ -n "$RELEASE_IDENTITY" ]]; then
  warn "signed for distribution but NOT notarized (no CFC_NOTARY_PROFILE)."
  warn "Gatekeeper will still refuse it on a machine that has not seen it before."
fi

# ---------------------------------------------------------------- disk image

log "building $DMG"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
/usr/bin/ditto "$APP_BUNDLE" "$STAGE/$APP_NAME.app"
# The drag-to-install convention. Without the symlink people run the app from the mounted image,
# where it cannot be updated and its permissions are attached to a read-only volume path.
ln -s /Applications "$STAGE/Applications"

hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

if [[ -n "$RELEASE_IDENTITY" ]]; then
  codesign --force --sign "$RELEASE_IDENTITY" "$DMG"
  if [[ -n "$NOTARY_PROFILE" ]]; then
    # The image is notarized separately from the app inside it.
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait \
      && xcrun stapler staple "$DMG"
  fi
fi

# ---------------------------------------------------------------- the verdict

echo
log "built: $DMG ($(du -h "$DMG" | cut -f1))"
echo
VERDICT="$(spctl --assess --type execute --verbose=2 "$APP_BUNDLE" 2>&1 || true)"
if grep -q "accepted" <<<"$VERDICT"; then
  log "Gatekeeper: ACCEPTED — this will open on other Macs."
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
