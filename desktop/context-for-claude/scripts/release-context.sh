#!/bin/bash
# Context for Claude's product configuration for the reusable micro-app release helper.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    --github-repo "${CONTEXT_RELEASE_REPO:-BasedHardware/omi}" \
    "$@"
