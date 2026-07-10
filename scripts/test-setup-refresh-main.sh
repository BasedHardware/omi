#!/usr/bin/env bash

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-setup-refresh-main.XXXXXX")"
trap 'rm -rf "$TMPDIR"' EXIT

git init --bare --initial-branch=main "$TMPDIR/remote.git" >/dev/null

git clone "$TMPDIR/remote.git" "$TMPDIR/primary" >/dev/null 2>&1
(
  cd "$TMPDIR/primary"
  git config user.email test@example.com
  git config user.name "Test User"
  echo one >file.txt
  git add file.txt
  git commit -m initial >/dev/null
  git push origin HEAD:main >/dev/null 2>&1
  git branch -M main
  git fetch origin main >/dev/null 2>&1
  git branch --set-upstream-to origin/main main >/dev/null
)

git clone "$TMPDIR/remote.git" "$TMPDIR/updater" >/dev/null 2>&1
(
  cd "$TMPDIR/updater"
  git config user.email test@example.com
  git config user.name "Test User"
  git switch main >/dev/null 2>&1
  echo two >>file.txt
  git commit -am update >/dev/null
  git push origin main >/dev/null 2>&1
)

(
  cd "$TMPDIR/primary"
  git worktree add "$TMPDIR/feature" -b feature >/dev/null 2>&1
)

before="$(git -C "$TMPDIR/primary" rev-parse main)"
output="$(
  cd "$TMPDIR/feature"
  bash "$ROOT/scripts/setup-refresh-main.sh" 2>&1
)"
after="$(git -C "$TMPDIR/primary" rev-parse main)"
remote_after="$(git -C "$TMPDIR/feature" rev-parse origin/main)"

if [ "$before" != "$after" ]; then
  echo "FAIL: local main changed while checked out in another worktree." >&2
  exit 1
fi

if ! git -C "$TMPDIR/feature" merge-base --is-ancestor "$before" "$remote_after"; then
  echo "FAIL: origin/main was not refreshed." >&2
  exit 1
fi

case "$output" in
  *"checked out in another worktree"*) ;;
  *)
    echo "FAIL: expected checked-out worktree message." >&2
    echo "$output" >&2
    exit 1
    ;;
esac

echo "setup-refresh-main test passed."

git init --bare --initial-branch=main "$TMPDIR/diverged-remote.git" >/dev/null

git clone "$TMPDIR/diverged-remote.git" "$TMPDIR/diverged-primary" >/dev/null 2>&1
(
  cd "$TMPDIR/diverged-primary"
  git config user.email test@example.com
  git config user.name "Test User"
  echo one >file.txt
  git add file.txt
  git commit -m initial >/dev/null
  git push origin main >/dev/null 2>&1
)

git clone "$TMPDIR/diverged-remote.git" "$TMPDIR/diverged-updater" >/dev/null 2>&1
(
  cd "$TMPDIR/diverged-updater"
  git config user.email test@example.com
  git config user.name "Test User"
  echo remote >>file.txt
  git commit -am remote-update >/dev/null
  git push origin main >/dev/null 2>&1
)

(
  cd "$TMPDIR/diverged-primary"
  echo local >>file.txt
  git commit -am local-update >/dev/null
)

diverged_before="$(git -C "$TMPDIR/diverged-primary" rev-parse main)"
diverged_output="$(
  cd "$TMPDIR/diverged-primary"
  bash "$ROOT/scripts/setup-refresh-main.sh" 2>&1
)"
diverged_after="$(git -C "$TMPDIR/diverged-primary" rev-parse main)"

if [ "$diverged_before" != "$diverged_after" ]; then
  echo "FAIL: diverged current main changed." >&2
  exit 1
fi

case "$diverged_output" in
  *"not a fast-forward"*) ;;
  *)
    echo "FAIL: expected non-fast-forward message." >&2
    echo "$diverged_output" >&2
    exit 1
    ;;
esac

echo "setup-refresh-main diverged-current-main test passed."
