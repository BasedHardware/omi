#!/bin/bash
# Static/guard tests for the Context release path. This intentionally does not build, sign, notarize,
# contact GitHub, or require any release secret.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PKG_DIR/../.." && pwd)"

fail() { printf 'release-path test failed: %s\n' "$*" >&2; exit 1; }

bash -n \
    "$SCRIPT_DIR/build.sh" \
    "$SCRIPT_DIR/package-dmg.sh" \
    "$SCRIPT_DIR/release-micro-app.sh" \
    "$SCRIPT_DIR/release-context.sh" \
    || fail "shell syntax"

DRY_RUN_OUTPUT="$("$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --dry-run)" \
    || fail "secretless dry-run"
printf '%s\n' "$DRY_RUN_OUTPUT" | grep -qF 'product=context-for-claude tag=context-for-claude-v1.1.0 version=1.1.0 build=1001000' \
    || fail "tag/version/build derivation"
printf '%s\n' "$DRY_RUN_OUTPUT" | grep -qF 'no build, signing, notarization, GitHub release' \
    || fail "dry-run side-effect promise"

if CONTEXT_SPARKLE_PUBLIC_KEY="REPLACE_WITH_SUPublicEDKey_FROM_generate_keys" \
    "$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --dry-run >/dev/null 2>&1; then
    fail "placeholder public key was accepted"
fi

# `grep -qF`, not `rg`: ripgrep is not part of a stock macOS or Codemagic image, and a missing binary
# exits 127 here — indistinguishable from a real contract regression, so the whole suite reported
# "tag/version/build derivation" failures on a machine that simply lacked the tool.
grep -qF 'CONTEXT_SPARKLE_PUBLIC_KEY' "$SCRIPT_DIR/build.sh" \
    || fail "build key injection contract"
grep -qF 'CONTEXT_SPARKLE_PRIVATE_KEY' "$SCRIPT_DIR/release-context.sh" \
    || fail "Context private key naming contract"
grep -qF 'build: $BUILD_NUMBER' "$SCRIPT_DIR/release-micro-app.sh" \
    || fail "generic feed build metadata"
grep -qF 'edSignature: $ED_SIGNATURE' "$SCRIPT_DIR/release-micro-app.sh" \
    || fail "generic feed signature metadata"
grep -qF 'context-for-claude-v*' "$REPO_ROOT/codemagic.yaml" \
    || fail "Codemagic Context tag trigger"

printf 'Context release-path tests passed\n'
