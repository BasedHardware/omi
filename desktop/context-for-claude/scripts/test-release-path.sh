#!/bin/bash
# Guard tests for the Context release path. This intentionally does not build, sign, notarize,
# contact GitHub, or require any release secret. It runs the appcast generator for real — that is
# the part with behavior worth asserting — and treats the shell helpers' refusals as behavior too.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

fail() { printf 'release-path test failed: %s\n' "$*" >&2; exit 1; }

WORK_DIR="$(mktemp -d /tmp/cfc-release-path.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

FEED_URL="https://github.com/BasedHardware/omi/releases/download/context-for-claude-appcast/appcast.xml"

bash -n \
    "$SCRIPT_DIR/build.sh" \
    "$SCRIPT_DIR/package-dmg.sh" \
    "$SCRIPT_DIR/release-micro-app.sh" \
    "$SCRIPT_DIR/release-context.sh" \
    || fail "shell syntax"
python3 -c 'import py_compile,sys; py_compile.compile(sys.argv[1], doraise=True)' \
    "$SCRIPT_DIR/generate-appcast.py" >/dev/null \
    || fail "generate-appcast.py syntax"

# ---------------------------------------------------------------- the orchestrator's refusals

DRY_RUN_OUTPUT="$("$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --dry-run)" \
    || fail "secretless dry-run"
printf '%s\n' "$DRY_RUN_OUTPUT" | grep -qF 'product=context-for-claude tag=context-for-claude-v1.1.0 version=1.1.0 build=1001000' \
    || fail "tag/version/build derivation"
printf '%s\n' "$DRY_RUN_OUTPUT" | grep -qF "feed=$FEED_URL" \
    || fail "default feed URL"
printf '%s\n' "$DRY_RUN_OUTPUT" | grep -qF 'feed asset appcast.xml on holder release context-for-claude-appcast in BasedHardware/omi' \
    || fail "feed holder derivation"
printf '%s\n' "$DRY_RUN_OUTPUT" | grep -qF 'enclosure=https://github.com/BasedHardware/omi/releases/download/context-for-claude-v1.1.0/ContextForClaude-1.1.0.zip' \
    || fail "enclosure URL"
printf '%s\n' "$DRY_RUN_OUTPUT" | grep -qF 'no build, signing, notarization, GitHub release, appcast' \
    || fail "dry-run side-effect promise"

# The permanent download link is version-less on purpose: the asset name is the URL, so a versioned
# name would change the link on every release and defeat the point.
printf '%s\n' "$DRY_RUN_OUTPUT" | grep -qF 'permanent download link=https://github.com/BasedHardware/omi/releases/download/context-for-claude-latest/ContextForClaude.dmg' \
    || fail "permanent download link"

# Publication falls back to the shared CI token when the scoped one was never provisioned, and says
# so — a release that quietly used a broader credential than intended would be worse than a loud one.
FALLBACK_OUTPUT="$(env -u CONTEXT_GITHUB_TOKEN GH_TOKEN=selection-probe \
    "$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --dry-run 2>&1)" \
    || fail "dry-run with only the shared token"
printf '%s\n' "$FALLBACK_OUTPUT" | grep -qF 'CONTEXT_GITHUB_TOKEN is unset; publishing with the shared GH_TOKEN' \
    || fail "shared-token fallback is silent"
SCOPED_OUTPUT="$(CONTEXT_GITHUB_TOKEN=scoped-probe GH_TOKEN=shared-probe \
    "$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --dry-run 2>&1)" \
    || fail "dry-run with both tokens"
printf '%s\n' "$SCOPED_OUTPUT" | grep -qF 'publishing with the shared' \
    && fail "the shared token was used while a scoped one was available"

# That link is maintained with --clobber, so the same namespace rules that protect the feed have to
# protect it: never another product's release, never a versioned release, never the feed's own.
if LATEST_TAG="omi-desktop-latest" "$SCRIPT_DIR/release-context.sh" \
    --tag context-for-claude-v1.1.0 --dry-run >/dev/null 2>&1; then
    fail "a latest-installer tag outside the product namespace was accepted"
fi
if LATEST_TAG="context-for-claude-v1.1.0" "$SCRIPT_DIR/release-context.sh" \
    --tag context-for-claude-v1.1.0 --dry-run >/dev/null 2>&1; then
    fail "a versioned tag was accepted as the latest-installer holder"
fi
if LATEST_TAG="context-for-claude-appcast" "$SCRIPT_DIR/release-context.sh" \
    --tag context-for-claude-v1.1.0 --dry-run >/dev/null 2>&1; then
    fail "the feed holder was accepted as the latest-installer holder"
fi

