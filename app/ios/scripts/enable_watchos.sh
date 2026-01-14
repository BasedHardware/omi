#!/bin/bash
# enable_watchos.sh - Enables watchOS companion app for CI builds
#
# This script modifies the Xcode project to include the watchOS app
# in the build. It should be run before building on Codemagic/CI.
#
# Usage: ./scripts/enable_watchos.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_FILE="$IOS_DIR/Runner.xcodeproj/project.pbxproj"
INFO_PLIST="$IOS_DIR/Runner/Info.plist"

echo "Enabling watchOS companion app..."

# 1. Add omiWatchApp.app to Embed Watch Content build phase
echo "Adding omiWatchApp to Embed Watch Content build phase..."
# Use perl for reliable multi-line replacement
# Find the "Embed Watch Content" section and add the watch app to the files array
perl -i -0pe 's/(422906722E75A21E00F49E67 \/\* Embed Watch Content \*\/ = \{[^}]*files = \(\n)(\t*\);)/$1\t\t\t\t42A7BA3E2E788BD400138969 \/* omiWatchApp.app in Embed Watch Content *\/,\n$2/s' "$PROJECT_FILE"

# 2. Add target dependency to Runner
echo "Adding target dependency to Runner..."
# Find the Runner target dependencies and add the watch app dependency
perl -i -0pe 's/(97C146ED1CF9000F007C117D \/\* Runner \*\/ = \{[^}]*dependencies = \(\n)(\t*\);)/$1\t\t\t\t42A7BA3D2E788BD400138969 \/* PBXTargetDependency *\/,\n$2/s' "$PROJECT_FILE"

# 3. Add WKCompanionAppBundleIdentifier to Info.plist if not already present
echo "Adding WKCompanionAppBundleIdentifier to Info.plist..."
if ! grep -q "WKCompanionAppBundleIdentifier" "$INFO_PLIST"; then
    # Use perl for reliable plist modification
    perl -i -pe 's/<\/dict>\n<\/plist>/<key>WKCompanionAppBundleIdentifier<\/key>\n\t<string>\$(PRODUCT_BUNDLE_IDENTIFIER)<\/string>\n<\/dict>\n<\/plist>/' "$INFO_PLIST"
fi

echo ""
echo "watchOS companion app enabled successfully!"
echo ""
echo "The following changes were made:"
echo "  - Added omiWatchApp to 'Embed Watch Content' build phase"
echo "  - Added target dependency from Runner to omiWatchApp"
echo "  - Added WKCompanionAppBundleIdentifier to Info.plist"
