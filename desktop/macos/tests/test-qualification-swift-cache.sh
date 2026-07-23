#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_HELPER="$SCRIPT_DIR/../scripts/qualification-swift-cache.sh"
TMP_ROOT_RAW="$(mktemp -d "${TMPDIR:-/tmp}/omi-qualification-swift-cache-test.XXXXXX")"
TMP_ROOT="$(cd "$TMP_ROOT_RAW" && pwd -P)"
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

expect_rejected() {
  local label="$1" expected="$2"
  shift 2
  if "$@" >"$TMP_ROOT/$label.out" 2>"$TMP_ROOT/$label.err"; then
    fail "$label was accepted"
  fi
  grep -Fq "$expected" "$TMP_ROOT/$label.err" \
    || fail "$label did not report '$expected': $(cat "$TMP_ROOT/$label.err")"
}

# Capture Git's repository-local namespace before any fixture injects its own
# non-exported shell variables. Hooks may also receive exported Git config
# overrides, so fixture_git clears both sets while preserving PATH and HOME.
REPOSITORY_LOCAL_GIT_VARS="$(git rev-parse --local-env-vars)"
clear_inherited_git_environment() {
  local variable
  unset $REPOSITORY_LOCAL_GIT_VARS
  while IFS='=' read -r variable _; do
    if [[ "$variable" == GIT_* ]]; then
      unset "$variable"
    fi
  done < <(env)
}

# The cache helper is itself part of this synthetic-repository test, so isolate
# the complete fixture subprocess before any helper or direct Git command runs.
clear_inherited_git_environment

fixture_git() (
  clear_inherited_git_environment
  git "$@"
)

vulnerable_git() {
  git "$@"
}

make_repo() {
  local path="$1" fixture_identity="${2:-default}" git_runner="${3:-fixture_git}"
  mkdir -p "$path/desktop/macos/Desktop"
  cat > "$path/desktop/macos/Desktop/Package.swift" <<SWIFT
// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "QualificationCacheFixture-$fixture_identity")
SWIFT
  cat > "$path/desktop/macos/Desktop/Package.resolved" <<JSON
{
  "originHash": "$fixture_identity",
  "pins": [
    {
      "identity": "fixture",
      "kind": "remoteSourceControl",
      "location": "https://example.invalid/fixture.git",
      "state": {
        "revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "version": "1.0.0"
      }
    }
  ],
  "version": 3
}
JSON
  "$git_runner" -C "$path" init -q
  "$git_runner" -C "$path" config user.email cache-test@omi.invalid
  "$git_runner" -C "$path" config user.name 'Cache Test'
  "$git_runner" -C "$path" config core.hooksPath /dev/null
  "$git_runner" -C "$path" add desktop/macos/Desktop/Package.swift desktop/macos/Desktop/Package.resolved
  "$git_runner" -C "$path" commit -qm "fixture $fixture_identity"
}

assert_outer_unchanged() {
  local repo="$1" git_dir="$2" expected_head="$3" expected_index="$4"
  local expected_package_swift="$5" expected_package_resolved="$6"
  [[ "$(fixture_git -C "$repo" rev-parse HEAD)" == "$expected_head" ]] \
    || { echo "fixture setup changed the outer repository HEAD" >&2; return 1; }
  [[ "$(shasum -a 256 "$git_dir/index" | cut -d ' ' -f 1)" == "$expected_index" ]] \
    || { echo "fixture setup changed the outer repository index" >&2; return 1; }
  [[ "$(shasum -a 256 "$repo/desktop/macos/Desktop/Package.swift" | cut -d ' ' -f 1)" == "$expected_package_swift" ]] \
    || { echo "fixture setup changed the outer Package.swift" >&2; return 1; }
  [[ "$(shasum -a 256 "$repo/desktop/macos/Desktop/Package.resolved" | cut -d ' ' -f 1)" == "$expected_package_resolved" ]] \
    || { echo "fixture setup changed the outer Package.resolved" >&2; return 1; }
}

