#!/bin/bash
# Bundle Helper Script
# Copies the Swift "Omi Computer" app into the Flutter app bundle
# This allows the Flutter app to launch the Rewind feature from the Swift app

set -e

echo "=== Bundle Helper: Starting ==="

# Configuration
SWIFT_APP_NAME="Omi Computer.app"
SWIFT_APP_LOCATIONS=(
    # Built app from build.sh script (omi-desktop is sibling to omi/, not inside it)
    # PROJECT_DIR = omi/app/macos, so ../../../omi-desktop = /Users/matthewdi/omi-desktop
    "$PROJECT_DIR/../../../omi-desktop/build/${SWIFT_APP_NAME}"
    # Built app in omi-desktop (Xcode paths)
    "$PROJECT_DIR/../../../omi-desktop/build/Build/Products/Release/${SWIFT_APP_NAME}"
    "$PROJECT_DIR/../../../omi-desktop/build/Build/Products/Debug/${SWIFT_APP_NAME}"
    # Archived/exported app
    "$PROJECT_DIR/../../../omi-desktop/export/${SWIFT_APP_NAME}"
    # User's Applications folder
    "/Applications/${SWIFT_APP_NAME}"
    # Home Applications folder
    "$HOME/Applications/${SWIFT_APP_NAME}"
)

# Destination inside the Flutter app bundle
DEST_DIR="${BUILT_PRODUCTS_DIR}/${PRODUCT_NAME}.app/Contents/MacOS"
DEST_PATH="${DEST_DIR}/${SWIFT_APP_NAME}"

echo "Looking for Swift app: ${SWIFT_APP_NAME}"
echo "Destination: ${DEST_PATH}"

# Find the Swift app
SWIFT_APP_PATH=""
for location in "${SWIFT_APP_LOCATIONS[@]}"; do
    echo "Checking: ${location}"
    if [ -d "${location}" ]; then
        SWIFT_APP_PATH="${location}"
        echo "Found Swift app at: ${SWIFT_APP_PATH}"
        break
    fi
done

# If not found, try to find it anywhere
if [ -z "${SWIFT_APP_PATH}" ]; then
    echo "Swift app not found in standard locations, searching..."
    FOUND_PATH=$(mdfind "kMDItemCFBundleIdentifier == 'me.omi.computer'" 2>/dev/null | head -1)
    if [ -n "${FOUND_PATH}" ] && [ -d "${FOUND_PATH}" ]; then
        SWIFT_APP_PATH="${FOUND_PATH}"
        echo "Found via Spotlight: ${SWIFT_APP_PATH}"
    fi
fi

# Check if we found it
if [ -z "${SWIFT_APP_PATH}" ]; then
    echo "WARNING: Swift app '${SWIFT_APP_NAME}' not found."
    echo "The Rewind feature will try to launch it from Applications or by name."
    echo "To bundle it, build the Swift app first or place it in one of these locations:"
    for location in "${SWIFT_APP_LOCATIONS[@]}"; do
        echo "  - ${location}"
    done
    exit 0  # Don't fail the build, just warn
fi

# Create destination directory if needed
mkdir -p "${DEST_DIR}"

# Remove old bundled app if exists
if [ -d "${DEST_PATH}" ]; then
    echo "Removing old bundled app..."
    rm -rf "${DEST_PATH}"
fi

# Copy the Swift app
echo "Copying Swift app to bundle..."
cp -R "${SWIFT_APP_PATH}" "${DEST_PATH}"

# Verify
if [ -d "${DEST_PATH}" ]; then
    echo "SUCCESS: Swift app bundled at ${DEST_PATH}"
    # Show bundle size
    SIZE=$(du -sh "${DEST_PATH}" | cut -f1)
    echo "Bundle size: ${SIZE}"
else
    echo "ERROR: Failed to copy Swift app"
    exit 1
fi

echo "=== Bundle Helper: Complete ==="
