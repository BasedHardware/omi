#!/usr/bin/env bash
# Local dev signing contract.
#
# Hardened-runtime library validation matches Team IDs, so a signing identity
# that carries no Team ID cannot load the bundled Sparkle/Sentry/onnxruntime
# frameworks. That is true of ad-hoc signing *and* of a self-signed identity
# such as "Omi Local Dev Signing" (`codesign -dvv` reports
# `TeamIdentifier=not set` for both). Keying the entitlement on the identity
# string instead of on the Team ID produced bundles that passed
# `codesign --verify`, returned 0 from `open -a`, and never launched.
#
# These tests drive the real decision through the script's own CLI and through
# run.sh's own function bodies; they never assert on source text.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PREPARE_SCRIPT="$MACOS_DIR/scripts/prepare-local-dev-entitlements.sh"
RUN_SCRIPT="$MACOS_DIR/run.sh"
BASE_ENTITLEMENTS="$MACOS_DIR/Desktop/Omi.entitlements"

LIBRARY_VALIDATION_KEY="com.apple.security.cs.disable-library-validation"
DEVELOPER_ID_IDENTITY="Developer ID Application: Based Hardware INC (9536L8KLMP)"
DEVELOPER_ID_TEAM="9536L8KLMP"
APPLE_DEVELOPMENT_IDENTITY="Apple Development: dev@example.com (AB12CD34EF)"
APPLE_DEVELOPMENT_TEAM="AB12CD34EF"
LOCAL_DEV_IDENTITY="Omi Local Dev Signing"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

has_key() {
    /usr/libexec/PlistBuddy -c "Print :$2" "$1" >/dev/null 2>&1
}

# Feed the script identity metadata and assert the signing mode it derives.
assert_identity_policy() {
    local expected="$1" identity="$2" team_id="$3" named="$4" allow_adhoc="$5"
    local actual status=0
    actual="$("$PREPARE_SCRIPT" --validate-identity \
        "$identity" "$team_id" "$named" "$allow_adhoc" 2>/dev/null)" || status=$?

    if [ "$expected" = "rejected" ]; then
        [ "$status" -ne 0 ] \
            || fail "identity policy accepted '$identity' (team='$team_id', named=$named, adhoc=$allow_adhoc)"
        return
    fi

    [ "$status" -eq 0 ] \
        || fail "identity policy rejected '$identity' (team='$team_id', named=$named, adhoc=$allow_adhoc)"
    [ "$actual" = "$expected" ] \
        || fail "'$identity' (team='$team_id') classified as '$actual', expected '$expected'"
}

# The entitlements a signature with this mode is actually given.
prepare_entitlements() {
    local bundle_id="$1" mode="$2"
    "$PREPARE_SCRIPT" "$BASE_ENTITLEMENTS" "$TMP_ROOT/modes/.dev" "$bundle_id" "$mode"
}

