#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OMI_MAIN="$SCRIPT_DIR/../scripts/omi-main"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ORIGIN="$TMP_DIR/origin.git"
SOURCE="$TMP_DIR/source"
WORKTREE="$TMP_DIR/omi-main-worktree"
STATE="$TMP_DIR/state"
RUN_LOG="$TMP_DIR/run.log"

git init --bare --initial-branch=main "$ORIGIN" >/dev/null
git init --initial-branch=main "$SOURCE" >/dev/null
git -C "$SOURCE" config user.name test
git -C "$SOURCE" config user.email test@example.com
git -C "$SOURCE" remote add origin "$ORIGIN"
mkdir -p "$SOURCE/desktop/macos"
cat > "$SOURCE/desktop/macos/run.sh" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
printf '%s %s\n' "$OMI_APP_NAME" "$*" >> "$OMI_MAIN_TEST_RUN_LOG"
RUN
chmod +x "$SOURCE/desktop/macos/run.sh"
git -C "$SOURCE" add desktop/macos/run.sh
git -C "$SOURCE" commit -m initial >/dev/null
git -C "$SOURCE" push -u origin main >/dev/null

export OMI_MAIN_REPOSITORY="$SOURCE"
export OMI_MAIN_WORKTREE="$WORKTREE"
export OMI_MAIN_STATE_DIR="$STATE"
export OMI_MAIN_TEST_RUN_LOG="$RUN_LOG"

"$OMI_MAIN" install
FIRST_SHA=$(git -C "$SOURCE" rev-parse HEAD)
test "$(cat "$STATE/installed-sha")" = "$FIRST_SHA"
grep -q '^omi-main --yolo$' "$RUN_LOG"

printf 'next\n' > "$SOURCE/next.txt"
git -C "$SOURCE" add next.txt
git -C "$SOURCE" commit -m next >/dev/null
git -C "$SOURCE" push origin main >/dev/null
SECOND_SHA=$(git -C "$SOURCE" rev-parse HEAD)

"$OMI_MAIN" update
test "$(cat "$STATE/installed-sha")" = "$SECOND_SHA"
test "$(git -C "$WORKTREE" rev-parse HEAD)" = "$SECOND_SHA"
"$OMI_MAIN" status | grep -q 'update:    current'

echo "omi-main test passed"
