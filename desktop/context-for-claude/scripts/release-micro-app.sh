#!/bin/bash
#
# Config-driven release orchestrator for a small macOS app with a Sparkle update enclosure.
# The product-specific wrapper supplies names and secret variable names; this file owns the
# common tag validation, version injection, ZIP signing, and GitHub publication sequence.
#
# It deliberately does not know how to sign the app or notarize it. The configured package script
# remains the authority for those operations, so a future micro-app can reuse this flow without
# copying Omi's large desktop release workflow.
#
# Usage (normally through release-context.sh):
#   release-micro-app.sh --tag context-for-claude-v1.1.0 --dry-run
#   release-micro-app.sh --tag context-for-claude-v1.1.0 --publish
#
set -euo pipefail

export PATH="/bin:/usr/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"

TAG="${CM_TAG:-}"
TAG_PREFIX=""
PRODUCT_SLUG=""
APP_NAME=""
ARTIFACT_PREFIX=""
PACKAGE_SCRIPT=""
PUBLIC_KEY_ENV=""
PRIVATE_KEY_ENV=""
VERSION_ENV=""
BUILD_NUMBER_ENV=""
RELEASE_IDENTITY_ENV=""
GITHUB_TOKEN_ENV=""
GITHUB_REPO="BasedHardware/omi"
NOTES_FILE=""
MODE=""
NO_STYLE=1

log()  { printf '\033[1m[release]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[release]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,20p' "${BASH_SOURCE[0]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)                  TAG="${2:?--tag needs a value}"; shift 2 ;;
        --tag-prefix)           TAG_PREFIX="${2:?--tag-prefix needs a value}"; shift 2 ;;
        --product-slug)         PRODUCT_SLUG="${2:?--product-slug needs a value}"; shift 2 ;;
        --app-name)             APP_NAME="${2:?--app-name needs a value}"; shift 2 ;;
        --artifact-prefix)      ARTIFACT_PREFIX="${2:?--artifact-prefix needs a value}"; shift 2 ;;
        --package-script)       PACKAGE_SCRIPT="${2:?--package-script needs a path}"; shift 2 ;;
        --public-key-env)       PUBLIC_KEY_ENV="${2:?--public-key-env needs a name}"; shift 2 ;;
        --private-key-env)      PRIVATE_KEY_ENV="${2:?--private-key-env needs a name}"; shift 2 ;;
        --version-env)          VERSION_ENV="${2:?--version-env needs a name}"; shift 2 ;;
        --build-number-env)     BUILD_NUMBER_ENV="${2:?--build-number-env needs a name}"; shift 2 ;;
        --release-identity-env) RELEASE_IDENTITY_ENV="${2:?--release-identity-env needs a name}"; shift 2 ;;
        --github-token-env)     GITHUB_TOKEN_ENV="${2:?--github-token-env needs a name}"; shift 2 ;;
        --github-repo)          GITHUB_REPO="${2:?--github-repo needs a value}"; shift 2 ;;
        --notes-file)           NOTES_FILE="${2:?--notes-file needs a path}"; shift 2 ;;
        --dry-run)              MODE="dry-run"; shift ;;
        --publish)              MODE="publish"; shift ;;
        --style)                NO_STYLE=0; shift ;;
        -h|--help)              usage; exit 0 ;;
        *)                      die "unknown argument: $1 (see --help)" ;;
    esac
done

[[ -n "$TAG_PREFIX" ]] || die "--tag-prefix is required"
[[ -n "$PRODUCT_SLUG" ]] || die "--product-slug is required"
[[ -n "$APP_NAME" ]] || die "--app-name is required"
[[ -n "$ARTIFACT_PREFIX" ]] || die "--artifact-prefix is required"
[[ -n "$PACKAGE_SCRIPT" && -x "$PACKAGE_SCRIPT" ]] || die "package script is missing or not executable: $PACKAGE_SCRIPT"
[[ -n "$PUBLIC_KEY_ENV" ]] || die "--public-key-env is required"
[[ -n "$PRIVATE_KEY_ENV" ]] || die "--private-key-env is required"
[[ -n "$VERSION_ENV" ]] || die "--version-env is required"
[[ -n "$BUILD_NUMBER_ENV" ]] || die "--build-number-env is required"
[[ -n "$RELEASE_IDENTITY_ENV" ]] || die "--release-identity-env is required"
[[ -n "$GITHUB_TOKEN_ENV" ]] || die "--github-token-env is required"
[[ -n "$TAG" ]] || die "a tag is required (pass --tag or set CM_TAG)"
[[ -n "$MODE" ]] || die "choose exactly one mode: --dry-run or --publish"