# Run run.sh's own function bodies as the production code they are, in
# dependency order. run.sh runs under bare `set -e`, so adopt exactly those
# options before calling in: `pipefail`/`nounset` would make these functions
# behave differently here than they do in the launcher.
eval_run_function() {
    local name body="" extracted
    for name in "$@"; do
        extracted="$(sed -n "/^$name()/,/^}/p" "$RUN_SCRIPT")"
        [ -n "$extracted" ] || fail "$name is missing from $RUN_SCRIPT"
        body+="$extracted"$'\n'
    done
    set +o pipefail +o nounset
    set -o errexit
    eval "$body"
}

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-local-entitlements-test.XXXXXX")"
cleanup() {
    rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

teamless_path="$TMP_ROOT/teamless.path"
team_scoped_path="$TMP_ROOT/team-scoped.path"

# Prepare opposite signing modes concurrently, as parallel worktrees do.
"$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$TMP_ROOT/worktree-a/.dev" \
    com.omi.omi-bluetooth-quality teamless >"$teamless_path" &
teamless_pid=$!
"$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$TMP_ROOT/worktree-b/.dev" \
    com.omi.omi-other team-scoped >"$team_scoped_path" &
team_scoped_pid=$!
wait "$teamless_pid"
wait "$team_scoped_pid"

teamless_entitlements="$(<"$teamless_path")"
team_scoped_entitlements="$(<"$team_scoped_path")"
[ "$teamless_entitlements" != "$team_scoped_entitlements" ] \
    || fail "parallel worktrees shared an entitlement path"

has_key "$teamless_entitlements" "com.apple.developer.applesignin" \
    && fail "teamless fallback retained Sign in with Apple"
teamless_library_validation="$(/usr/libexec/PlistBuddy \
    -c "Print :$LIBRARY_VALIDATION_KEY" \
    "$teamless_entitlements")"
[ "$teamless_library_validation" = "true" ] \
    || fail "teamless fallback did not disable library validation"

has_key "$team_scoped_entitlements" "com.apple.developer.applesignin" \
    && fail "team-scoped fallback retained Sign in with Apple"
has_key "$team_scoped_entitlements" "$LIBRARY_VALIDATION_KEY" \
    && fail "team-scoped fallback disabled library validation"

# Named apps in one worktree also get distinct generated files.
second_bundle_entitlements="$("$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$TMP_ROOT/worktree-a/.dev" \
    com.omi.omi-second teamless)"
[ "$teamless_entitlements" != "$second_bundle_entitlements" ] \
    || fail "named bundles in one worktree shared an entitlement path"

# Existing output symlinks are replaced atomically, never followed while the
# plist is mutated.
symlink_dev_dir="$TMP_ROOT/symlink-worktree/.dev"
symlink_output_dir="$symlink_dev_dir/local-signing"
symlink_output="$symlink_output_dir/com.omi.omi-symlink.entitlements"
symlink_target="$TMP_ROOT/symlink-target.plist"
mkdir -p "$symlink_output_dir"
cp "$BASE_ENTITLEMENTS" "$symlink_target"
ln -s "$symlink_target" "$symlink_output"
prepared_symlink_output="$("$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$symlink_dev_dir" \
    com.omi.omi-symlink teamless)"
[ ! -L "$prepared_symlink_output" ] || fail "generated output remained a symlink"
has_key "$symlink_target" "com.apple.developer.applesignin" \
    || fail "entitlement generation mutated a symlink target"

directory_symlink_dev_dir="$TMP_ROOT/directory-symlink-worktree/.dev"
directory_symlink_output_dir="$directory_symlink_dev_dir/local-signing"
directory_symlink_output="$directory_symlink_output_dir/com.omi.omi-directory.entitlements"
directory_symlink_target="$TMP_ROOT/external-directory"
mkdir -p "$directory_symlink_output_dir" "$directory_symlink_target"
ln -s "$directory_symlink_target" "$directory_symlink_output"
prepared_directory_output="$("$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$directory_symlink_dev_dir" \
    com.omi.omi-directory teamless)"
[ ! -L "$prepared_directory_output" ] \
    || fail "generated output remained a directory symlink"
[ -f "$prepared_directory_output" ] \
    || fail "directory symlink was not replaced by a plist"
[ -z "$(find "$directory_symlink_target" -mindepth 1 -maxdepth 1 -print -quit)" ] \
    || fail "entitlement plist escaped into a symlinked directory"

# ── Signing mode is derived from the Team ID, not from the identity string ──

# The documented local identity is self-signed with no Team ID. It must be
# accepted and classified teamless; classifying it as a real identity is what
# produced bundles that could not launch.
assert_identity_policy teamless "$LOCAL_DEV_IDENTITY" "" false 0
assert_identity_policy teamless "$LOCAL_DEV_IDENTITY" "" true 0

# Identities that do carry a Team ID keep library validation.
assert_identity_policy team-scoped "$APPLE_DEVELOPMENT_IDENTITY" "$APPLE_DEVELOPMENT_TEAM" false 0
assert_identity_policy team-scoped "$APPLE_DEVELOPMENT_IDENTITY" "$APPLE_DEVELOPMENT_TEAM" true 0
assert_identity_policy team-scoped "$DEVELOPER_ID_IDENTITY" "$DEVELOPER_ID_TEAM" false 0

# Ad-hoc keeps its own opt-in gate: it carries no Team ID *and* it invalidates
# the bundle's Screen Recording grant.
assert_identity_policy teamless - "" true 1
assert_identity_policy rejected - "" true 0
assert_identity_policy rejected - "" false 1

# Dishonest or missing metadata must be refused rather than defaulted.
assert_identity_policy rejected - "$DEVELOPER_ID_TEAM" true 1
assert_identity_policy rejected "" "" false 0
assert_identity_policy rejected "$DEVELOPER_ID_IDENTITY" "9536 L8KLMP" false 0
assert_identity_policy rejected "$DEVELOPER_ID_IDENTITY" "$DEVELOPER_ID_TEAM" yes 0
assert_identity_policy rejected "$DEVELOPER_ID_IDENTITY" "$DEVELOPER_ID_TEAM" false 2

# ── End to end: the classification decides the entitlement ──

mkdir -p "$TMP_ROOT/modes/.dev"

local_dev_mode="$("$PREPARE_SCRIPT" --validate-identity "$LOCAL_DEV_IDENTITY" "" true 0)"
local_dev_entitlements="$(prepare_entitlements com.omi.omi-local-dev "$local_dev_mode")"
has_key "$local_dev_entitlements" "$LIBRARY_VALIDATION_KEY" \
    || fail "the documented local identity produced a bundle that cannot load its frameworks"

# Production signing must be untouched: the release pipeline's Developer ID
# carries a Team ID, so it can never acquire disable-library-validation.
release_mode="$("$PREPARE_SCRIPT" --validate-identity "$DEVELOPER_ID_IDENTITY" "$DEVELOPER_ID_TEAM" false 0)"
[ "$release_mode" = "team-scoped" ] || fail "release Developer ID was not team-scoped"
release_entitlements="$(prepare_entitlements com.omi.computer-macos "$release_mode")"
has_key "$release_entitlements" "$LIBRARY_VALIDATION_KEY" \
    && fail "release Developer ID signing gained disable-library-validation"

# ── Team ID resolution ──

for identity in "-" ""; do
    resolved_team="$("$PREPARE_SCRIPT" --identity-team-id "$identity")"
    [ -z "$resolved_team" ] \
        || fail "identity '$identity' reported Team ID '$resolved_team'"
done

# ── run.sh: entitlement-source selection ──

(
    eval_run_function local_entitlements_fallback_reason

    # A teamless identity needs the generated entitlements even for the default
    # unnamed bundle whose provisioning profile matches — library validation,
    # not the profile, is what blocks the launch.
    reason="$(local_entitlements_fallback_reason teamless false true "$DEVELOPER_ID_TEAM" "")"
    [ -n "$reason" ] || fail "teamless signing did not select the local entitlements fallback"
    case "$reason" in
        *"Team ID"*) ;;
        *) fail "teamless fallback reason did not name the Team ID problem: $reason" ;;
    esac

    # A matching Team ID identity with its own profile keeps the checked-in
    # entitlements — this is the path production-shaped signing takes.
    reason="$(local_entitlements_fallback_reason team-scoped false true "$DEVELOPER_ID_TEAM" "$DEVELOPER_ID_TEAM")"
    [ -z "$reason" ] || fail "matching team/profile signing was pushed onto the local fallback: $reason"

    # Named bundles and profile mismatches keep their existing fallbacks.
    reason="$(local_entitlements_fallback_reason team-scoped true false "" "$APPLE_DEVELOPMENT_TEAM")"
    [ -n "$reason" ] || fail "named bundle lost its entitlements fallback"
    reason="$(local_entitlements_fallback_reason team-scoped false true "$DEVELOPER_ID_TEAM" "$APPLE_DEVELOPMENT_TEAM")"
    [ -n "$reason" ] || fail "profile/identity team mismatch lost its entitlements fallback"
    reason="$(local_entitlements_fallback_reason team-scoped false true "" "$APPLE_DEVELOPMENT_TEAM")"
    [ -n "$reason" ] || fail "unreadable provisioning profile lost its entitlements fallback"
    reason="$(local_entitlements_fallback_reason team-scoped false false "" "$APPLE_DEVELOPMENT_TEAM")"
    [ -z "$reason" ] || fail "an unprofiled team-scoped bundle was pushed onto the local fallback: $reason"
)

