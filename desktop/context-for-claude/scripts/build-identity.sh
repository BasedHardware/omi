#!/bin/bash
#
# The single owner of the mapping from *signing identity* to *platform identity*.
#
# Usage:
#   eval "$(scripts/build-identity.sh 'Developer ID Application: Based Hardware INC (9536L8KLMP)')"
#
# Prints four shell assignments, or exits non-zero with a reason on stderr:
#   CFC_BUNDLE_ID          CFBundleIdentifier for the built bundle
#   CFC_APP_NAME           bundle name, install-path basename, and Mach-O filename
#   CFC_MCP_SERVER_NAME    key under `mcpServers` and the ~/.claude/skills directory name
#   CFC_IS_DEVELOPMENT     1 when this build is not signed for release
#
# ---------------------------------------------------------------------------------------------
# WHY A DEVELOPER BUILD MUST NOT ANSWER TO THE PRODUCTION IDENTIFIER
#
# macOS stores a *code requirement* — which pins the signing certificate — alongside every TCC
# permission grant. Two builds that share a bundle identifier but carry different certificates
# therefore write mutually unsatisfiable records. Observed on a developer's Mac, both bundles
# claiming `com.omi.context-for-claude`:
#
#   dev      designated => identifier "com.omi.context-for-claude"
#                          and certificate leaf = H"bb925114bcb64bd0d17b4ca18cc67b8b2a5ce614"
#   release  designated => identifier "com.omi.context-for-claude" and anchor apple generic
#                          and ... certificate leaf[subject.OU] = "9536L8KLMP"
#
# Whichever build is granted first wins the record, and from then on tccd logs
#
#   Failed to match existing code requirement for subject com.omi.context-for-claude
#
# for the other one — while System Settings still draws the switch ON, because the *allowed* flag
# and the *requirement* are separate fields. The user can toggle it forever and nothing changes;
# only `tccutil reset` clears it. That cost several days of debugging and shipped three rounds of
# dead-end guidance to users.
#
# Requiring a *stable* local certificate (which build.sh already does) is not enough: it makes
# grants stick between developer builds and still guarantees a poisoned handoff to the release
# build, because stable is not the same as identical. The identifiers must diverge instead.
#
# This mapping is a separate file, and pure, so it can be exercised directly by
# `scripts/test-build-identity.sh` on any machine — no Xcode, no keychain, no codesign.
# ---------------------------------------------------------------------------------------------

set -euo pipefail

# The production identity. These four strings are what a notarized, Developer-ID-signed build
# answers to, and nothing else may claim them.
readonly PRODUCTION_BUNDLE_ID="com.omi.context-for-claude"
readonly PRODUCTION_APP_NAME="Context for Claude"
readonly PRODUCTION_MCP_SERVER_NAME="context-for-claude"

# The developer identity. Distinct in all three namespaces macOS and Claude Code key on, so a
# developer build and an installed release can coexist without either disturbing the other's
# TCC records, Keychain items, or `mcpServers` registration.
readonly DEVELOPMENT_BUNDLE_ID="com.omi.context-for-claude.dev"
readonly DEVELOPMENT_APP_NAME="Context for Claude Dev"
readonly DEVELOPMENT_MCP_SERVER_NAME="context-for-claude-dev"

die() { printf '\033[1;31m[context]\033[0m %s\n' "$*" >&2; exit 1; }

# Two input forms:
#
#   build-identity.sh '<signing identity>'   derive the kind from the certificate (build.sh)
#   build-identity.sh --kind development     name the kind outright (uninstall.sh, which is
#   build-identity.sh --kind release         removing an install rather than signing one)
#
IS_DEVELOPMENT=""

case "${1-}" in
    "")
        die "build-identity.sh needs a signing identity, or --kind development|release"
        ;;
    --kind)
        case "${2-}" in
            development) IS_DEVELOPMENT=1 ;;
            release)     IS_DEVELOPMENT=0 ;;
            *)           die "--kind takes 'development' or 'release', got '${2-}'" ;;
        esac
        ;;
    --*)
        die "unknown option '$1' (expected a signing identity, or --kind development|release)"
        ;;
    -)
        # Ad-hoc signing is refused outright rather than mapped to the developer identity. Its
        # signature changes on every build, so macOS treats each build as a new app and revokes
        # consent every time — a developer identifier would not rescue that, only hide it.
        die "ad-hoc signing ('-') is not supported: the signature changes every build, so macOS
revokes Screen Recording and microphone consent each time. Use a stable certificate."
        ;;
    *)
        # The one predicate. A release build is one signed by an Apple-issued Developer ID
        # Application certificate; everything else — self-signed, Apple Development, enterprise,
        # unknown — is a developer build.
        #
        # This tests the certificate's *name*, which is all that is knowable here, and a
        # self-signed certificate can be given any name its creator likes. The certificate itself
        # is checked where the signed bundle exists, by assert_release_signing_authority() in
        # package-dmg.sh, which reads the authority chain out of the signature.
        if [[ "$1" == *"Developer ID Application:"* ]]; then
            IS_DEVELOPMENT=0
        else
            IS_DEVELOPMENT=1
        fi
        ;;
esac

if [[ "$IS_DEVELOPMENT" -eq 1 ]]; then
    printf "CFC_BUNDLE_ID='%s'\n"       "$DEVELOPMENT_BUNDLE_ID"
    printf "CFC_APP_NAME='%s'\n"        "$DEVELOPMENT_APP_NAME"
    printf "CFC_MCP_SERVER_NAME='%s'\n" "$DEVELOPMENT_MCP_SERVER_NAME"
    printf "CFC_IS_DEVELOPMENT=1\n"
else
    printf "CFC_BUNDLE_ID='%s'\n"       "$PRODUCTION_BUNDLE_ID"
    printf "CFC_APP_NAME='%s'\n"        "$PRODUCTION_APP_NAME"
    printf "CFC_MCP_SERVER_NAME='%s'\n" "$PRODUCTION_MCP_SERVER_NAME"
    printf "CFC_IS_DEVELOPMENT=0\n"
fi