if CONTEXT_SPARKLE_PUBLIC_KEY="REPLACE_WITH_SUPublicEDKey_FROM_generate_keys" \
    "$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --dry-run >/dev/null 2>&1; then
    fail "placeholder public key was accepted"
fi

# A feed served by one repository cannot announce enclosures hosted by another.
if CONTEXT_APPCAST_FEED_URL="https://github.com/someone-else/omi/releases/download/context-for-claude-appcast/appcast.xml" \
    "$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --dry-run >/dev/null 2>&1; then
    fail "feed URL from a foreign repository was accepted"
fi

# `releases/latest/download` resolves to the newest release of the whole repository, which ships Omi
# Desktop tags almost daily. It must be refused wherever it can be spelled.
if CONTEXT_APPCAST_FEED_URL="https://github.com/BasedHardware/omi/releases/latest/download/appcast.xml" \
    "$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --dry-run >/dev/null 2>&1; then
    fail "releases/latest/download feed URL was accepted"
fi

# The feed is uploaded with --clobber; a holder tag inside the versioned namespace would let that
# replace an installer asset.
if CONTEXT_APPCAST_FEED_URL="https://github.com/BasedHardware/omi/releases/download/context-for-claude-v1.1.0/appcast.xml" \
    "$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --dry-run >/dev/null 2>&1; then
    fail "versioned tag was accepted as the feed holder"
fi

# No Developer ID, no notarization, no rehearsal flag: a release must not be publishable.
if env -u CFC_SIGN_IDENTITY "$SCRIPT_DIR/release-context.sh" \
    --tag context-for-claude-v1.1.0 --publish >/dev/null 2>&1; then
    fail "publication without a release identity was accepted"
fi

# A rehearsal is not distributable, so it must never reach the production repository.
if "$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1.0 --rehearsal --publish >/dev/null 2>&1; then
    fail "rehearsal publication to BasedHardware/omi was accepted"
fi

if "$SCRIPT_DIR/release-context.sh" --tag context-for-claude-v1.1 --dry-run >/dev/null 2>&1; then
    fail "non-semantic tag version was accepted"
fi

# ---------------------------------------------------------------- the generator, run for real

GEN="$SCRIPT_DIR/generate-appcast.py"
ZIP="$WORK_DIR/ContextForClaude-1.1.0.zip"
printf 'not really a zip, but a real file with a real size' > "$ZIP"
ZIP_BYTES="$(wc -c < "$ZIP" | tr -d ' ')"
SIG="$(printf 'A%.0s' {1..86})=="
MIN_SYSTEM="$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' "$PKG_DIR/Resources/Info.plist")"
[[ -n "$MIN_SYSTEM" ]] || fail "Resources/Info.plist has no LSMinimumSystemVersion to read"

generate() {   # generate <output> <version> <build> [extra args...]
    local output="$1" version="$2" build="$3"
    shift 3
    "$GEN" --output "$output" \
        --title "Context for Claude" \
        --feed-url "$FEED_URL" \
        --version "$version" --build "$build" \
        --zip "$ZIP" --signature "$SIG" \
        --enclosure-url "https://github.com/BasedHardware/omi/releases/download/context-for-claude-v$version/ContextForClaude-$version.zip" \
        --info-plist "$PKG_DIR/Resources/Info.plist" \
        "$@" >/dev/null
}

# `xmllint --xpath` rather than grep: the assertions are about parsed XML, and a feed that only
# looks right as text is exactly the failure worth catching.
xpath() {   # xpath <file> <expression>
    xmllint --xpath "$2" "$1" 2>/dev/null || true
}

generate "$WORK_DIR/first.xml" 1.1.0 1001000 || fail "generator run"
xmllint --noout "$WORK_DIR/first.xml" || fail "generated feed is not well-formed XML"
[[ "$(xpath "$WORK_DIR/first.xml" 'string(/rss/channel/item/enclosure/@length)')" == "$ZIP_BYTES" ]] \
    || fail "enclosure length is not the ZIP's real byte size"
[[ "$(xpath "$WORK_DIR/first.xml" 'string(/rss/channel/item/*[local-name()="minimumSystemVersion"])')" == "$MIN_SYSTEM" ]] \
    || fail "minimumSystemVersion does not come from Resources/Info.plist"
[[ "$(xpath "$WORK_DIR/first.xml" 'string(/rss/channel/item/*[local-name()="version"])')" == "1001000" ]] \
    || fail "sparkle:version is not the numeric build"
[[ "$(xpath "$WORK_DIR/first.xml" 'string(/rss/channel/item/enclosure/@*[local-name()="edSignature"])')" == "$SIG" ]] \
    || fail "edSignature is not the signature it was given"
[[ "$(xpath "$WORK_DIR/first.xml" 'string(/rss/channel/link)')" == "$FEED_URL" ]] \
    || fail "channel link is not the feed URL"

