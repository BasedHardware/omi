#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OMI_DEV="$SCRIPT_DIR/../scripts/omi-dev"
OMI_MAIN="$SCRIPT_DIR/../scripts/omi-main"
# The aggregate pre-push runner exports these for its own repository. The fixture
# below creates independent repositories, so inheriting them would reinitialize
# the caller's worktree instead of the temporary source repository.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-dev-test.XXXXXX")"
trap 'rm -rf "$TEST_ROOT"' EXIT

ORIGIN="$TEST_ROOT/origin.git"
SOURCE="$TEST_ROOT/source"
WORKTREE_ROOT="$TEST_ROOT/worktrees"
STATE_ROOT="$TEST_ROOT/state"
RUN_LOG="$TEST_ROOT/run.log"

git init --bare --initial-branch=main "$ORIGIN" >/dev/null
git init --initial-branch=main "$SOURCE" >/dev/null
git -C "$SOURCE" config user.name test
git -C "$SOURCE" config user.email test@example.com
git -C "$SOURCE" remote add origin "$ORIGIN"
mkdir -p "$SOURCE/desktop/macos"
cat > "$SOURCE/desktop/macos/run.sh" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
printf '%s %s\n' "$OMI_APP_NAME" "$*" >> "$OMI_DEV_TEST_RUN_LOG"
RUN
chmod +x "$SOURCE/desktop/macos/run.sh"
git -C "$SOURCE" add desktop/macos/run.sh
git -C "$SOURCE" commit -m initial >/dev/null
git -C "$SOURCE" tag v0.0.1-macos
git -C "$SOURCE" push -u origin main --tags >/dev/null
FIRST_SHA="$(git -C "$SOURCE" rev-parse HEAD)"

export OMI_DEV_REPOSITORY="$SOURCE"
export OMI_DEV_WORKTREE_ROOT="$WORKTREE_ROOT"
export OMI_DEV_STATE_ROOT="$STATE_ROOT"
export OMI_DEV_TEST_RUN_LOG="$RUN_LOG"

"$OMI_DEV" install --name omi-alice --ref origin/main
test "$(<"$STATE_ROOT/omi-alice/installed-sha")" = "$FIRST_SHA"
test "$(<"$STATE_ROOT/omi-alice/ref")" = "origin/main"
grep -q '^omi-alice --yolo$' "$RUN_LOG"

printf 'next\n' > "$SOURCE/next.txt"
git -C "$SOURCE" add next.txt
git -C "$SOURCE" commit -m next >/dev/null
git -C "$SOURCE" push origin main >/dev/null
SECOND_SHA="$(git -C "$SOURCE" rev-parse HEAD)"

"$OMI_DEV" update --name omi-alice --ref origin/main
"$OMI_DEV" update --name omi-bob --ref v0.0.1-macos
test "$(<"$STATE_ROOT/omi-alice/installed-sha")" = "$SECOND_SHA"
test "$(<"$STATE_ROOT/omi-bob/installed-sha")" = "$FIRST_SHA"
test "$(git -C "$WORKTREE_ROOT/omi-alice" rev-parse HEAD)" = "$SECOND_SHA"
test "$(git -C "$WORKTREE_ROOT/omi-bob" rev-parse HEAD)" = "$FIRST_SHA"
test "$WORKTREE_ROOT/omi-alice" != "$WORKTREE_ROOT/omi-bob"
test "$STATE_ROOT/omi-alice" != "$STATE_ROOT/omi-bob"
grep -q '^omi-bob --yolo$' "$RUN_LOG"
BOB_STATUS="$("$OMI_DEV" status --name omi-bob)"
grep -Fq 'bundle:    /Applications/omi-bob.app' <<<"$BOB_STATUS"
grep -Fq 'ref:       v0.0.1-macos' <<<"$BOB_STATUS"

if "$OMI_DEV" update --name 'Omi Beta' --ref origin/main >/dev/null 2>&1; then
  echo "expected protected standard bundle name to be rejected" >&2
  exit 1
fi
if grep -Eq '^(omi|Omi|Omi Beta) --yolo$' "$RUN_LOG"; then
  echo "a standard bundle path reached the build command" >&2
  exit 1
fi

export OMI_MAIN_WORKTREE="$TEST_ROOT/legacy-worktree"
export OMI_MAIN_STATE_DIR="$TEST_ROOT/legacy-state"
"$OMI_MAIN" install
test "$(<"$OMI_MAIN_STATE_DIR/installed-sha")" = "$SECOND_SHA"
test -e "$OMI_MAIN_WORKTREE/.git"
grep -q '^omi-main --yolo$' "$RUN_LOG"

echo "omi-dev test passed"
