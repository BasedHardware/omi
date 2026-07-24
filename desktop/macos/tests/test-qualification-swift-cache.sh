#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_HELPER="$SCRIPT_DIR/../scripts/qualification-swift-cache.sh"
# Pre-push hooks can export repository-local Git variables. This fixture creates
# independent repositories and must never reinitialize the caller's worktree.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
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

make_repo() {
  local path="$1"
  mkdir -p "$path/desktop/macos/Desktop"
  printf '%s\n' '// package-a' > "$path/desktop/macos/Desktop/Package.swift"
  printf '%s\n' '{"pins":[]}' > "$path/desktop/macos/Desktop/Package.resolved"
  git -C "$path" init -q
  git -C "$path" config user.email cache-test@omi.invalid
  git -C "$path" config user.name 'Cache Test'
  git -C "$path" config core.hooksPath /dev/null
  git -C "$path" add desktop/macos/Desktop/Package.swift desktop/macos/Desktop/Package.resolved
  git -C "$path" commit -qm 'fixture'
}

export OMI_QUALIFICATION_SWIFT_CACHE_ROOT="$TMP_ROOT/cache"
export OMI_QUALIFICATION_SWIFT_CACHE_XCODE="Xcode 16.4\nBuild version 16F6"
export OMI_QUALIFICATION_SWIFT_CACHE_SWIFT="Apple Swift version 6.1"
export OMI_QUALIFICATION_SWIFT_CACHE_MACOS="15.5 (24F74)"
export OMI_QUALIFICATION_SWIFT_CACHE_ARCH="arm64"

REPO_A="$TMP_ROOT/repo-a"
REPO_A_OTHER_PATH="$TMP_ROOT/repo-a-other-path"
make_repo "$REPO_A"
cp -R "$REPO_A" "$REPO_A_OTHER_PATH"
SHA_A="$(git -C "$REPO_A" rev-parse HEAD)"
SHA_B="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

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
[[ "$(git -C "$first_source" rev-parse HEAD)" == "$SHA_A" ]] || fail "persistent source is not the requested SHA"
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
git -C "$first_source" restore desktop/macos/Desktop/Package.swift

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