# Git exports repository-local variables while hooks run. Prove fixture setup
# cannot redirect its nested Git commands into that invoking repository.
OUTER_REPO="$TMP_ROOT/outer-repo"
make_repo "$OUTER_REPO" outer
OUTER_GIT_DIR="$(fixture_git -C "$OUTER_REPO" rev-parse --absolute-git-dir)"
OUTER_HEAD_BEFORE="$(fixture_git -C "$OUTER_REPO" rev-parse HEAD)"
OUTER_INDEX_BEFORE="$(shasum -a 256 "$OUTER_GIT_DIR/index" | cut -d ' ' -f 1)"
OUTER_PACKAGE_SWIFT_BEFORE="$(shasum -a 256 "$OUTER_REPO/desktop/macos/Desktop/Package.swift" | cut -d ' ' -f 1)"
OUTER_PACKAGE_RESOLVED_BEFORE="$(shasum -a 256 "$OUTER_REPO/desktop/macos/Desktop/Package.resolved" | cut -d ' ' -f 1)"

INHERITED_REPO="$TMP_ROOT/inherited-repo"
GIT_DIR="$OUTER_GIT_DIR" GIT_INDEX_FILE="$OUTER_GIT_DIR/index" make_repo "$INHERITED_REPO" inherited
assert_outer_unchanged "$OUTER_REPO" "$OUTER_GIT_DIR" "$OUTER_HEAD_BEFORE" "$OUTER_INDEX_BEFORE" \
  "$OUTER_PACKAGE_SWIFT_BEFORE" "$OUTER_PACKAGE_RESOLVED_BEFORE"
[[ "$(fixture_git -C "$INHERITED_REPO" rev-parse --show-toplevel)" == "$INHERITED_REPO" ]] \
  || fail "fixture setup did not create an isolated repository"

# Negative control: the same observably different fixture must mutate the outer
# synthetic repository when Git's inherited environment is deliberately kept.
# The nested commit must succeed, then the shared integrity assertion must fail
# specifically on outer mutation rather than an incidental Git error.
VULNERABLE_OUTER_REPO="$TMP_ROOT/vulnerable-outer-repo"
make_repo "$VULNERABLE_OUTER_REPO" vulnerable-outer
VULNERABLE_OUTER_GIT_DIR="$(fixture_git -C "$VULNERABLE_OUTER_REPO" rev-parse --absolute-git-dir)"
VULNERABLE_OUTER_HEAD_BEFORE="$(fixture_git -C "$VULNERABLE_OUTER_REPO" rev-parse HEAD)"
VULNERABLE_OUTER_INDEX_BEFORE="$(shasum -a 256 "$VULNERABLE_OUTER_GIT_DIR/index" | cut -d ' ' -f 1)"
VULNERABLE_OUTER_PACKAGE_SWIFT_BEFORE="$(shasum -a 256 "$VULNERABLE_OUTER_REPO/desktop/macos/Desktop/Package.swift" | cut -d ' ' -f 1)"
VULNERABLE_OUTER_PACKAGE_RESOLVED_BEFORE="$(shasum -a 256 "$VULNERABLE_OUTER_REPO/desktop/macos/Desktop/Package.resolved" | cut -d ' ' -f 1)"
VULNERABLE_INHERITED_REPO="$TMP_ROOT/vulnerable-inherited-repo"
GIT_DIR="$VULNERABLE_OUTER_GIT_DIR" GIT_INDEX_FILE="$VULNERABLE_OUTER_GIT_DIR/index" \
  make_repo "$VULNERABLE_INHERITED_REPO" vulnerable-inherited vulnerable_git
if assert_outer_unchanged \
    "$VULNERABLE_OUTER_REPO" "$VULNERABLE_OUTER_GIT_DIR" \
    "$VULNERABLE_OUTER_HEAD_BEFORE" "$VULNERABLE_OUTER_INDEX_BEFORE" \
    "$VULNERABLE_OUTER_PACKAGE_SWIFT_BEFORE" "$VULNERABLE_OUTER_PACKAGE_RESOLVED_BEFORE" \
    >"$TMP_ROOT/vulnerable-integrity.out" 2>"$TMP_ROOT/vulnerable-integrity.err"; then
  fail "vulnerable negative control left the outer repository unchanged"