# ── run.sh: identity resolution prefers a stable identity over ad-hoc ──
#
# resolve_signing_identity is driven together with the helpers it now
# delegates to, against faked environment binaries: `security` answers
# find-identity and the keychain calls; `codesign` answers probes, failing
# for identities on the refusal list exactly as the keychain refuses to
# release a key (errSecInternalComponent). Keychain and stamp state is
# sandboxed under TMP_ROOT via HOME and OMI_LOCAL_SIGN_KEYCHAIN overrides.

FAKE_BIN="$TMP_ROOT/fake-bin"
mkdir -p "$FAKE_BIN"
REFUSED_IDENTITIES_FILE="$TMP_ROOT/refused-identities"
FAKE_CREATED_IDENTITY="$LOCAL_DEV_IDENTITY"
export REFUSED_IDENTITIES_FILE FAKE_CREATED_IDENTITY
: >"$REFUSED_IDENTITIES_FILE"

refuse_identities() {
    printf '%s\n' "$@" >>"$REFUSED_IDENTITIES_FILE"
}

# What `security find-identity -v -p codesigning` reports.
FAKE_IDENTITY_LISTING='     0 valid identities found'
set_fake_identity_listing() {
    FAKE_IDENTITY_LISTING="$1"
    export FAKE_IDENTITY_LISTING
}

