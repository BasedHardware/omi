#!/bin/bash
# Context for Claude's product configuration for the reusable micro-app release helper.
#
# CONTEXT_RELEASE_REPO retargets both halves of the release at once — the artifacts and the feed
# they are announced through — so a rehearsal can be published to a fork without editing anything.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_REPO="${CONTEXT_RELEASE_REPO:-BasedHardware/omi}"

# Must stay character-for-character equal to SUFeedURL in Resources/Info.plist.
DEFAULT_FEED_URL="https://github.com/$RELEASE_REPO/releases/download/context-for-claude-appcast/appcast.xml"

exec "$SCRIPT_DIR/release-micro-app.sh" \
    --tag-prefix "${CONTEXT_RELEASE_TAG_PREFIX:-context-for-claude-v}" \
    --product-slug context-for-claude \
    --app-name "Context for Claude" \
    --artifact-prefix ContextForClaude \
    --package-script "$SCRIPT_DIR/package-dmg.sh" \
    --public-key-env CONTEXT_SPARKLE_PUBLIC_KEY \
    --private-key-env CONTEXT_SPARKLE_PRIVATE_KEY \
    --version-env CONTEXT_VERSION \
    --build-number-env CONTEXT_BUILD_NUMBER \
    --release-identity-env CFC_SIGN_IDENTITY \
    --github-token-env CONTEXT_GITHUB_TOKEN \
    --github-repo "$RELEASE_REPO" \
    --feed-url "${CONTEXT_APPCAST_FEED_URL:-$DEFAULT_FEED_URL}" \
    "$@"
