#!/bin/bash
#
# Behavioural coverage for scripts/build-identity.sh — the rule that a build which is not signed
# for release must not claim the production platform identity.
#
# This drives the real resolver as a subprocess and asserts on what it actually produces. It is
# not a source scrape: reverting the rule inside build-identity.sh turns these red.
#
# Portable by construction — bash only, no Xcode, keychain, codesign or network — so it runs on the
# Linux lane of .github/checks-manifest.yaml on every PR that touches this package.
#
# Usage: scripts/test-build-identity.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOLVER="$SCRIPT_DIR/build-identity.sh"

PASS=0
FAIL=0

pass() { printf '  \033[1;32mok\033[0m   %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  \033[1;31mFAIL\033[0m %s\n' "$1"; printf '       %s\n' "$2"; FAIL=$((FAIL + 1)); }

# Resolves `identity` and echoes the value of one printed variable.
resolve_field() {
    local identity="$1" field="$2"
    (
        eval "$("$RESOLVER" "$identity")"
        printf '%s' "${!field}"
    )
}

assert_field() {
    local what="$1" identity="$2" field="$3" expected="$4" actual
    actual="$(resolve_field "$identity" "$field")" \
        || { fail "$what" "resolver exited non-zero for identity '$identity'"; return; }
    if [[ "$actual" == "$expected" ]]; then
        pass "$what"
    else
        fail "$what" "expected $field='$expected', got '$actual'"
    fi
}

assert_refused() {
    local what="$1" identity="$2"
    if "$RESOLVER" "$identity" >/dev/null 2>&1; then
        fail "$what" "resolver accepted an identity it must refuse: '$identity'"
    else
        pass "$what"
    fi
}

printf '\033[1m[context]\033[0m build identity resolution\n'

# ---------------------------------------------------------------------------------------------
# A release identity keeps the production identifiers. If this ever drifts, shipped builds change
# identity and every existing user's grants, Keychain items and Claude registration are orphaned —
# so it is asserted as tightly as the developer case.
# ---------------------------------------------------------------------------------------------
RELEASE_ID='Developer ID Application: Based Hardware INC (9536L8KLMP)'

assert_field "a Developer ID build keeps the production bundle id" \
    "$RELEASE_ID" CFC_BUNDLE_ID "com.omi.context-for-claude"
assert_field "a Developer ID build keeps the production app name" \
    "$RELEASE_ID" CFC_APP_NAME "Context for Claude"
assert_field "a Developer ID build keeps the production MCP server name" \
    "$RELEASE_ID" CFC_MCP_SERVER_NAME "context-for-claude"
assert_field "a Developer ID build is not marked as development" \
    "$RELEASE_ID" CFC_IS_DEVELOPMENT "0"

# ---------------------------------------------------------------------------------------------
# The regression itself. The self-signed identity below is the exact one build.sh tells developers
# to create, and the certificate that poisoned this app's TCC records for days by writing them
# under the production bundle id.
# ---------------------------------------------------------------------------------------------
DEV_ID='Omi Local Dev Signing'

assert_field "a self-signed build does NOT claim the production bundle id" \
    "$DEV_ID" CFC_BUNDLE_ID "com.omi.context-for-claude.dev"
assert_field "a self-signed build does NOT claim the production app name" \
    "$DEV_ID" CFC_APP_NAME "Context for Claude Dev"
assert_field "a self-signed build does NOT claim the production MCP server name" \
    "$DEV_ID" CFC_MCP_SERVER_NAME "context-for-claude-dev"
assert_field "a self-signed build is marked as development" \
    "$DEV_ID" CFC_IS_DEVELOPMENT "1"

# An arbitrary certificate a developer already owns is still a developer build.
assert_field "an unrecognised certificate does not claim the production bundle id" \
    'Some Other Certificate' CFC_BUNDLE_ID "com.omi.context-for-claude.dev"

# An Apple *Development* certificate is not a Developer ID Application certificate. It is the
# easiest one to confuse for a release identity, and it cannot notarize.
assert_field "an Apple Development certificate is treated as development" \
    'Apple Development: someone@example.com (ABCDE12345)' CFC_BUNDLE_ID "com.omi.context-for-claude.dev"

# The developer and production identities must never coincide in any namespace, whatever the
# constants are edited to.
DEV_BUNDLE="$(resolve_field "$DEV_ID" CFC_BUNDLE_ID)"
REL_BUNDLE="$(resolve_field "$RELEASE_ID" CFC_BUNDLE_ID)"
DEV_APP="$(resolve_field "$DEV_ID" CFC_APP_NAME)"
REL_APP="$(resolve_field "$RELEASE_ID" CFC_APP_NAME)"
DEV_MCP="$(resolve_field "$DEV_ID" CFC_MCP_SERVER_NAME)"
REL_MCP="$(resolve_field "$RELEASE_ID" CFC_MCP_SERVER_NAME)"

if [[ "$DEV_BUNDLE" != "$REL_BUNDLE" && "$DEV_APP" != "$REL_APP" && "$DEV_MCP" != "$REL_MCP" ]]; then
    pass "developer and production identities are disjoint in all three namespaces"
else
    fail "developer and production identities are disjoint in all three namespaces" \
        "bundle '$DEV_BUNDLE' vs '$REL_BUNDLE', app '$DEV_APP' vs '$REL_APP', mcp '$DEV_MCP' vs '$REL_MCP'"
fi

# ---------------------------------------------------------------------------------------------
# The --kind form, used by uninstall.sh, must agree with what the certificate form produces —
# otherwise uninstall.sh would look for an install build.sh never created.
# ---------------------------------------------------------------------------------------------
resolve_kind_field() {
    local kind="$1" field="$2"
    (
        eval "$("$RESOLVER" --kind "$kind")"
        printf '%s' "${!field}"
    )
}

assert_kinds_agree() {
    local kind="$1" identity="$2" field="$3" by_kind by_cert
    by_kind="$(resolve_kind_field "$kind" "$field")"
    by_cert="$(resolve_field "$identity" "$field")"
    if [[ "$by_kind" == "$by_cert" ]]; then
        pass "--kind $kind agrees with its certificate on $field"
    else
        fail "--kind $kind agrees with its certificate on $field" \
            "--kind gave '$by_kind', certificate gave '$by_cert'"
    fi
}

for field in CFC_BUNDLE_ID CFC_APP_NAME CFC_MCP_SERVER_NAME CFC_IS_DEVELOPMENT; do
    assert_kinds_agree development "$DEV_ID"     "$field"
    assert_kinds_agree release     "$RELEASE_ID" "$field"
done

# ---------------------------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------------------------
assert_refused "ad-hoc signing is refused outright" "-"
assert_refused "an unknown --kind is refused" "--kind"
if "$RESOLVER" >/dev/null 2>&1; then
    fail "a missing identity is refused" "resolver accepted no argument at all"
else
    pass "a missing identity is refused"
fi

# ---------------------------------------------------------------------------------------------
# The production Info.plist template must keep holding the production identifier: build.sh derives
# the developer bundle from it by rewriting the built copy, so a template that already said `.dev`
# would ship a developer identifier in a release.
# ---------------------------------------------------------------------------------------------
TEMPLATE="$SCRIPT_DIR/../Resources/Info.plist"
if grep -q '<string>com.omi.context-for-claude</string>' "$TEMPLATE"; then
    pass "Resources/Info.plist still declares the production bundle id"
else
    fail "Resources/Info.plist still declares the production bundle id" \
        "the template no longer contains the production identifier"
fi

printf '\n\033[1m[context]\033[0m %d passed, %d failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
