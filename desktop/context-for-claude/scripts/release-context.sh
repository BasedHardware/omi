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

# Which variable holds the token that publishes the release. CONTEXT_GITHUB_TOKEN is the intended
# one — a fine-grained token scoped to this repository — but the CI environment already carries the
# shared GH_TOKEN from the appstore_credentials group, so falling back to it means a release is not
# blocked on provisioning a second credential.
#
# The choice is made here, as a *name*, rather than by reading a value and passing it along: the
# helper resolves the variable itself, so the token never becomes an argument in a process list.
# Binding is explicit either way, which is what codemagic.yaml's note about GH_TOKEN shadowing
# GITHUB_TOKEN in the GitHub CLI actually asks for. Prefer the scoped token when both exist.
GITHUB_TOKEN_ENV="CONTEXT_GITHUB_TOKEN"
if [[ -z "${CONTEXT_GITHUB_TOKEN:-}" ]]; then
    for candidate in GH_TOKEN GITHUB_TOKEN; do
        if [[ -n "${!candidate:-}" ]]; then
            GITHUB_TOKEN_ENV="$candidate"
            printf '\033[1;33m[release]\033[0m %s\n' \
                "CONTEXT_GITHUB_TOKEN is unset; publishing with the shared $candidate instead. A token scoped to $RELEASE_REPO is preferred." >&2
            break
        fi
    done
fi

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
    --github-token-env "$GITHUB_TOKEN_ENV" \
    --github-repo "$RELEASE_REPO" \
    --feed-url "${CONTEXT_APPCAST_FEED_URL:-$DEFAULT_FEED_URL}" \
    "$@"