fi
grep -Fq "fixture setup changed the outer repository HEAD" "$TMP_ROOT/vulnerable-integrity.err" \
  || fail "vulnerable negative control did not reach the outer integrity assertion: $(cat "$TMP_ROOT/vulnerable-integrity.err")"
echo "vulnerable inherited-Git negative control reached the integrity assertion and detected outer HEAD mutation"

TOOLCHAIN_SHIM_DIR="$TMP_ROOT/toolchain-shim"
mkdir -p "$TOOLCHAIN_SHIM_DIR"
cat > "$TOOLCHAIN_SHIM_DIR/swift" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
echo "PATH swift must not be used directly" >&2
exit 42
SH
cat > "$TOOLCHAIN_SHIM_DIR/xcrun" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == "swift" ]]
shift
[[ "${1:-}" == "package" && "${2:-}" == "dump-package" && "${3:-}" == "--package-path" && -n "${4:-}" ]]
if grep -Fq '// invalid-package' "$4/Package.swift"; then
  echo "invalid fixture package" >&2
  exit 1
fi
printf '%s\n' '{}'
SH
chmod +x "$TOOLCHAIN_SHIM_DIR/swift" "$TOOLCHAIN_SHIM_DIR/xcrun"
export PATH="$TOOLCHAIN_SHIM_DIR:$PATH"

export OMI_QUALIFICATION_SWIFT_CACHE_ROOT="$TMP_ROOT/cache"
export OMI_QUALIFICATION_SWIFT_CACHE_XCODE="Xcode 16.4\nBuild version 16F6"
export OMI_QUALIFICATION_SWIFT_CACHE_SWIFT="Apple Swift version 6.1"
export OMI_QUALIFICATION_SWIFT_CACHE_MACOS="15.5 (24F74)"
export OMI_QUALIFICATION_SWIFT_CACHE_ARCH="arm64"

REPO_A="$TMP_ROOT/repo-a"
REPO_A_OTHER_PATH="$TMP_ROOT/repo-a-other-path"
make_repo "$REPO_A"
cp -R "$REPO_A" "$REPO_A_OTHER_PATH"
SHA_A="$(fixture_git -C "$REPO_A" rev-parse HEAD)"
SHA_B="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

INVALID_PACKAGE_REPO="$TMP_ROOT/invalid-package-repo"
make_repo "$INVALID_PACKAGE_REPO"
printf '%s\n' '// invalid-package' > "$INVALID_PACKAGE_REPO/desktop/macos/Desktop/Package.swift"
fixture_git -C "$INVALID_PACKAGE_REPO" add desktop/macos/Desktop/Package.swift
fixture_git -C "$INVALID_PACKAGE_REPO" commit -qm 'invalid package fixture'
INVALID_PACKAGE_SHA="$(fixture_git -C "$INVALID_PACKAGE_REPO" rev-parse HEAD)"
expect_rejected invalid-package "Package.swift failed swift package dump-package" \
  "$CACHE_HELPER" prepare "$INVALID_PACKAGE_SHA" "$INVALID_PACKAGE_REPO"

EMPTY_PINS_REPO="$TMP_ROOT/empty-pins-repo"
make_repo "$EMPTY_PINS_REPO"
printf '%s\n' '{"pins":[],"version":3}' > "$EMPTY_PINS_REPO/desktop/macos/Desktop/Package.resolved"
fixture_git -C "$EMPTY_PINS_REPO" add desktop/macos/Desktop/Package.resolved
fixture_git -C "$EMPTY_PINS_REPO" commit -qm 'empty pins fixture'
EMPTY_PINS_SHA="$(fixture_git -C "$EMPTY_PINS_REPO" rev-parse HEAD)"
expect_rejected empty-pins "Package.resolved must be valid JSON version 3 with non-empty pins" \
  "$CACHE_HELPER" prepare "$EMPTY_PINS_SHA" "$EMPTY_PINS_REPO"

