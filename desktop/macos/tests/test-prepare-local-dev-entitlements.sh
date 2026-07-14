#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PREPARE_SCRIPT="$MACOS_DIR/scripts/prepare-local-dev-entitlements.sh"
BASE_ENTITLEMENTS="$MACOS_DIR/Desktop/Omi.entitlements"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

has_key() {
    /usr/libexec/PlistBuddy -c "Print :$2" "$1" >/dev/null 2>&1
}

assert_identity_policy() {
    local expected="$1" identity="$2" named="$3" allow_adhoc="$4"
    if "$PREPARE_SCRIPT" --validate-identity \
        "$identity" "$named" "$allow_adhoc" >/dev/null 2>&1; then
        [ "$expected" = "pass" ] || fail "unsafe identity policy was accepted"
    else
        [ "$expected" = "fail" ] || fail "safe identity policy was rejected"
    fi
}

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-local-entitlements-test.XXXXXX")"
cleanup() {
    rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

adhoc_path="$TMP_ROOT/adhoc.path"
development_path="$TMP_ROOT/development.path"

# Prepare opposite signing modes concurrently, as parallel worktrees do.
"$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$TMP_ROOT/worktree-a/.dev" \
    com.omi.omi-bluetooth-quality adhoc >"$adhoc_path" &
adhoc_pid=$!
"$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$TMP_ROOT/worktree-b/.dev" \
    com.omi.omi-other development >"$development_path" &
development_pid=$!
wait "$adhoc_pid"
wait "$development_pid"

adhoc_entitlements="$(<"$adhoc_path")"
development_entitlements="$(<"$development_path")"
[ "$adhoc_entitlements" != "$development_entitlements" ] \
    || fail "parallel worktrees shared an entitlement path"

has_key "$adhoc_entitlements" "com.apple.developer.applesignin" \
    && fail "ad-hoc fallback retained Sign in with Apple"
adhoc_library_validation="$(/usr/libexec/PlistBuddy \
    -c "Print :com.apple.security.cs.disable-library-validation" \
    "$adhoc_entitlements")"
[ "$adhoc_library_validation" = "true" ] \
    || fail "ad-hoc fallback did not disable library validation"

has_key "$development_entitlements" "com.apple.developer.applesignin" \
    && fail "development fallback retained Sign in with Apple"
has_key "$development_entitlements" "com.apple.security.cs.disable-library-validation" \
    && fail "real-identity fallback disabled library validation"

# Named apps in one worktree also get distinct generated files.
second_bundle_entitlements="$("$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$TMP_ROOT/worktree-a/.dev" \
    com.omi.omi-second adhoc)"
[ "$adhoc_entitlements" != "$second_bundle_entitlements" ] \
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
    com.omi.omi-symlink adhoc)"
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
    com.omi.omi-directory adhoc)"
[ ! -L "$prepared_directory_output" ] \
    || fail "generated output remained a directory symlink"
[ -f "$prepared_directory_output" ] \
    || fail "directory symlink was not replaced by a plist"
[ -z "$(find "$directory_symlink_target" -mindepth 1 -maxdepth 1 -print -quit)" ] \
    || fail "entitlement plist escaped into a symlinked directory"

assert_identity_policy pass "Apple Development: Test" false 0
assert_identity_policy pass - true 1
assert_identity_policy fail - true 0
assert_identity_policy fail - false 1

# Preparing a named bundle must never mutate the checked-in source plist.
has_key "$BASE_ENTITLEMENTS" "com.apple.developer.applesignin" \
    || fail "source entitlements were mutated"

if "$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$TMP_ROOT/invalid/.dev" \
    com.omi.invalid invalid >/dev/null 2>&1; then
    fail "invalid signing mode was accepted"
fi
if "$PREPARE_SCRIPT" \
    "$BASE_ENTITLEMENTS" "$TMP_ROOT/invalid/.dev" \
    '../escape' adhoc >/dev/null 2>&1; then
    fail "unsafe bundle ID was accepted"
fi

echo "local dev entitlement tests passed"