cat >"$FAKE_BIN/security" <<'EOF'
#!/bin/bash
case "$1" in
    find-identity)
        printf '%s\n' "$FAKE_IDENTITY_LISTING"
        ;;
    import)
        # Importing the generated self-signed identity is what makes it usable.
        sed -i '' "/^$FAKE_CREATED_IDENTITY$/d" "$REFUSED_IDENTITIES_FILE" 2>/dev/null
        ;;
    create-keychain)
        for arg in "$@"; do :; done
        touch "$arg" 2>/dev/null
        ;;
esac
exit 0
EOF
chmod +x "$FAKE_BIN/security"

cat >"$FAKE_BIN/codesign" <<'EOF'
#!/bin/bash
# Identity probes answer the way the keychain would: a refused identity
# fails instantly, which is what errSecInternalComponent looks like from
# codesign. Anything else signs.
identity=""
while [ $# -gt 0 ]; do
    case "$1" in
        --sign) identity="$2"; shift 2; continue ;;
    esac
    shift
done
if [ -n "$identity" ] && grep -Fxq -- "$identity" "$REFUSED_IDENTITIES_FILE" 2>/dev/null; then
    exit 1
fi
exit 0
EOF
chmod +x "$FAKE_BIN/codesign"

(
    PATH="$FAKE_BIN:$PATH"
    HOME="$TMP_ROOT/sandbox-home"
    mkdir -p "$HOME/Library/Keychains"
    step() { :; }
    substep() { :; }
    IS_NAMED_BUNDLE=true
    BUNDLE_ID=com.omi.omi-signfix
    OMI_ALLOW_ADHOC_SIGN=1
    OMI_LOCAL_DEV_SIGN_IDENTITY="$LOCAL_DEV_IDENTITY"
    OMI_LOCAL_SIGN_KEYCHAIN="$HOME/Library/Keychains/omi-local-dev-signing.keychain-db"
    OMI_LOCAL_SIGN_KEYCHAIN_PASSWORD=test-only
    eval_run_function \
        signing_identity_usable \
        add_keychain_to_search_list \
        ensure_local_dev_signing_identity \
        signing_identity_stamp_path \
        remembered_signing_identity \
        resolve_signing_identity

    stamp_file="$HOME/Library/Application Support/Omi Dev Bundles/$BUNDLE_ID/.signing-identity"
    reset_case() {
        SIGN_IDENTITY=""
        rm -f "$stamp_file" "$OMI_LOCAL_SIGN_KEYCHAIN"
        : >"$REFUSED_IDENTITIES_FILE"
    }

    # Only the self-signed identity exists: it must win over ad-hoc, because
    # ad-hoc would drop this bundle's Screen Recording grant.
    reset_case
    set_fake_identity_listing "  1) BB925114BCB64BD0D17B4CA18CC67B8B2A5CE614 \"$LOCAL_DEV_IDENTITY\"
     1 valid identities found"
    resolve_signing_identity
    [ "$SIGN_IDENTITY" = "$LOCAL_DEV_IDENTITY" ] \
        || fail "ad-hoc signing was chosen over the stable local identity (got '$SIGN_IDENTITY')"

    # An Apple identity still wins over the self-signed one.
    reset_case
    set_fake_identity_listing "  1) AAAA \"$APPLE_DEVELOPMENT_IDENTITY\"
  2) BBBB \"$LOCAL_DEV_IDENTITY\"
     2 valid identities found"
    resolve_signing_identity
    [ "$SIGN_IDENTITY" = "$APPLE_DEVELOPMENT_IDENTITY" ] \
        || fail "Apple Development identity was not preferred (got '$SIGN_IDENTITY')"

    # A listed identity is not a usable one: presence is not permission. A key
    # the keychain refuses to release must lose to the stable local identity,
    # not fail the build after the compile.
    reset_case
    set_fake_identity_listing "  1) AAAA \"$APPLE_DEVELOPMENT_IDENTITY\"
     1 valid identities found"
    refuse_identities "$APPLE_DEVELOPMENT_IDENTITY"
    resolve_signing_identity
    [ "$SIGN_IDENTITY" = "$LOCAL_DEV_IDENTITY" ] \
        || fail "a refused Apple Development identity was chosen anyway (got '$SIGN_IDENTITY')"

    # An identity this bundle already wears wins over a "better" one, because
    # switching resets every permission the bundle has been granted.
    reset_case
    set_fake_identity_listing "  1) AAAA \"$APPLE_DEVELOPMENT_IDENTITY\"
     1 valid identities found"
    mkdir -p "$(dirname "$stamp_file")"
    printf '%s' "$LOCAL_DEV_IDENTITY" >"$stamp_file"
    resolve_signing_identity
    [ "$SIGN_IDENTITY" = "$LOCAL_DEV_IDENTITY" ] \
        || fail "the bundle's remembered identity was not reused (got '$SIGN_IDENTITY')"

    # With nothing in the keychain the local identity is created on demand —
    # never ad-hoc, which would silently drop the Screen Recording grant.
    reset_case
    set_fake_identity_listing '     0 valid identities found'
    refuse_identities "$LOCAL_DEV_IDENTITY"   # does not exist yet: unusable until imported
    resolve_signing_identity
    [ "$SIGN_IDENTITY" = "$LOCAL_DEV_IDENTITY" ] \
        || fail "on-demand local identity creation was not used (got '$SIGN_IDENTITY')"
    [ -f "$OMI_LOCAL_SIGN_KEYCHAIN" ] \
        || fail "the local identity was reported usable without creating its keychain"

    # Ad-hoc remains reachable, but only by opting out of the local identity.
    reset_case
    set_fake_identity_listing '     0 valid identities found'
    refuse_identities "$LOCAL_DEV_IDENTITY"
    OMI_SKIP_LOCAL_SIGN_IDENTITY=1
    resolve_signing_identity
    [ "$SIGN_IDENTITY" = "-" ] \
        || fail "opted-in ad-hoc fallback stopped working (got '$SIGN_IDENTITY')"
    unset OMI_SKIP_LOCAL_SIGN_IDENTITY
)

# Preparing a named bundle must never mutate the checked-in source plist.
has_key "$BASE_ENTITLEMENTS" "com.apple.developer.applesignin" \
    || fail "source entitlements were mutated"

# Retired mode names must not silently generate entitlements again.
for retired_mode in adhoc development invalid; do
    if "$PREPARE_SCRIPT" \
        "$BASE_ENTITLEMENTS" "$TMP_ROOT/invalid/.dev" \
        com.omi.invalid "$retired_mode" >/dev/null 2>&1; then
        fail "signing mode '$retired_mode' was accepted"
    fi
done
if "$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$TMP_ROOT/invalid/.dev" \
    '../escape' teamless >/dev/null 2>&1; then
    fail "unsafe bundle ID was accepted"
fi

echo "local dev entitlement tests passed"