# Publication must serialize same-SHA creators. The mv shim holds both old
# implementations immediately after their no-destination precheck, making the
# directory-into-directory race deterministic instead of scheduler-dependent.
CONCURRENT_CACHE="$TMP_ROOT/concurrent-cache"
MV_SHIM_DIR="$TMP_ROOT/mv-shim"
MV_BARRIER="$TMP_ROOT/mv-barrier"
mkdir -p "$MV_SHIM_DIR" "$MV_BARRIER"
REAL_MV="$(command -v mv)"
cat > "$MV_SHIM_DIR/mv" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
marker="$OMI_TEST_MV_BARRIER/$$"
: > "$marker"
for _ in {1..200}; do
  count="$(find "$OMI_TEST_MV_BARRIER" -type f | wc -l | tr -d ' ')"
  [[ "$count" -ge 2 ]] && break
  sleep 0.01
done
exec "$OMI_TEST_REAL_MV" "$@"
SH
chmod +x "$MV_SHIM_DIR/mv"
for process in {1..16}; do
  env PATH="$MV_SHIM_DIR:$PATH" \
    OMI_TEST_MV_BARRIER="$MV_BARRIER" \
    OMI_TEST_REAL_MV="$REAL_MV" \
    OMI_QUALIFICATION_SWIFT_CACHE_ROOT="$CONCURRENT_CACHE" \
    "$CACHE_HELPER" prepare "$SHA_A" "$REPO_A" \
    >"$TMP_ROOT/concurrent-$process.out" 2>"$TMP_ROOT/concurrent-$process.err" &
  concurrent_pids[$process]=$!
done
for process in {1..16}; do
  wait "${concurrent_pids[$process]}" || fail "concurrent prepare $process failed: $(cat "$TMP_ROOT/concurrent-$process.err")"
done
[[ "$(sort -u "$TMP_ROOT"/concurrent-*.out | wc -l | tr -d ' ')" == "1" ]] \
  || fail "concurrent prepares returned different source paths"
[[ "$(grep -hF 'qualification Swift cache MISS' "$TMP_ROOT"/concurrent-*.err | wc -l | tr -d ' ')" == "1" ]] \
  || fail "concurrent publication must have exactly one MISS"
[[ "$(grep -hF 'qualification Swift cache HIT' "$TMP_ROOT"/concurrent-*.err | wc -l | tr -d ' ')" == "15" ]] \
  || fail "concurrent publication must make every other caller a HIT"
[[ -z "$(find "$CONCURRENT_CACHE/$SHA_A" -mindepth 1 -maxdepth 1 -name ".${SHA_A}.prepare.*" -print)" ]] \
  || fail "concurrent publication nested a prepare clone inside the final entry"

mkdir -p "$TMP_ROOT/symlink-ancestor-target"
ln -s "$TMP_ROOT/symlink-ancestor-target" "$TMP_ROOT/symlink-ancestor"
expect_rejected symlink-ancestor "refusing symlinked cache path component" \
  env OMI_QUALIFICATION_SWIFT_CACHE_ROOT="$TMP_ROOT/symlink-ancestor/cache" \
  "$CACHE_HELPER" prepare "$SHA_A" "$REPO_A"

first_source="$($CACHE_HELPER prepare "$SHA_A" "$REPO_A")"
expected_source="$OMI_QUALIFICATION_SWIFT_CACHE_ROOT/$SHA_A/source"
[[ "$first_source" == "$expected_source" ]] || fail "prepare must return the stable exact-SHA source path"
[[ -d "$first_source/desktop/macos/Desktop/.build" ]] || fail "prepare must create a direct persistent SwiftPM build path"
[[ ! -L "$first_source" && ! -L "$first_source/desktop/macos/Desktop/.build" ]] \
  || fail "persistent source and build paths must not be symlinks"
[[ "$(fixture_git -C "$first_source" rev-parse HEAD)" == "$SHA_A" ]] || fail "persistent source is not the requested SHA"
printf 'compiled-output\n' > "$first_source/desktop/macos/Desktop/.build/probe.o"
printf 'remove-me\n' > "$first_source/untrusted-untracked-file"