case "$TAG" in
    "$TAG_PREFIX"*) VERSION="${TAG#"$TAG_PREFIX"}" ;;
    *) die "tag '$TAG' does not use the required '$TAG_PREFIX<version>' convention" ;;
esac
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || die "tag version '$VERSION' must be a stable semantic version (x.y.z)"

IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION"
BUILD_NUMBER=$((10#$MAJOR * 1000000 + 10#$MINOR * 1000 + 10#$PATCH))
[[ "$BUILD_NUMBER" -gt 0 ]] || die "tag version must produce a positive Sparkle build number"

get_env() {
    local name="$1"
    printf '%s' "${!name:-}"
}

PUBLIC_KEY="$(get_env "$PUBLIC_KEY_ENV")"
PRIVATE_KEY="$(get_env "$PRIVATE_KEY_ENV")"
RELEASE_IDENTITY="$(get_env "$RELEASE_IDENTITY_ENV")"
GITHUB_TOKEN="$(get_env "$GITHUB_TOKEN_ENV")"

is_valid_sparkle_public_key() {
    local key="$1"
    [[ "$key" != "REPLACE_WITH_SUPublicEDKey_FROM_generate_keys" ]] \
        && [[ "$key" =~ ^[A-Za-z0-9+/]{43}=$ ]]
}

PACKAGE_ROOT="$(cd "$(dirname "$PACKAGE_SCRIPT")/.." && pwd)"
DIST_DIR="$PACKAGE_ROOT/dist"
ZIP_PATH="$DIST_DIR/$ARTIFACT_PREFIX-$VERSION.zip"
DMG_PATH="$DIST_DIR/$ARTIFACT_PREFIX-$VERSION.dmg"

if [[ "$MODE" == "dry-run" ]]; then
    [[ -z "$NOTES_FILE" || -f "$NOTES_FILE" ]] || die "notes file does not exist: $NOTES_FILE"
    if [[ -n "$PUBLIC_KEY" ]]; then
        is_valid_sparkle_public_key "$PUBLIC_KEY" \
            || die "$PUBLIC_KEY_ENV is not a valid Context Sparkle public key"
        PUBLIC_KEY_STATUS="valid"
    else
        PUBLIC_KEY_STATUS="not supplied (allowed for dry-run)"
    fi
    if [[ -n "$PRIVATE_KEY" ]]; then
        PRIVATE_KEY_STATUS="supplied (value withheld)"
    else
        PRIVATE_KEY_STATUS="not supplied (allowed for dry-run)"
    fi
    log "dry-run: product=$PRODUCT_SLUG tag=$TAG version=$VERSION build=$BUILD_NUMBER"
    log "dry-run: package=$PACKAGE_SCRIPT"
    log "dry-run: artifacts=$(basename "$DMG_PATH"), $(basename "$ZIP_PATH")"
    log "dry-run: $PUBLIC_KEY_ENV=$PUBLIC_KEY_STATUS; $PRIVATE_KEY_ENV=$PRIVATE_KEY_STATUS"
    log "dry-run: no build, signing, notarization, GitHub release, or source-file changes"
    exit 0
fi

[[ -n "$PUBLIC_KEY" ]] \
    || die "$PUBLIC_KEY_ENV is required for publication; refusing to ship the placeholder Sparkle key"
is_valid_sparkle_public_key "$PUBLIC_KEY" \
    || die "$PUBLIC_KEY_ENV is invalid; refusing to ship the placeholder Sparkle key"
[[ ${#PRIVATE_KEY} -ge 32 ]] \
    || die "$PRIVATE_KEY_ENV is required for publication; ZIP signing cannot be skipped"
[[ -n "$RELEASE_IDENTITY" ]] \
    || die "$RELEASE_IDENTITY_ENV is required for publication"
[[ -n "$GITHUB_TOKEN" ]] \
    || die "$GITHUB_TOKEN_ENV is required for GitHub release publication"

if [[ -n "$NOTES_FILE" ]]; then
    [[ -f "$NOTES_FILE" ]] || die "notes file does not exist: $NOTES_FILE"
    RELEASE_NOTES="$(<"$NOTES_FILE")"
else
    RELEASE_NOTES="$APP_NAME $VERSION."
fi
[[ "$RELEASE_NOTES" != *"KEY_VALUE_START"* ]] \
    || die "release notes must not contain KEY_VALUE_START; the helper owns the signed metadata block"

# A published artifact must be bound to the tag that triggered this run. --verify-tag below also
# protects against gh silently creating a tag at an unintended commit.
TOP_LEVEL="$(git -C "$PACKAGE_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$TOP_LEVEL" ]] || die "package checkout is not a Git worktree"
TAG_SHA="$(git -C "$TOP_LEVEL" rev-parse "refs/tags/$TAG^{commit}" 2>/dev/null || true)"
HEAD_SHA="$(git -C "$TOP_LEVEL" rev-parse HEAD 2>/dev/null || true)"
[[ -n "$TAG_SHA" && "$TAG_SHA" == "$HEAD_SHA" ]] \
    || die "HEAD is not the exact commit named by tag '$TAG'; refusing to publish"

export "$VERSION_ENV=$VERSION"
export "$BUILD_NUMBER_ENV=$BUILD_NUMBER"
export CONTEXT_SPARKLE_PUBLIC_KEY="$PUBLIC_KEY"
export CFC_SIGN_IDENTITY="$RELEASE_IDENTITY"

PACKAGE_ARGS=(--release)
[[ "$NO_STYLE" -eq 1 ]] && PACKAGE_ARGS+=(--no-style)
log "building and packaging $APP_NAME $VERSION"
"$PACKAGE_SCRIPT" "${PACKAGE_ARGS[@]}"

[[ -f "$ZIP_PATH" ]] || die "Sparkle ZIP was not produced at $ZIP_PATH"
[[ -f "$DMG_PATH" ]] || die "DMG was not produced at $DMG_PATH"

SPARKLE_SIGN_UPDATE="$(find "$PACKAGE_ROOT/.build" -type f -path '*/Sparkle/bin/sign_update' -print -quit 2>/dev/null || true)"
[[ -x "$SPARKLE_SIGN_UPDATE" ]] \
    || die "Sparkle sign_update tool not found below $PACKAGE_ROOT/.build"

log "signing $(basename "$ZIP_PATH") with the Context EdDSA key"
SIGN_OUTPUT="$(printf '%s' "$PRIVATE_KEY" | "$SPARKLE_SIGN_UPDATE" "$ZIP_PATH" --ed-key-file - 2>&1)" \
    || die "Sparkle ZIP signing failed"
ED_SIGNATURE="$(printf '%s\n' "$SIGN_OUTPUT" | sed -nE 's/.*sparkle:edSignature="([^"]+)".*/\1/p' | tail -1)"
[[ -n "$ED_SIGNATURE" ]] \
    || die "Sparkle ZIP signing produced no EdDSA signature"

RELEASE_BODY="$RELEASE_NOTES

<!-- KEY_VALUE_START
product: $PRODUCT_SLUG
build: $BUILD_NUMBER
edSignature: $ED_SIGNATURE
artifact: $(basename "$ZIP_PATH")
installer: $(basename "$DMG_PATH")
changelog: $APP_NAME $VERSION
KEY_VALUE_END -->"

command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) is required for publication"
GH_TOKEN="$GITHUB_TOKEN" gh auth status --hostname github.com >/dev/null 2>&1 \
    || die "GitHub CLI authentication failed for $GITHUB_REPO"
if GH_TOKEN="$GITHUB_TOKEN" gh release view "$TAG" --repo "$GITHUB_REPO" >/dev/null 2>&1; then
    die "GitHub release '$TAG' already exists; releases are immutable in this helper"
fi

log "publishing GitHub release $TAG to $GITHUB_REPO"
GH_TOKEN="$GITHUB_TOKEN" gh release create "$TAG" \
    --repo "$GITHUB_REPO" \
    --verify-tag \
    --title "$APP_NAME $VERSION" \
    --notes "$RELEASE_BODY" \
    "$ZIP_PATH" "$DMG_PATH"
log "published $(basename "$ZIP_PATH") and $(basename "$DMG_PATH")"
