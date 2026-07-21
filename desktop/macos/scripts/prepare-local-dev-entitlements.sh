#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "--validate-identity" ]; then
    if [ "$#" -ne 4 ]; then
        echo "Usage: $0 --validate-identity SIGN_IDENTITY true|false 0|1" >&2
        exit 2
    fi

    SIGN_IDENTITY="$2"
    IS_NAMED_BUNDLE="$3"
    ALLOW_ADHOC="$4"
    if [ "$SIGN_IDENTITY" = "-" ] \
        && { [ "$IS_NAMED_BUNDLE" != "true" ] || [ "$ALLOW_ADHOC" != "1" ]; }; then
        echo "Ad-hoc signing requires an explicitly opted-in named bundle" >&2
        exit 2
    fi
    exit 0
fi

if [ "$#" -ne 4 ]; then
    echo "Usage: $0 BASE_ENTITLEMENTS DEV_DIR BUNDLE_ID development|adhoc" >&2
    exit 2
fi

BASE_ENTITLEMENTS="$1"
DEV_DIR="$2"
BUNDLE_ID="$3"
SIGNING_MODE="$4"

case "$SIGNING_MODE" in
    development|adhoc) ;;
    *)
        echo "Unsupported local signing mode: $SIGNING_MODE" >&2
        exit 2
        ;;
esac

case "$BUNDLE_ID" in
    ''|*[!A-Za-z0-9._-]*)
        echo "Bundle ID contains unsupported path characters: $BUNDLE_ID" >&2
        exit 2
        ;;
esac

# The run.sh build lock serializes a checkout. Keeping generated entitlements
# under that checkout's .dev directory and naming them by bundle also isolates
# parallel worktrees and named apps from one another.
OUTPUT_DIR="$DEV_DIR/local-signing"
OUTPUT_ENTITLEMENTS="$OUTPUT_DIR/$BUNDLE_ID.entitlements"
mkdir -p "$OUTPUT_DIR"
TEMP_ENTITLEMENTS="$(mktemp "$OUTPUT_DIR/.$BUNDLE_ID.entitlements.XXXXXX")"
cleanup() {
    rm -f "$TEMP_ENTITLEMENTS"
}
trap cleanup EXIT
cp "$BASE_ENTITLEMENTS" "$TEMP_ENTITLEMENTS"

# Named bundles have no provisioning profile, so Sign in with Apple must not
# be present in their local signature.
/usr/libexec/PlistBuddy \
    -c "Delete :com.apple.developer.applesignin" \
    "$TEMP_ENTITLEMENTS" >/dev/null 2>&1 || true

LIBRARY_VALIDATION_KEY="com.apple.security.cs.disable-library-validation"
if [ "$SIGNING_MODE" = "adhoc" ]; then
    # Hardened runtime rejects ad-hoc third-party frameworks even when the app
    # and nested code are all ad-hoc signed. This exception is limited to the
    # explicitly opted-in named-bundle path; real identities retain validation.
    /usr/libexec/PlistBuddy \
        -c "Add :$LIBRARY_VALIDATION_KEY bool true" \
        "$TEMP_ENTITLEMENTS" >/dev/null 2>&1 || \
        /usr/libexec/PlistBuddy \
            -c "Set :$LIBRARY_VALIDATION_KEY true" \
            "$TEMP_ENTITLEMENTS"
else
    /usr/libexec/PlistBuddy \
        -c "Delete :$LIBRARY_VALIDATION_KEY" \
        "$TEMP_ENTITLEMENTS" >/dev/null 2>&1 || true
fi

plutil -lint "$TEMP_ENTITLEMENTS" >/dev/null
mv -fh "$TEMP_ENTITLEMENTS" "$OUTPUT_ENTITLEMENTS"
printf '%s\n' "$OUTPUT_ENTITLEMENTS"
