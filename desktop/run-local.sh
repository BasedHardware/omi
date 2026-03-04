#!/bin/bash
set -e

# Simplified local dev script for Nooto desktop
# Skips cloudflared tunnel and Rust backend — uses remote API directly

# Use Xcode's default toolchain to match the SDK version
unset TOOLCHAINS

# App configuration
BINARY_NAME="Omi Computer"
APP_NAME="Nooto Dev"
BUNDLE_ID="com.togodynamics.nooto.desktop-dev"
BUILD_DIR="build"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
APP_PATH="/Applications/$APP_NAME.app"
SIGN_IDENTITY="${OMI_SIGN_IDENTITY:-}"

echo "=== Nooto Desktop (local dev) ==="

echo "[1] Killing existing instances..."
pkill -f "$APP_NAME.app" 2>/dev/null || true
sleep 0.5

echo "[2] Cleaning conflicting app bundles..."
rm -rf "$BUILD_DIR/Omi Computer.app" 2>/dev/null
for app in "/Applications/Omi Computer.app" "/Applications/Omi.app" "$HOME/Desktop/Omi.app" "$HOME/Desktop/Omi Dev.app" "/Applications/Nooto Dev.app" "/Applications/Nooto.app"; do
    if [ -d "$app" ]; then
        echo "   Removing: $app"
        rm -rf "$app" 2>/dev/null || echo "   (needs sudo to remove $app)"
    fi
done

echo "[3] Building Swift app..."
xcrun swift build -c debug --package-path Desktop

echo "[4] Creating app bundle..."
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"
mkdir -p "$APP_BUNDLE/Contents/Frameworks"

cp -f "Desktop/.build/debug/$BINARY_NAME" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME"
install_name_tool -add_rpath "@executable_path/../Frameworks" "$APP_BUNDLE/Contents/MacOS/$BINARY_NAME" 2>/dev/null || true

# Copy Sparkle framework
SPARKLE_FRAMEWORK="Desktop/.build/arm64-apple-macosx/debug/Sparkle.framework"
if [ -d "$SPARKLE_FRAMEWORK" ]; then
    rm -rf "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
    cp -R "$SPARKLE_FRAMEWORK" "$APP_BUNDLE/Contents/Frameworks/"
fi

# Info.plist
cp -f Desktop/Info.plist "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $BINARY_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName $APP_NAME" "$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleURLTypes:0:CFBundleURLSchemes:0 nooto-desktop-dev" "$APP_BUNDLE/Contents/Info.plist"

# GoogleService-Info.plist
if [ -f "Desktop/Sources/GoogleService-Info-Dev.plist" ]; then
    cp -f Desktop/Sources/GoogleService-Info-Dev.plist "$APP_BUNDLE/Contents/Resources/GoogleService-Info.plist"
else
    cp -f Desktop/Sources/GoogleService-Info.plist "$APP_BUNDLE/Contents/Resources/"
fi

# Resource bundle
RESOURCE_BUNDLE="Desktop/.build/arm64-apple-macosx/debug/Omi Computer_Omi Computer.bundle"
if [ -d "$RESOURCE_BUNDLE" ]; then
    cp -Rf "$RESOURCE_BUNDLE" "$APP_BUNDLE/Contents/Resources/"
fi

# acp-bridge
ACP_BRIDGE_DIR="$(dirname "$0")/acp-bridge"
if [ -d "$ACP_BRIDGE_DIR/dist" ]; then
    mkdir -p "$APP_BUNDLE/Contents/Resources/acp-bridge"
    cp -Rf "$ACP_BRIDGE_DIR/dist" "$APP_BUNDLE/Contents/Resources/acp-bridge/"
    cp -f "$ACP_BRIDGE_DIR/package.json" "$APP_BUNDLE/Contents/Resources/acp-bridge/"
    [ -d "$ACP_BRIDGE_DIR/node_modules" ] && cp -Rf "$ACP_BRIDGE_DIR/node_modules" "$APP_BUNDLE/Contents/Resources/acp-bridge/"
fi

# .env — point to Nooto staging API
if [ -f ".env.app.dev" ]; then
    cp -f .env.app.dev "$APP_BUNDLE/Contents/Resources/.env"
elif [ -f ".env.app" ]; then
    cp -f .env.app "$APP_BUNDLE/Contents/Resources/.env"
else
    echo "OMI_API_URL=https://nooto-dev.togodynamics.com/" > "$APP_BUNDLE/Contents/Resources/.env"
fi

# App icon
cp -f omi_icon.icns "$APP_BUNDLE/Contents/Resources/OmiIcon.icns" 2>/dev/null || true

echo -n "APPL????" > "$APP_BUNDLE/Contents/PkgInfo"

# Skip provisioning profile — it's for Based Hardware team, not ours
# Apple Sign-In will use web-based OAuth instead of native

echo "[5] Signing app..."
xattr -cr "$APP_BUNDLE"

if [ -z "$SIGN_IDENTITY" ]; then
    SIGN_IDENTITY=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | sed 's/.*"\(.*\)"/\1/')
    if [ -z "$SIGN_IDENTITY" ]; then
        SIGN_IDENTITY=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | sed 's/.*"\(.*\)"/\1/')
    fi
fi

if [ -n "$SIGN_IDENTITY" ]; then
    echo "   Using identity: $SIGN_IDENTITY"
    if [ -d "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework" ]; then
        codesign --force --options runtime --sign "$SIGN_IDENTITY" "$APP_BUNDLE/Contents/Frameworks/Sparkle.framework"
    fi
    NODE_BIN="$APP_BUNDLE/Contents/Resources/Omi Computer_Omi Computer.bundle/node"
    if [ -f "$NODE_BIN" ]; then
        codesign --force --options runtime --entitlements Desktop/Node.entitlements --sign "$SIGN_IDENTITY" "$NODE_BIN"
    fi
    codesign --force --options runtime --entitlements Desktop/Omi-local.entitlements --sign "$SIGN_IDENTITY" "$APP_BUNDLE"
else
    echo "   Warning: No signing identity found. Using ad-hoc."
    codesign --force --deep --sign - "$APP_BUNDLE"
fi

xattr -cr "$APP_BUNDLE"

echo "[6] Installing to /Applications/..."
ditto "$APP_BUNDLE" "$APP_PATH"

echo "[7] Registering with LaunchServices..."
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
$LSREGISTER -u "$APP_BUNDLE" 2>/dev/null || true
$LSREGISTER -u "$APP_PATH" 2>/dev/null || true
$LSREGISTER -f "$APP_PATH" 2>/dev/null || true

echo "[8] Launching..."
echo ""
echo "=== Nooto Desktop Dev ==="
echo "App: $APP_PATH"
echo "API: $(grep OMI_API_URL "$APP_BUNDLE/Contents/Resources/.env" 2>/dev/null || echo 'not set')"
echo "========================="
echo ""

open "$APP_PATH"
