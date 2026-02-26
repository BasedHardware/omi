#!/bin/bash
# =============================================================================
# Post-Release Verification
# Downloads, installs, and tests the released app to catch broken builds early.
# Usage: ./verify-release.sh [version]
# If no version specified, checks the latest live release from the appcast.
# =============================================================================

set -e

DESKTOP_BACKEND_URL="https://desktop-backend-hhibjajaja-uc.a.run.app"
GITHUB_REPO="BasedHardware/omi"
APP_NAME="Omi Beta"
VERIFY_DIR="/tmp/omi-verify-release"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }

# Clean up any previous verification
rm -rf "$VERIFY_DIR"
mkdir -p "$VERIFY_DIR"

echo "=============================================="
echo "  Post-Release Verification"
echo "=============================================="
echo ""

# -----------------------------------------------------------------------------
# Step 1: Check appcast is serving the expected version
# -----------------------------------------------------------------------------
echo "[1/5] Checking appcast..."

APPCAST_XML=$(curl -s "$DESKTOP_BACKEND_URL/appcast.xml")
APPCAST_VERSION=$(echo "$APPCAST_XML" | grep -o 'shortVersionString>[^<]*' | head -1 | sed 's/shortVersionString>//')

if [ -z "$APPCAST_VERSION" ]; then
    fail "Appcast returned no version — is the backend healthy?"
    echo "$APPCAST_XML"
    exit 1
fi

VERSION="${1:-$APPCAST_VERSION}"

if [ "$APPCAST_VERSION" = "$VERSION" ]; then
    pass "Appcast serving v$APPCAST_VERSION"
else
    fail "Appcast serving v$APPCAST_VERSION but expected v$VERSION"
    exit 1
fi

# Extract download URL and signature from appcast
DOWNLOAD_URL=$(echo "$APPCAST_XML" | grep -o 'url="[^"]*"' | head -1 | sed 's/url="//;s/"//')
ED_SIGNATURE=$(echo "$APPCAST_XML" | grep -o 'edSignature="[^"]*"' | head -1 | sed 's/edSignature="//;s/"//')

if [ -n "$DOWNLOAD_URL" ]; then
    pass "Download URL: $DOWNLOAD_URL"
else
    fail "No download URL in appcast"
    exit 1
fi

if [ -n "$ED_SIGNATURE" ]; then
    pass "EdDSA signature present"
else
    fail "No EdDSA signature in appcast"
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 2: Download the Sparkle ZIP (what auto-update users get)
# -----------------------------------------------------------------------------
echo ""
echo "[2/5] Downloading Sparkle ZIP..."

ZIP_PATH="$VERIFY_DIR/Omi.zip"
HTTP_CODE=$(curl -sL -o "$ZIP_PATH" -w "%{http_code}" "$DOWNLOAD_URL")

if [ "$HTTP_CODE" = "200" ] && [ -f "$ZIP_PATH" ]; then
    ZIP_SIZE=$(stat -f%z "$ZIP_PATH" 2>/dev/null || stat -c%s "$ZIP_PATH" 2>/dev/null)
    pass "Downloaded ($((ZIP_SIZE / 1024 / 1024))MB)"
else
    fail "Download failed (HTTP $HTTP_CODE)"
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 3: Extract and verify code signature
# -----------------------------------------------------------------------------
echo ""
echo "[3/5] Verifying code signature..."

cd "$VERIFY_DIR"
ditto -xk Omi.zip . 2>/dev/null

APP_BUNDLE="$VERIFY_DIR/$APP_NAME.app"
if [ ! -d "$APP_BUNDLE" ]; then
    # Try without "Beta"
    APP_BUNDLE=$(find "$VERIFY_DIR" -name "*.app" -maxdepth 1 | head -1)
fi

if [ ! -d "$APP_BUNDLE" ]; then
    fail "No .app bundle found in ZIP"
    ls -la "$VERIFY_DIR"
    exit 1
fi

pass "Extracted: $(basename "$APP_BUNDLE")"

# Check Gatekeeper assessment
if spctl --assess --verbose=2 "$APP_BUNDLE" 2>&1 | grep -q "accepted"; then
    pass "Gatekeeper: accepted"