# Update history has to survive a release, and the feed is no longer on disk between releases: the
# previous feed is handed in, and both items must come out.
generate "$WORK_DIR/second.xml" 1.2.0 1002000 --existing "$WORK_DIR/first.xml" || fail "append run"
[[ "$(xpath "$WORK_DIR/second.xml" 'count(/rss/channel/item)')" == "2" ]] \
    || fail "the previously published item was dropped"
[[ "$(xpath "$WORK_DIR/second.xml" 'string(/rss/channel/item[1]/*[local-name()="version"])')" == "1002000" ]] \
    || fail "the new item is not first in the feed"

# Re-running the same release must not reorder the feed or re-date an already-published build.
generate "$WORK_DIR/again.xml" 1.2.0 1002000 --existing "$WORK_DIR/second.xml" || fail "rerun"
diff "$WORK_DIR/second.xml" "$WORK_DIR/again.xml" >/dev/null \
    || fail "re-running the same release changed the feed"

# An existing feed that does not parse must stop the release, not silently start a new feed.
printf 'this is not xml' > "$WORK_DIR/corrupt.xml"
if generate "$WORK_DIR/from-corrupt.xml" 1.3.0 1003000 --existing "$WORK_DIR/corrupt.xml" 2>/dev/null; then
    fail "an unparseable existing feed was accepted"
fi

if "$GEN" --output "$WORK_DIR/no-zip.xml" --title T --feed-url "$FEED_URL" \
    --version 1.1.0 --build 1001000 --zip "$WORK_DIR/absent.zip" --signature "$SIG" \
    --enclosure-url "https://github.com/BasedHardware/omi/releases/download/context-for-claude-v1.1.0/x.zip" \
    --info-plist "$PKG_DIR/Resources/Info.plist" >/dev/null 2>&1; then
    fail "a missing enclosure was accepted"
fi

if generate "$WORK_DIR/bad-sig.xml" 1.1.0 1001000 --signature "" 2>/dev/null; then
    fail "an empty signature was accepted"
fi

if "$GEN" --output "$WORK_DIR/latest.xml" --title T --feed-url "$FEED_URL" \
    --version 1.1.0 --build 1001000 --zip "$ZIP" --signature "$SIG" \
    --enclosure-url "https://github.com/BasedHardware/omi/releases/latest/download/x.zip" \
    --info-plist "$PKG_DIR/Resources/Info.plist" >/dev/null 2>&1; then
    fail "a releases/latest/download enclosure was accepted"
fi

# ---------------------------------------------------------------- static tripwires
#
# These are source scrapes, not behavioral coverage: they hold contracts whose enforcement lives in
# another script or in the deleted backend, where this suite cannot execute them.
#
# `grep -qF`, not `rg`: ripgrep is not part of a stock macOS or CI image, and a missing binary
# exits 127 here — indistinguishable from a real contract regression, so the whole suite reported
# "tag/version/build derivation" failures on a machine that simply lacked the tool.
grep -qF 'CONTEXT_SPARKLE_PUBLIC_KEY' "$SCRIPT_DIR/build.sh" \
    || fail "build key injection contract"
grep -qF 'CONTEXT_SPARKLE_PRIVATE_KEY' "$SCRIPT_DIR/release-context.sh" \
    || fail "Context private key naming contract"
grep -qF 'assert_not_production' "$SCRIPT_DIR/build.sh" \
    || fail "build.sh production guard"
grep -qF 'assert_not_production' "$SCRIPT_DIR/package-dmg.sh" \
    || fail "package-dmg.sh production guard"
# The metadata block existed only so the retired backend feed could parse a release body. Nothing
# reads it now, and reintroducing it would recreate a publisher/parser contract with no parser.
RELEASE_PATH_FILES=(
    "$SCRIPT_DIR/build.sh"
    "$SCRIPT_DIR/package-dmg.sh"
    "$SCRIPT_DIR/release-micro-app.sh"
    "$SCRIPT_DIR/release-context.sh"
    "$SCRIPT_DIR/generate-appcast.py"
)
if grep -qF 'KEY_VALUE_START' "${RELEASE_PATH_FILES[@]}"; then
    fail "the retired release-body metadata block is back in the release path"
fi
if grep -qF 'api.omi.me' "${RELEASE_PATH_FILES[@]}"; then
    fail "the release path references a platform endpoint; GitHub is the whole update backend"
fi
# The feed is an uploaded asset, never a tracked file: the signature only exists after the build, so
# a tracked feed would mean a commit pushed on every release.
if git -C "$PKG_DIR" ls-files --error-unmatch appcast.xml >/dev/null 2>&1; then
    fail "appcast.xml is tracked in the repository; the feed is a release asset"
fi

printf 'Context release-path tests passed\n'
