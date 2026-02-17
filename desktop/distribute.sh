#!/bin/bash
set -e

# Distribution configuration
APP_NAME="Omi Beta"
BUNDLE_ID="com.omi.computer-macos"
BUILD_DIR="build"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
ZIP_PATH="$BUILD_DIR/$APP_NAME.zip"

# Signing identity
SIGN_IDENTITY="Developer ID Application: Matthew Diakonov (S6DP5HF77G)"
TEAM_ID="S6DP5HF77G"
APPLE_ID="matthew.heartful@gmail.com"

echo "=== Building for Distribution ==="

# Build the app
./build.sh

echo ""
echo "=== Signing with Developer ID ==="

# Sign with Developer ID and hardened runtime
codesign --force --options runtime \
    --sign "$SIGN_IDENTITY" \
    --entitlements Desktop/Omi.entitlements \
    "$APP_BUNDLE"

# Verify signature
codesign --verify --verbose=2 "$APP_BUNDLE"
echo "Signature verified."

echo ""
echo "=== Creating ZIP for notarization ==="
rm -f "$ZIP_PATH"
ditto -c -k --keepParent "$APP_BUNDLE" "$ZIP_PATH"
echo "Created: $ZIP_PATH"

echo ""
echo "=== Submitting for notarization ==="
echo "Note: New developer accounts may take hours for first submissions."
echo ""

# Submit for notarization (don't wait - it takes too long)
xcrun notarytool submit "$ZIP_PATH" \
    --apple-id "$APPLE_ID" \
    --team-id "$TEAM_ID" \
    --keychain-profile "omi-notarize" 2>/dev/null || \
xcrun notarytool submit "$ZIP_PATH" \
    --apple-id "$APPLE_ID" \
    --team-id "$TEAM_ID" \
    --password "${NOTARIZE_PASSWORD:-REDACTED}"

echo ""
echo "=== Submission complete ==="
echo ""
echo "To check status:"
echo "  xcrun notarytool history --apple-id \"$APPLE_ID\" --team-id \"$TEAM_ID\""
echo ""
echo "Once status is 'Accepted', staple the ticket:"
echo "  xcrun stapler staple $APP_BUNDLE"
echo ""
echo "Then redistribute the app (not the zip - rebuild zip after stapling):"
echo "  ditto -c -k --keepParent $APP_BUNDLE $ZIP_PATH"