else
    SPCTL_OUTPUT=$(spctl --assess --verbose=2 "$APP_BUNDLE" 2>&1)
    fail "Gatekeeper: rejected"
    echo "    $SPCTL_OUTPUT"
    echo ""
    fail "RELEASE IS BROKEN — users will see 'app can't be opened'"
    echo ""
    echo "  Run rollback: see .claude/skills/rollback/SKILL.md"
    exit 1
fi

# Deep signature verification
if codesign --verify --deep --strict "$APP_BUNDLE" 2>&1; then
    pass "Deep codesign verification passed"
else
    fail "Deep codesign verification failed"
    exit 1
fi

# Check entitlements don't require provisioning profile
ENTITLEMENTS=$(codesign -d --entitlements - "$APP_BUNDLE" 2>/dev/null)
if echo "$ENTITLEMENTS" | grep -q "com.apple.application-identifier"; then
    fail "Has com.apple.application-identifier — requires provisioning profile!"
    echo "  This will cause 'app can't be opened' error (EPOLICY 163)"
    exit 1
else
    pass "No provisioning-profile-dependent entitlements"
fi

# -----------------------------------------------------------------------------
# Step 4: Test app launch
# -----------------------------------------------------------------------------
echo ""
echo "[4/5] Testing app launch..."

# Copy to a temp location to test launch
TEST_APP="$VERIFY_DIR/test-launch/$APP_NAME.app"
mkdir -p "$VERIFY_DIR/test-launch"
cp -R "$APP_BUNDLE" "$TEST_APP"

# Try to launch and wait up to 10 seconds for it to start
open "$TEST_APP" 2>/tmp/omi-verify-launch-error.txt &

# Wait for the app to appear in process list
LAUNCH_OK=false
for i in $(seq 1 10); do
    sleep 1
    if pgrep -f "$TEST_APP" > /dev/null 2>&1 || pgrep -x "Omi Computer" > /dev/null 2>&1 || pgrep -x "Omi Beta" > /dev/null 2>&1; then
        LAUNCH_OK=true
        break
    fi
done

if $LAUNCH_OK; then
    pass "App launched successfully"
    # Kill only the test instance (by matching its path, not the process name)
    # Avoid pkill -x "Omi Computer" which kills ALL instances including Dev/Production
    TEST_PIDS=$(pgrep -f "$VERIFY_DIR" 2>/dev/null || true)
    if [ -n "$TEST_PIDS" ]; then
        echo "$TEST_PIDS" | xargs kill 2>/dev/null || true
    fi
else
    LAUNCH_ERROR=$(cat /tmp/omi-verify-launch-error.txt 2>/dev/null)
    # Also check Console for launch errors
    CONSOLE_ERROR=$(log show --predicate 'process == "Omi Computer" OR process == "Omi Beta"' --last 30s --style compact 2>/dev/null | tail -5)
    fail "App failed to launch within 10 seconds"
    [ -n "$LAUNCH_ERROR" ] && echo "    Error: $LAUNCH_ERROR"
    [ -n "$CONSOLE_ERROR" ] && echo "    Console: $CONSOLE_ERROR"
    echo ""
    fail "RELEASE IS BROKEN — app won't start"
    echo ""
    echo "  Run rollback: see .claude/skills/rollback/SKILL.md"
    # Clean up — only kill the test instance
    TEST_PIDS=$(pgrep -f "$VERIFY_DIR" 2>/dev/null || true)
    if [ -n "$TEST_PIDS" ]; then
        echo "$TEST_PIDS" | xargs kill 2>/dev/null || true
    fi
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 5: Verify DMG download works too
# -----------------------------------------------------------------------------
echo ""
echo "[5/5] Checking DMG download..."

DMG_HTTP=$(curl -sI -o /dev/null -w "%{http_code}" -L "$DESKTOP_BACKEND_URL/download")
if [ "$DMG_HTTP" = "200" ]; then
    pass "DMG download endpoint working (HTTP $DMG_HTTP)"
else
    warn "DMG download returned HTTP $DMG_HTTP (may need GCS upload)"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=============================================="
echo -e "  ${GREEN}Release v$VERSION verified successfully!${NC}"
echo "=============================================="
echo ""

# Clean up
rm -rf "$VERIFY_DIR"
rm -f /tmp/omi-verify-launch-error.txt
