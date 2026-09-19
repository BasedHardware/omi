#!/usr/bin/env bash
set -euo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/build_provenance_dart_defines.sh"
chmod +x "$SCRIPT"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

parse_defines() {
  local out="$1"
  sha="$(sed -n 's/^--dart-define=OMI_GIT_SHA=//p' "$out")"
  dirty="$(sed -n 's/^--dart-define=OMI_GIT_DIRTY=//p' "$out")"
  build="$(sed -n 's/^--dart-define=OMI_BUILD_NUMBER=//p' "$out")"
}

run_script() {
  env -u BUILD_NUMBER -u OMI_BUILD_NUMBER -u CM_TAG -u CM_BUILD_ID "$@" "$SCRIPT"
}

repo="$(mktemp -d "${TMPDIR:-/tmp}/omi-provenance-git.XXXXXX")"
nogit="$(mktemp -d "${TMPDIR:-/tmp}/omi-provenance-nogit.XXXXXX")"
trap 'rm -rf "$repo" "$nogit"' EXIT

git -C "$repo" init -q
git -C "$repo" config user.name test
git -C "$repo" config user.email test@example.com
git -C "$repo" config commit.gpgsign false
printf 'tracked\n' >"$repo/tracked.txt"
git -C "$repo" add tracked.txt
git -C "$repo" commit -q -m tracked
head_sha="$(git -C "$repo" rev-parse HEAD)"

# Clean tree
out="$(mktemp)"
(
  cd "$repo"
  run_script >"$out"
)
parse_defines "$out"
[[ "$sha" == "$head_sha" ]] || fail "clean tree SHA: got $sha want $head_sha"
[[ "$dirty" == "false" ]] || fail "clean tree should not be dirty"
[[ "$build" == "local" ]] || fail "clean tree default build: got $build"

# Untracked file only — must not mark dirty (Codemagic writes untracked files)
printf 'scratch\n' >"$repo/untracked.txt"
(
  cd "$repo"
  run_script >"$out"
)
parse_defines "$out"
[[ "$dirty" == "false" ]] || fail "untracked-only tree was marked dirty"
[[ "$sha" == "$head_sha" ]] || fail "untracked-only changed SHA"
rm -f "$repo/untracked.txt"

# Modified tracked file
printf 'changed\n' >"$repo/tracked.txt"
err="$(mktemp)"
(
  cd "$repo"
  run_script >"$out" 2>"$err"
)
parse_defines "$out"
[[ "$dirty" == "true" ]] || fail "modified tracked file was not dirty"
[[ "$sha" == "$head_sha" ]] || fail "dirty tree SHA should stay HEAD, got $sha"
if grep -q 'tracked files differ from HEAD' "$err"; then
  fail "non-Codemagic dirty run printed Codemagic file list"
fi

# Codemagic dirty log names the tracked file
(
  cd "$repo"
  env -u BUILD_NUMBER -u OMI_BUILD_NUMBER -u CM_TAG CM_BUILD_ID=cm-test "$SCRIPT" >"$out" 2>"$err"
)
grep -F 'build provenance: tracked files differ from HEAD:' "$err" >/dev/null \
  || fail "Codemagic dirty run did not print the file-list header"
grep -F 'tracked.txt' "$err" >/dev/null \
  || fail "Codemagic dirty run did not name tracked.txt"
git -C "$repo" checkout -q -- tracked.txt

# BUILD_NUMBER wins
(
  cd "$repo"
  env -u OMI_BUILD_NUMBER -u CM_TAG BUILD_NUMBER=1001 "$SCRIPT" >"$out"
)
parse_defines "$out"
[[ "$build" == "1001" ]] || fail "BUILD_NUMBER: got $build"

# OMI_BUILD_NUMBER when BUILD_NUMBER unset
(
  cd "$repo"
  env -u BUILD_NUMBER -u CM_TAG OMI_BUILD_NUMBER=7 "$SCRIPT" >"$out"
)
parse_defines "$out"
[[ "$build" == "7" ]] || fail "OMI_BUILD_NUMBER: got $build"

# CM_TAG with +N
(
  cd "$repo"
  env -u BUILD_NUMBER -u OMI_BUILD_NUMBER CM_TAG='v1.0.543+992-mobile-cm' "$SCRIPT" >"$out"
)
parse_defines "$out"
[[ "$build" == "992" ]] || fail "CM_TAG +N: got $build"

# CM_TAG without +N falls through to local
(
  cd "$repo"
  env -u BUILD_NUMBER -u OMI_BUILD_NUMBER CM_TAG='v1.0.543-mobile-cm' "$SCRIPT" >"$out"
)
parse_defines "$out"
[[ "$build" == "local" ]] || fail "CM_TAG without +N: got $build want local"

# Whitespace in BUILD_NUMBER fails the build
if (
  cd "$repo"
  env -u OMI_BUILD_NUMBER -u CM_TAG BUILD_NUMBER='9 9' "$SCRIPT" >"$out" 2>"$err"
); then
  fail "accepted BUILD_NUMBER with whitespace"
fi
grep -F "invalid OMI_BUILD_NUMBER='9 9'" "$err" >/dev/null \
  || fail "whitespace BUILD_NUMBER did not fail loudly"

# Not a git repo
(
  cd "$nogit"
  run_script >"$out"
)
parse_defines "$out"
[[ "$sha" == "unknown" ]] || fail "non-git SHA: got $sha"
[[ "$dirty" == "false" ]] || fail "non-git dirty: got $dirty"
[[ "$build" == "local" ]] || fail "non-git build: got $build"

echo 'build_provenance_dart_defines.sh: clean, tracked-dirty, untracked-only, non-git, and build-number sources'