retry_source="$($CACHE_HELPER prepare "$SHA_A" "$REPO_A_OTHER_PATH")"
[[ "$retry_source" == "$first_source" ]] || fail "caller checkout paths must not affect the persistent source path"
[[ "$(cat "$retry_source/desktop/macos/Desktop/.build/probe.o")" == "compiled-output" ]] \
  || fail "same-SHA retry did not retain direct SwiftPM output"
[[ ! -e "$retry_source/untrusted-untracked-file" ]] || fail "same-SHA reuse retained an untrusted untracked source"

# A dirty tracked source cannot be trusted even if HEAD still names the exact SHA.
printf '%s\n' '// stale package' > "$first_source/desktop/macos/Desktop/Package.swift"
expect_rejected stale-package "persistent source has tracked changes" \
  "$CACHE_HELPER" prepare "$SHA_A" "$REPO_A"
fixture_git -C "$first_source" restore desktop/macos/Desktop/Package.swift

MANIFEST="$OMI_QUALIFICATION_SWIFT_CACHE_ROOT/$SHA_A/manifest.json"
cp "$MANIFEST" "$TMP_ROOT/manifest.good"
python3 - "$MANIFEST" <<'PY'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))
data["source_sha"] = "b" * 40
open(p, "w", encoding="utf-8").write(json.dumps(data, indent=2, sort_keys=True) + "\n")
PY
expect_rejected wrong-sha "cache provenance mismatch" \
  "$CACHE_HELPER" prepare "$SHA_A" "$REPO_A"
cp "$TMP_ROOT/manifest.good" "$MANIFEST"

for field in package_swift_sha256 package_resolved_sha256 xcode swift macos architecture; do
  cp "$TMP_ROOT/manifest.good" "$MANIFEST"
  python3 - "$MANIFEST" "$field" <<'PY'
import json, sys
p, field = sys.argv[1:]
data = json.load(open(p, encoding="utf-8"))
data[field] = "stale"
open(p, "w", encoding="utf-8").write(json.dumps(data, indent=2, sort_keys=True) + "\n")
PY
  expect_rejected "stale-$field" "cache provenance mismatch" \
    "$CACHE_HELPER" prepare "$SHA_A" "$REPO_A"
done
cp "$TMP_ROOT/manifest.good" "$MANIFEST"

for variable in XCODE SWIFT MACOS ARCH; do
  expect_rejected "changed-$variable" "cache provenance mismatch" \
    env "OMI_QUALIFICATION_SWIFT_CACHE_${variable}=different-host-identity" \
    "$CACHE_HELPER" prepare "$SHA_A" "$REPO_A"
done

: > "$OMI_QUALIFICATION_SWIFT_CACHE_ROOT/$SHA_A/complete"
expect_rejected incomplete "incomplete exact-SHA cache entry" \
  "$CACHE_HELPER" prepare "$SHA_A" "$REPO_A"
printf '%s\n' complete > "$OMI_QUALIFICATION_SWIFT_CACHE_ROOT/$SHA_A/complete"

cp -R "$OMI_QUALIFICATION_SWIFT_CACHE_ROOT/$SHA_A" "$OMI_QUALIFICATION_SWIFT_CACHE_ROOT/$SHA_B"
expect_rejected wrong-source "persistent source SHA $SHA_A does not match candidate $SHA_B" \
  "$CACHE_HELPER" prepare "$SHA_B" "$REPO_A"
rm -rf "$OMI_QUALIFICATION_SWIFT_CACHE_ROOT/$SHA_B"

mkdir -p "$TMP_ROOT/symlink-target"
ln -s "$TMP_ROOT/symlink-target" "$OMI_QUALIFICATION_SWIFT_CACHE_ROOT/$SHA_B"
expect_rejected symlink "refusing symlinked exact-SHA cache entry" \
  "$CACHE_HELPER" prepare "$SHA_B" "$REPO_A"

SHA_C="cccccccccccccccccccccccccccccccccccccccc"
printf collision > "$OMI_QUALIFICATION_SWIFT_CACHE_ROOT/$SHA_C"
expect_rejected collision "exact-SHA cache destination collision" \
  "$CACHE_HELPER" prepare "$SHA_C" "$REPO_A"

echo "qualification Swift cache tests passed"
