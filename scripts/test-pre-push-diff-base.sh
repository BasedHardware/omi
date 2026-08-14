#!/usr/bin/env bash
set -euo pipefail

# Git hooks export their own repository environment. This fixture creates a
# separate temporary repository, so it must not inherit that hook context.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="$ROOT/scripts/pre-push-diff-base"
TMPDIR="$(mktemp -d)"
cleanup() { rm -rf "$TMPDIR"; }
trap cleanup EXIT

git -C "$TMPDIR" init -q
git -C "$TMPDIR" config user.email test@example.com
git -C "$TMPDIR" config user.name test
printf 'base\n' >"$TMPDIR/base.txt"
git -C "$TMPDIR" add base.txt
git -C "$TMPDIR" commit -qm base
git -C "$TMPDIR" branch -M main
printf 'main\n' >"$TMPDIR/main.txt"
git -C "$TMPDIR" add main.txt
git -C "$TMPDIR" commit -qm main
git -C "$TMPDIR" branch feature HEAD~1
git -C "$TMPDIR" switch -q feature
printf 'desktop\n' >"$TMPDIR/desktop.txt"
git -C "$TMPDIR" add desktop.txt
git -C "$TMPDIR" commit -qm desktop
git -C "$TMPDIR" merge -q --no-edit main

base="$(cd "$TMPDIR" && "$HELPER" main HEAD)"
selected="$(git -C "$TMPDIR" diff --name-only "$base" HEAD)"
test "$selected" = "desktop.txt"
test "$(cd "$TMPDIR" && "$HELPER" "$(git rev-parse main)" "$(git rev-parse HEAD)")" = "$base"

preflight_repo="$TMPDIR/preflight-repo"
preflight_marker="$TMPDIR/pr-preflight-called"
mkdir -p \
  "$preflight_repo/scripts" \
  "$preflight_repo/.github/scripts" \
  "$preflight_repo/backend/scripts" \
  "$preflight_repo/desktop/macos/scripts"
cp "$ROOT/scripts/pre-push" "$preflight_repo/scripts/pre-push"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' >"$preflight_repo/scripts/changed-files"
printf '%s\n' '#!/usr/bin/env python3' 'raise SystemExit(0)' >"$preflight_repo/scripts/pre_push_ci_prediction.py"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  ': "${PREFLIGHT_MARKER:?}"' \
  'printf called >"$PREFLIGHT_MARKER"' \
  >"$preflight_repo/scripts/pr-preflight"
printf '%s\n' '#!/usr/bin/env python3' 'raise SystemExit(0)' \
  >"$preflight_repo/.github/scripts/check-desktop-prod-promotion-policy.py"
printf '%s\n' '#!/usr/bin/env python3' 'raise SystemExit(0)' \
  >"$preflight_repo/.github/scripts/check-deployment-concurrency.py"
printf '%s\n' '#!/usr/bin/env bash' 'exit 1' >"$preflight_repo/backend/scripts/needs-typecheck.sh"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' \
  >"$preflight_repo/desktop/macos/scripts/check-gauntlet-evidence-at-head.sh"
chmod +x \
  "$preflight_repo/scripts/pre-push" \
  "$preflight_repo/scripts/changed-files" \
  "$preflight_repo/scripts/pr-preflight" \
  "$preflight_repo/backend/scripts/needs-typecheck.sh" \
  "$preflight_repo/desktop/macos/scripts/check-gauntlet-evidence-at-head.sh"

git -C "$preflight_repo" init -q
git -C "$preflight_repo" config user.email test@example.com
git -C "$preflight_repo" config user.name test
git -C "$preflight_repo" add .
git -C "$preflight_repo" commit -qm base
git -C "$preflight_repo" update-ref refs/remotes/origin/main HEAD

preflight_output="$(
  cd "$preflight_repo"
  PRE_PUSH_BASE_REMOTE=origin \
    PRE_PUSH_BASE_BRANCH=main \
    PRE_PUSH_SKIP_PR_PREFLIGHT=1 \
    PREFLIGHT_MARKER="$preflight_marker" \
    scripts/pre-push </dev/null
)"
if [ ! -f "$preflight_marker" ]; then
  echo "FAIL: retired PRE_PUSH_SKIP_PR_PREFLIGHT still bypasses shared preflight" >&2
  exit 1
fi
case "$preflight_output" in
  *"Skipping shared PR preflight"*)
    echo "FAIL: retired PRE_PUSH_SKIP_PR_PREFLIGHT still bypasses shared preflight" >&2
    exit 1
    ;;
esac

echo "pre-push final-PR-diff and mandatory PR preflight tests passed"
