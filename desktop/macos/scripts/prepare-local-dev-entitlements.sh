#!/usr/bin/env bash
set -euo pipefail

# Local development code signing for the macOS desktop app.
#
# Hardened-runtime library validation only lets a process load third-party code
# whose signature carries the *same Team ID*. A signing identity that carries no
# Team ID — ad-hoc ("-"), or a self-signed certificate with no Organizational
# Unit such as the local "Omi Local Dev Signing" identity — can never satisfy
# that for the bundled Sparkle/Sentry/onnxruntime frameworks:
#
#   dyld: Library not loaded: @rpath/Sparkle.framework/Versions/B/Sparkle
#     ... mapping process and mapped file (non-platform) have different Team IDs
#
# The failure hides from every usual check: `codesign --verify` passes (the
# signature really is valid), and `open -a` exits 0 while nothing starts. Only
# running the executable directly prints the reason.
#
# So the library-validation exception keys on whether the identity carries a
# Team ID, never on whether the identity string happens to be "-". Identities
# that do carry one — Apple Development, and the
# "Developer ID Application: Based Hardware INC (9536L8KLMP)" used by the
# release pipeline — stay `team-scoped` and keep full library validation.

LIBRARY_VALIDATION_KEY="com.apple.security.cs.disable-library-validation"
TEAM_SCOPED_MODE="team-scoped"
TEAMLESS_MODE="teamless"

usage() {
    cat >&2 <<'EOF'
Usage:
  prepare-local-dev-entitlements.sh --identity-team-id SIGN_IDENTITY
      Print the Team ID codesign will stamp for SIGN_IDENTITY (empty when none).

  prepare-local-dev-entitlements.sh --validate-identity \
      SIGN_IDENTITY TEAM_ID true|false 0|1
      Reject a local signing configuration that must not be used, otherwise
      print its signing mode (team-scoped|teamless).

  prepare-local-dev-entitlements.sh \
      BASE_ENTITLEMENTS DEV_DIR BUNDLE_ID team-scoped|teamless
      Generate the local entitlements plist and print its path.
EOF
}

# Ask codesign what it actually stamps for this identity. The certificate's
# Organizational Unit is the Team ID, but reading it back off a real signature
# is the only answer that matches what the dynamic loader compares at launch,
# and it works whether the identity is given by name or by SHA-1 hash.
resolve_identity_team_id() {
    local identity="$1"
    if [ -z "$identity" ] || [ "$identity" = "-" ]; then
        return 0
    fi

    local probe team_id
    probe="$(mktemp "${TMPDIR:-/tmp}/omi-signing-team-probe.XXXXXX")"
    if ! cp /usr/bin/true "$probe" 2>/dev/null; then
        rm -f "$probe"
        return 0
    fi
    chmod u+w "$probe"
    if ! codesign --force --sign "$identity" "$probe" >/dev/null 2>&1; then
        rm -f "$probe"
        return 0
    fi
    team_id="$(codesign --display --verbose=2 "$probe" 2>&1 |
        sed -n 's/^TeamIdentifier=//p' | head -1)"
    rm -f "$probe"

    # codesign spells "no Team ID" as the literal string "not set".
    if [ -z "$team_id" ] || [ "$team_id" = "not set" ]; then
        return 0
    fi
    printf '%s\n' "$team_id"
}

if [ "${1:-}" = "--identity-team-id" ]; then
    if [ "$#" -ne 2 ]; then
        usage
        exit 2
    fi
    resolve_identity_team_id "$2"
    exit 0
fi

if [ "${1:-}" = "--validate-identity" ]; then
    if [ "$#" -ne 5 ]; then
        usage
        exit 2
    fi

    SIGN_IDENTITY="$2"
    TEAM_ID="$3"
    IS_NAMED_BUNDLE="$4"
    ALLOW_ADHOC="$5"

    case "$IS_NAMED_BUNDLE" in
        true|false) ;;
        *)
            echo "Named-bundle flag must be true or false: $IS_NAMED_BUNDLE" >&2
            exit 2
            ;;
    esac
    case "$ALLOW_ADHOC" in
        0|1) ;;
        *)
            echo "Ad-hoc opt-in flag must be 0 or 1: $ALLOW_ADHOC" >&2
            exit 2
            ;;
    esac

    if [ -z "$SIGN_IDENTITY" ]; then
        echo "No code signing identity was resolved; nothing can be signed" >&2
        exit 2
    fi

    # Team ID metadata must be honest: it is the only input to the
    # library-validation decision below.
    case "$TEAM_ID" in
        '') ;;
        *[!A-Za-z0-9]*)
            echo "Team ID must be alphanumeric: $TEAM_ID" >&2
            exit 2
            ;;
    esac
    if [ "$SIGN_IDENTITY" = "-" ] && [ -n "$TEAM_ID" ]; then
        echo "Ad-hoc signatures never carry a Team ID, but one was supplied: $TEAM_ID" >&2
        exit 2
    fi

    if [ "$SIGN_IDENTITY" = "-" ] \
        && { [ "$IS_NAMED_BUNDLE" != "true" ] || [ "$ALLOW_ADHOC" != "1" ]; }; then
        echo "Ad-hoc signing requires an explicitly opted-in named bundle" >&2
        echo "Ad-hoc signatures also invalidate this bundle's own Screen Recording" >&2
        echo "grant, so Rewind silently captures nothing. Prefer a stable" >&2
        echo "self-signed identity such as 'Omi Local Dev Signing'." >&2
        exit 2
    fi

    if [ -n "$TEAM_ID" ]; then
        printf '%s\n' "$TEAM_SCOPED_MODE"
    else
        # No Team ID, so hardened-runtime library validation can never match the
        # bundled frameworks. This is the launchable local configuration; the
        # generated entitlements must disable library validation.
        printf '%s\n' "$TEAMLESS_MODE"
    fi
    exit 0
fi

if [ "$#" -ne 4 ]; then
    usage
    exit 2
fi

BASE_ENTITLEMENTS="$1"
DEV_DIR="$2"
BUNDLE_ID="$3"
SIGNING_MODE="$4"

case "$SIGNING_MODE" in
    "$TEAM_SCOPED_MODE"|"$TEAMLESS_MODE") ;;
    *)
        echo "Unsupported local signing mode: $SIGNING_MODE" >&2
        echo "Expected $TEAM_SCOPED_MODE or $TEAMLESS_MODE (from --validate-identity)" >&2
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

if [ "$SIGNING_MODE" = "$TEAMLESS_MODE" ]; then
    # A signature with no Team ID can never pass library validation against the
    # bundled frameworks, which carry no Team ID either. This exception is
    # limited to local signatures; a Team-ID identity (Apple Development, or the
    # release pipeline's Developer ID) retains validation.
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
