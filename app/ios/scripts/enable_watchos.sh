#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_FILE="$IOS_DIR/Runner.xcodeproj/project.pbxproj"
INFO_PLIST="$IOS_DIR/Runner/Info.plist"

echo "Enabling watchOS companion app..."

# Step 1: Add omiWatchApp to Embed Watch Content build phase
if grep -q "42A7BA3E2E788BD400138969 /\* omiWatchApp.app in Embed Watch Content \*/," "$PROJECT_FILE"; then
    echo "Embed Watch Content: already configured"
else
    sed -i.bak 's/422906722E75A21E00F49E67 \/\* Embed Watch Content \*\/ = {/EMBED_WATCH_MARKER/' "$PROJECT_FILE"
    perl -i -0pe 's/(EMBED_WATCH_MARKER[^}]*files = \(\n)(\t*\);)/$1\t\t\t\t42A7BA3E2E788BD400138969 \/* omiWatchApp.app in Embed Watch Content *\/,\n$2/s' "$PROJECT_FILE"
    sed -i.bak 's/EMBED_WATCH_MARKER/422906722E75A21E00F49E67 \/\* Embed Watch Content \*\/ = {/' "$PROJECT_FILE"

    if ! grep -q "42A7BA3E2E788BD400138969 /\* omiWatchApp.app in Embed Watch Content \*/," "$PROJECT_FILE"; then
        echo "ERROR: Failed to add omiWatchApp to Embed Watch Content"
        exit 1
    fi
    echo "Embed Watch Content: configured"
fi

# Step 2: Add target dependency to Runner
if grep -A5 "dependencies = (" "$PROJECT_FILE" | grep -q "42A7BA3D2E788BD400138969"; then
    echo "Target dependency: already configured"
else
    perl -i -0pe 's/(97C146ED1CF9000F007C117D \/\* Runner \*\/ = \{[^}]*dependencies = \(\n)(\t*\);)/$1\t\t\t\t42A7BA3D2E788BD400138969 \/* PBXTargetDependency *\/,\n$2/s' "$PROJECT_FILE"

    if ! grep -q "42A7BA3D2E788BD400138969 /\* PBXTargetDependency \*/," "$PROJECT_FILE"; then
        echo "ERROR: Failed to add target dependency"
        exit 1
    fi
    echo "Target dependency: configured"
fi

# Step 3: Add WKCompanionAppBundleIdentifier to Info.plist
if grep -q "WKCompanionAppBundleIdentifier" "$INFO_PLIST"; then
    echo "WKCompanionAppBundleIdentifier: already configured"
else
    perl -i -pe 'BEGIN{undef $/;} s|</dict>\s*</plist>\s*$|<key>WKCompanionAppBundleIdentifier</key>\n\t<string>\$(PRODUCT_BUNDLE_IDENTIFIER)</string>\n</dict>\n</plist>\n|s' "$INFO_PLIST"

    if ! grep -q "WKCompanionAppBundleIdentifier" "$INFO_PLIST"; then
        echo "ERROR: Failed to add WKCompanionAppBundleIdentifier"
        exit 1
    fi
    echo "WKCompanionAppBundleIdentifier: configured"
fi

rm -f "$PROJECT_FILE.bak" "$INFO_PLIST.bak"

echo "watchOS companion app enabled successfully"
