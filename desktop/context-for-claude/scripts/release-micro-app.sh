#!/bin/bash
#
# Config-driven release orchestrator for a small macOS app that updates itself through Sparkle,
# with GitHub as the whole update backend. Nothing else serves the feed: no platform endpoint reads
# this release, and no service has to be deployed for an update to reach users.
#
# The product-specific wrapper supplies names and secret variable names; this file owns tag
# validation, version injection, ZIP signing, appcast generation, and GitHub publication.
#
# Where the feed lives, and why it is not a file in the repository: the enclosure's EdDSA signature
# only exists once the ZIP has been packaged, so the feed can only be written after the build. A
# tracked appcast would therefore mean a commit pushed on every release — which this repository
# forbids on `main` — so the feed is an asset on one fixed, mutable GitHub release instead. The
# versioned release holds the artifacts; the holder release holds only the feed, is marked as a
# prerelease so it never claims the repository-wide "Latest" pointer, and is re-uploaded in place.
#
# It deliberately does not know how to sign the app or notarize it. The configured package script
# remains the authority for those operations, so a future micro-app can reuse this flow without
# copying Omi's large desktop release workflow.
#
# Usage (normally through the product wrapper, e.g. release-context.sh):
#   release-micro-app.sh --tag <prefix><version> --dry-run     # validate config, touch nothing
#   release-micro-app.sh --tag <prefix><version> --rehearsal    # build + sign + feed, locally
#   release-micro-app.sh --tag <prefix><version> --publish      # the real, distributable release
#   release-micro-app.sh --tag <prefix><version> --rehearsal --publish  # rehearse against a fork
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
FEED_URL=""
NOTES_FILE=""
EXISTING_APPCAST=""
MODE=""
REHEARSAL=0
NO_STYLE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPCAST_GENERATOR="$SCRIPT_DIR/generate-appcast.py"

log()  { printf '\033[1m[release]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[release]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[release]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,26p' "${BASH_SOURCE[0]}"
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
        --feed-url)             FEED_URL="${2:?--feed-url needs a value}"; shift 2 ;;
        --notes-file)           NOTES_FILE="${2:?--notes-file needs a path}"; shift 2 ;;
        --existing-appcast)     EXISTING_APPCAST="${2:?--existing-appcast needs a path}"; shift 2 ;;
        --dry-run)              MODE="dry-run"; shift ;;
        --publish)              MODE="publish"; shift ;;
        --rehearsal)            REHEARSAL=1; shift ;;
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
[[ -n "$FEED_URL" ]] || die "--feed-url is required (the URL the app's SUFeedURL points at)"
[[ -n "$TAG" ]] || die "a tag is required (pass --tag or set CM_TAG)"
[[ -x "$APPCAST_GENERATOR" ]] || die "appcast generator is missing or not executable: $APPCAST_GENERATOR"
if [[ -z "$MODE" ]]; then
    [[ "$REHEARSAL" -eq 1 ]] || die "choose a mode: --dry-run, --rehearsal, or --publish"
    MODE="rehearsal"
fi

case "$TAG" in
    "$TAG_PREFIX"*) VERSION="${TAG#"$TAG_PREFIX"}" ;;
    *) die "tag '$TAG' does not use the required '$TAG_PREFIX<version>' convention" ;;
esac
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || die "tag version '$VERSION' must be a stable semantic version (x.y.z)"

IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION"
BUILD_NUMBER=$((10#$MAJOR * 1000000 + 10#$MINOR * 1000 + 10#$PATCH))
[[ "$BUILD_NUMBER" -gt 0 ]] || die "tag version must produce a positive Sparkle build number"

# The holder tag and the asset name are read out of the feed URL rather than configured twice: the
# app's SUFeedURL is the only thing that decides where a client looks, so anything else here would
# be a second copy of that fact, free to drift out of agreement with the shipped bundle.
#
# Requiring an explicit `/releases/download/<tag>/` also rules out `releases/latest/download`, which
# resolves to the newest release of the whole repository — Omi Desktop ships tags almost daily, so
# that spelling would hand out another product's assets or 404.
if [[ "$FEED_URL" =~ ^https://github\.com/([^/]+/[^/]+)/releases/download/([^/]+)/([^/]+\.xml)$ ]]; then
    FEED_REPO="${BASH_REMATCH[1]}"
    APPCAST_TAG="${BASH_REMATCH[2]}"
    APPCAST_ASSET="${BASH_REMATCH[3]}"
else
    die "--feed-url must be https://github.com/<owner>/<repo>/releases/download/<tag>/<name>.xml, got '$FEED_URL'"
fi
[[ "$FEED_REPO" == "$GITHUB_REPO" ]] \
    || die "--feed-url serves $FEED_REPO but artifacts publish to $GITHUB_REPO; the feed would name enclosures it does not host"
# The feed is uploaded with --clobber, which replaces an asset in place. Confining the holder tag to
# this product's namespace is what keeps that from ever overwriting an asset on another product's
# release, and confining it out of the versioned namespace keeps it from overwriting an installer.
[[ "$APPCAST_TAG" == "$PRODUCT_SLUG"* ]] \
    || die "appcast holder tag '$APPCAST_TAG' is outside the '$PRODUCT_SLUG' namespace; refusing to clobber another product's release asset"
[[ "$APPCAST_TAG" != "$TAG_PREFIX"* ]] \
    || die "appcast holder tag '$APPCAST_TAG' looks like a versioned release tag; the feed must not share a release with artifacts"

# A permanent download link, for humans rather than for Sparkle: a second fixed, mutable release
# carrying the installer under a *version-less* asset name, replaced in place on every release.
#
# GitHub's own `releases/latest/download/<asset>` cannot do this job here. It resolves to the newest
# release of the entire repository, and this repository publishes Omi Desktop tags several times a
# day, so such a URL would answer 404 almost always and would name the wrong product the rest of the
# time. `desktop/windows/docs/release-pipeline.md` rejected that same endpoint for the same reason.
LATEST_TAG="${LATEST_TAG:-$PRODUCT_SLUG-latest}"
LATEST_ASSET="$ARTIFACT_PREFIX.dmg"
LATEST_URL="https://github.com/$GITHUB_REPO/releases/download/$LATEST_TAG/$LATEST_ASSET"
[[ "$LATEST_TAG" == "$PRODUCT_SLUG"* ]] \
    || die "latest-installer holder tag '$LATEST_TAG' is outside the '$PRODUCT_SLUG' namespace; refusing to clobber another product's release asset"
[[ "$LATEST_TAG" != "$TAG_PREFIX"* ]] \
    || die "latest-installer holder tag '$LATEST_TAG' looks like a versioned release tag; the pointer must not share a release with artifacts"
[[ "$LATEST_TAG" != "$APPCAST_TAG" ]] \
    || die "the latest-installer holder must not be the feed holder; one clobbers the other's asset"

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
INFO_PLIST="$PACKAGE_ROOT/Resources/Info.plist"
BUILT_APP="$PACKAGE_ROOT/build/$APP_NAME.app"

# A rehearsal's artifacts carry `-rehearsal` in their own file names. That is the difference that
# cannot be lost: a rehearsal ZIP is not notarized and must never be served as an update, and a
# name is the one property that survives being copied out of dist/, attached to an issue, or found
# on disk a week later with no memory of how it was built.
if [[ "$REHEARSAL" -eq 1 ]]; then
    ARTIFACT_STEM="$ARTIFACT_PREFIX-$VERSION-rehearsal"
    APPCAST_DIR="$DIST_DIR/rehearsal"
    RELEASE_KIND="rehearsal"
else
    ARTIFACT_STEM="$ARTIFACT_PREFIX-$VERSION"
    APPCAST_DIR="$DIST_DIR"
    RELEASE_KIND="release"
fi
ZIP_PATH="$DIST_DIR/$ARTIFACT_STEM.zip"
DMG_PATH="$DIST_DIR/$ARTIFACT_STEM.dmg"
APPCAST_PATH="$APPCAST_DIR/$APPCAST_ASSET"
CURRENT_APPCAST_PATH="$APPCAST_DIR/current-$APPCAST_ASSET"
ENCLOSURE_URL="https://github.com/$GITHUB_REPO/releases/download/$TAG/$(basename "$ZIP_PATH")"

if [[ "$MODE" == "dry-run" ]]; then
    [[ -z "$NOTES_FILE" || -f "$NOTES_FILE" ]] || die "notes file does not exist: $NOTES_FILE"
    if [[ -n "$PUBLIC_KEY" ]]; then
        is_valid_sparkle_public_key "$PUBLIC_KEY" \
            || die "$PUBLIC_KEY_ENV is not a valid $APP_NAME Sparkle public key"
        PUBLIC_KEY_STATUS="valid"
    else
        PUBLIC_KEY_STATUS="not supplied (allowed for dry-run)"
    fi
    if [[ -n "$PRIVATE_KEY" ]]; then
        PRIVATE_KEY_STATUS="supplied (value withheld)"
    else
        PRIVATE_KEY_STATUS="not supplied (sign_update would read the login keychain)"
    fi
    log "dry-run: product=$PRODUCT_SLUG tag=$TAG version=$VERSION build=$BUILD_NUMBER"
    log "dry-run: package=$PACKAGE_SCRIPT"
    log "dry-run: artifacts=$(basename "$DMG_PATH"), $(basename "$ZIP_PATH")"
    log "dry-run: feed=$FEED_URL"
    log "dry-run: feed asset $APPCAST_ASSET on holder release $APPCAST_TAG in $GITHUB_REPO"
    log "dry-run: enclosure=$ENCLOSURE_URL"
    log "dry-run: permanent download link=$LATEST_URL"
    log "dry-run: $PUBLIC_KEY_ENV=$PUBLIC_KEY_STATUS; $PRIVATE_KEY_ENV=$PRIVATE_KEY_STATUS"
    log "dry-run: no build, signing, notarization, GitHub release, appcast, or source-file changes"
    exit 0
fi

# ---------------------------------------------------------------- what each mode is allowed to be
#
# A rehearsal exists because this machine has no Developer ID certificate and no notarization
# credentials, and the release path still has to be exercisable end to end. What it may not do is
# pass itself off as a release: it cannot publish to the production repository, and it cannot write
# the production feed.
if [[ "$REHEARSAL" -eq 1 ]]; then
    warn "REHEARSAL: the app will be signed with whatever identity is available and is NOT notarized."
    warn "REHEARSAL: its ZIP is a real, correctly signed Sparkle enclosure that Gatekeeper will still refuse."
    if [[ "$MODE" == "publish" ]]; then
        [[ "$GITHUB_REPO" != "BasedHardware/omi" ]] \
            || die "a rehearsal must not publish to BasedHardware/omi; point --github-repo at a fork"
    fi
else
    [[ -n "$RELEASE_IDENTITY" ]] \
        || die "$RELEASE_IDENTITY_ENV is required for a distributable release; pass --rehearsal for a non-distributable one"
fi

if [[ "$MODE" == "publish" ]]; then
    [[ -n "$PUBLIC_KEY" ]] \
        || die "$PUBLIC_KEY_ENV is required for publication; refusing to ship the placeholder Sparkle key"
    is_valid_sparkle_public_key "$PUBLIC_KEY" \
        || die "$PUBLIC_KEY_ENV is invalid; refusing to ship the placeholder Sparkle key"
    [[ -n "$GITHUB_TOKEN" ]] \
        || die "$GITHUB_TOKEN_ENV is required for GitHub release publication"

    # Everything publication needs, checked before the build rather than after it. The build, three
    # notarization round-trips and the DMG take roughly forty minutes; discovering a missing CLI, a bad
    # token or an already-published tag at the end of that wastes the run and leaves a signed artifact
    # with nowhere to go. The same checks repeat immediately before `gh release create`, where they guard
    # against a change during the build instead.
    command -v gh >/dev/null 2>&1 \
        || die "GitHub CLI (gh) is required for publication but is not on PATH"
    GH_TOKEN="$GITHUB_TOKEN" gh auth status --hostname github.com >/dev/null 2>&1 \
        || die "$GITHUB_TOKEN_ENV did not authenticate against github.com"
    if GH_TOKEN="$GITHUB_TOKEN" gh release view "$TAG" --repo "$GITHUB_REPO" >/dev/null 2>&1; then
        die "GitHub release '$TAG' already exists; releases are immutable in this helper"
    fi

    # A published artifact must be bound to the tag that triggered this run. --verify-tag below also
    # protects against gh silently creating a tag at an unintended commit.
    TOP_LEVEL="$(git -C "$PACKAGE_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
    [[ -n "$TOP_LEVEL" ]] || die "package checkout is not a Git worktree"
    TAG_SHA="$(git -C "$TOP_LEVEL" rev-parse "refs/tags/$TAG^{commit}" 2>/dev/null || true)"
    if [[ -z "$TAG_SHA" ]]; then
        # A CI checkout is routinely built from the tagged *commit* without the tag ref itself present,
        # so an absent ref does not mean an absent tag. Fetch just this one tag before concluding it is
        # missing; .github/scripts/desktop_release_doctor.py force-fetches the same way, for the same
        # reason. Failure is left to the comparison below, which reports it with the real cause.
        git -C "$TOP_LEVEL" fetch --no-tags origin "+refs/tags/$TAG:refs/tags/$TAG" >/dev/null 2>&1 || true
        TAG_SHA="$(git -C "$TOP_LEVEL" rev-parse "refs/tags/$TAG^{commit}" 2>/dev/null || true)"
    fi
    HEAD_SHA="$(git -C "$TOP_LEVEL" rev-parse HEAD 2>/dev/null || true)"
    [[ -n "$TAG_SHA" && "$TAG_SHA" == "$HEAD_SHA" ]] \
        || die "HEAD is not the exact commit named by tag '$TAG'; refusing to publish"
fi

if [[ -n "$NOTES_FILE" ]]; then
    [[ -f "$NOTES_FILE" ]] || die "notes file does not exist: $NOTES_FILE"
    RELEASE_NOTES="$(<"$NOTES_FILE")"
else
    RELEASE_NOTES="$APP_NAME $VERSION."
fi

# ---------------------------------------------------------------- build and package

export "$VERSION_ENV=$VERSION"
export "$BUILD_NUMBER_ENV=$BUILD_NUMBER"
[[ -z "$PUBLIC_KEY" ]] || export "$PUBLIC_KEY_ENV=$PUBLIC_KEY"
[[ -z "$RELEASE_IDENTITY" ]] || export "$RELEASE_IDENTITY_ENV=$RELEASE_IDENTITY"

PACKAGE_ARGS=()
[[ "$REHEARSAL" -eq 1 ]] || PACKAGE_ARGS+=(--release)
[[ "$NO_STYLE" -eq 1 ]] && PACKAGE_ARGS+=(--no-style)
PACKAGE_ARGS+=(--out "$DMG_PATH")
log "building and packaging $APP_NAME $VERSION ($RELEASE_KIND)"
"$PACKAGE_SCRIPT" "${PACKAGE_ARGS[@]}"

[[ -f "$ZIP_PATH" ]] || die "Sparkle ZIP was not produced at $ZIP_PATH"
[[ -f "$DMG_PATH" ]] || die "DMG was not produced at $DMG_PATH"

# The feed this run writes and the feed the built app reads have to be the same one. A bundle
# shipped with a different SUFeedURL never sees these items at all, and that failure is invisible
# until an update silently never arrives.
BUNDLE_FEED_URL="$(/usr/libexec/PlistBuddy -c 'Print :SUFeedURL' "$BUILT_APP/Contents/Info.plist" 2>/dev/null || true)"
if [[ "$BUNDLE_FEED_URL" != "$FEED_URL" ]]; then
    if [[ "$MODE" == "publish" && "$REHEARSAL" -eq 0 ]]; then
        die "the built app reads '$BUNDLE_FEED_URL' but this release writes '$FEED_URL'; the update would never be seen"
    fi
    warn "the built app reads '$BUNDLE_FEED_URL', not the '$FEED_URL' this run writes — a real release would refuse"
fi

# ---------------------------------------------------------------- sign the enclosure

SPARKLE_SIGN_UPDATE="$(find "$PACKAGE_ROOT/.build" -type f -path '*/Sparkle/bin/sign_update' -print -quit 2>/dev/null || true)"
[[ -x "$SPARKLE_SIGN_UPDATE" ]] \
    || die "Sparkle sign_update tool not found below $PACKAGE_ROOT/.build"

# No key argument means Sparkle reads the private key from the login keychain, which is where the
# releasing maintainer's copy lives and the only place it should be. $PRIVATE_KEY_ENV stays
# supported for a CI runner that has no keychain, and is the only path that moves the key at all.
sparkle_sign_update() {   # sparkle_sign_update <args...>
    if [[ -n "$PRIVATE_KEY" ]]; then
        printf '%s' "$PRIVATE_KEY" | "$SPARKLE_SIGN_UPDATE" "$@" --ed-key-file -
    else
        "$SPARKLE_SIGN_UPDATE" "$@"
    fi
}

log "signing $(basename "$ZIP_PATH") with the $APP_NAME EdDSA key"
SIGN_OUTPUT="$(sparkle_sign_update -p "$ZIP_PATH" 2>&1)" \
    || die "Sparkle ZIP signing failed ($SIGN_OUTPUT); supply $PRIVATE_KEY_ENV or put the private key in the login keychain"
ED_SIGNATURE="$(printf '%s\n' "$SIGN_OUTPUT" | tail -1 | tr -d '[:space:]')"
[[ -n "$ED_SIGNATURE" ]] \
    || die "Sparkle ZIP signing produced no EdDSA signature; supply $PRIVATE_KEY_ENV or put the private key in the login keychain"
# Signing the file and publishing a feed that verifies against it are two different claims. This
# checks the second one, against the exact bytes that are about to be uploaded.
sparkle_sign_update --verify "$ZIP_PATH" "$ED_SIGNATURE" >/dev/null \
    || die "the signature does not verify against $(basename "$ZIP_PATH")"
log "signature verified against $(basename "$ZIP_PATH")"

# ---------------------------------------------------------------- the feed
#
# The previous feed is not on disk anywhere, so it is fetched from the holder release before the
# new item is appended. Losing it would strand every client whose build is older than this one.
mkdir -p "$APPCAST_DIR"
HOLDER_EXISTS=0
EXISTING_ARGS=()
if [[ -n "$EXISTING_APPCAST" ]]; then
    [[ -f "$EXISTING_APPCAST" ]] || die "--existing-appcast does not exist: $EXISTING_APPCAST"
    EXISTING_ARGS=(--existing "$EXISTING_APPCAST")
fi
if [[ "$MODE" == "publish" ]]; then
    if GH_TOKEN="$GITHUB_TOKEN" gh release view "$APPCAST_TAG" --repo "$GITHUB_REPO" >/dev/null 2>&1; then
        HOLDER_EXISTS=1
        # Asked for by name rather than inferred from a failed download: "the asset is not there
        # yet" and "the network is down" are the same exit code, and treating the second as the
        # first would publish a feed with today's release as its only item.
        HOLDER_ASSETS="$(GH_TOKEN="$GITHUB_TOKEN" gh release view "$APPCAST_TAG" --repo "$GITHUB_REPO" --json assets --jq '.assets[].name')" \
            || die "could not list the assets on holder release '$APPCAST_TAG'"
        if [[ "${#EXISTING_ARGS[@]}" -gt 0 ]]; then
            log "using the feed passed with --existing-appcast instead of the published one"
        elif grep -qxF "$APPCAST_ASSET" <<<"$HOLDER_ASSETS"; then
            rm -f "$CURRENT_APPCAST_PATH"
            GH_TOKEN="$GITHUB_TOKEN" gh release download "$APPCAST_TAG" \
                --repo "$GITHUB_REPO" --pattern "$APPCAST_ASSET" --output "$CURRENT_APPCAST_PATH" \
                || die "could not download the published $APPCAST_ASSET; refusing to publish a feed that would drop its history"
            log "fetched the published feed ($(wc -c <"$CURRENT_APPCAST_PATH" | tr -d ' ') bytes)"
            EXISTING_ARGS=(--existing "$CURRENT_APPCAST_PATH")
        else
            log "holder release '$APPCAST_TAG' has no $APPCAST_ASSET yet; starting a new feed"
        fi
    else
        log "holder release '$APPCAST_TAG' does not exist yet; this is the first release of $PRODUCT_SLUG"
    fi
fi

GENERATOR_ARGS=(
    --output "$APPCAST_PATH"
    --title "$APP_NAME"
    --feed-url "$FEED_URL"
    --version "$VERSION"
    --build "$BUILD_NUMBER"
    --zip "$ZIP_PATH"
    --signature "$ED_SIGNATURE"
    --enclosure-url "$ENCLOSURE_URL"
    --info-plist "$INFO_PLIST"
    --notes "$RELEASE_NOTES"
)
[[ "${#EXISTING_ARGS[@]}" -eq 0 ]] || GENERATOR_ARGS+=("${EXISTING_ARGS[@]}")
[[ "$REHEARSAL" -eq 0 ]] || GENERATOR_ARGS+=(--rehearsal)
"$APPCAST_GENERATOR" "${GENERATOR_ARGS[@]}" || die "appcast generation failed"

if [[ "$MODE" != "publish" ]]; then
    log "$RELEASE_KIND complete, nothing published:"
    log "  $DMG_PATH"
    log "  $ZIP_PATH"
    log "  $APPCAST_PATH"
    exit 0
fi

# ---------------------------------------------------------------- publish

command -v gh >/dev/null 2>&1 || die "GitHub CLI (gh) is required for publication"
GH_TOKEN="$GITHUB_TOKEN" gh auth status --hostname github.com >/dev/null 2>&1 \
    || die "GitHub CLI authentication failed for $GITHUB_REPO"
if GH_TOKEN="$GITHUB_TOKEN" gh release view "$TAG" --repo "$GITHUB_REPO" >/dev/null 2>&1; then
    die "GitHub release '$TAG' already exists; releases are immutable in this helper"
fi

RELEASE_TITLE="$APP_NAME $VERSION"
RELEASE_ARGS=(--repo "$GITHUB_REPO" --verify-tag --title "$RELEASE_TITLE" --notes "$RELEASE_NOTES")
if [[ "$REHEARSAL" -eq 1 ]]; then
    RELEASE_TITLE="$APP_NAME $VERSION (REHEARSAL — not distributable)"
    RELEASE_ARGS=(--repo "$GITHUB_REPO" --verify-tag --prerelease --title "$RELEASE_TITLE"
        --notes "$RELEASE_NOTES

REHEARSAL. These artifacts are not notarized and will not open on another Mac. Do not announce or
install them.")
fi

# The artifacts go up before the feed does: an item is only publishable once the enclosure it names
# can actually be downloaded.
log "publishing GitHub release $TAG to $GITHUB_REPO"
GH_TOKEN="$GITHUB_TOKEN" gh release create "$TAG" "${RELEASE_ARGS[@]}" "$ZIP_PATH" "$DMG_PATH"
log "published $(basename "$ZIP_PATH") and $(basename "$DMG_PATH")"

if [[ "$HOLDER_EXISTS" -eq 0 ]]; then
    # --prerelease matters: without it this holder claims the repository-wide "Latest release"
    # pointer, and the repository front page starts offering an XML file as its newest download.
    log "creating the feed holder release $APPCAST_TAG"
    GH_TOKEN="$GITHUB_TOKEN" gh release create "$APPCAST_TAG" \
        --repo "$GITHUB_REPO" \
        --prerelease \
        --title "$APP_NAME update feed" \
        --notes "Holds the Sparkle appcast for $APP_NAME at a stable URL. Not an installable release: the
installers live on the $TAG_PREFIX<version> releases this feed points at. Marked as a prerelease so it
never becomes the repository's latest release. Updated in place by scripts/release-micro-app.sh." \
        "$APPCAST_PATH"
else
    log "updating $APPCAST_ASSET on the feed holder release $APPCAST_TAG"
    GH_TOKEN="$GITHUB_TOKEN" gh release upload "$APPCAST_TAG" "$APPCAST_PATH" \
        --repo "$GITHUB_REPO" --clobber
fi
log "feed live at $FEED_URL"

# The permanent download link moves last, and only for a real release. A rehearsal that advanced it
# would hand everyone who follows that link a build Gatekeeper refuses to open.
if [[ "$REHEARSAL" -eq 1 ]]; then
    warn "REHEARSAL: leaving $LATEST_ASSET on '$LATEST_TAG' where it was"
else
    # Uploaded from a copy under the version-less name, because the asset name is what the permanent
    # URL is made of; the versioned DMG keeps its own name on the versioned release.
    LATEST_STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/micro-app-latest.XXXXXX")"
    cp "$DMG_PATH" "$LATEST_STAGE_DIR/$LATEST_ASSET"
    if GH_TOKEN="$GITHUB_TOKEN" gh release view "$LATEST_TAG" --repo "$GITHUB_REPO" >/dev/null 2>&1; then
        log "pointing $LATEST_ASSET on '$LATEST_TAG' at $VERSION"
        GH_TOKEN="$GITHUB_TOKEN" gh release upload "$LATEST_TAG" "$LATEST_STAGE_DIR/$LATEST_ASSET" \
            --repo "$GITHUB_REPO" --clobber \
            || die "could not update the permanent installer link on '$LATEST_TAG'"
    else
        log "creating the permanent installer release $LATEST_TAG"
        GH_TOKEN="$GITHUB_TOKEN" gh release create "$LATEST_TAG" \
            --repo "$GITHUB_REPO" \
            --prerelease \
            --title "$APP_NAME — latest download" \
            --notes "Always holds the newest $APP_NAME installer at a stable URL:

$LATEST_URL

The file is replaced in place on every release, so the link never changes. Release notes and
per-version artifacts live on the $TAG_PREFIX<version> releases. Marked as a prerelease so it never
becomes the repository's latest release. Updated by scripts/release-micro-app.sh." \
            "$LATEST_STAGE_DIR/$LATEST_ASSET" \
            || die "could not create the permanent installer release '$LATEST_TAG'"
    fi
    rm -rf "$LATEST_STAGE_DIR"
    log "permanent download link: $LATEST_URL"
fi
