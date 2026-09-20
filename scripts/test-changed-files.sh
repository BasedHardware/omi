#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HELPER="$ROOT/scripts/changed-files"
TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-changed-files.XXXXXX")"
trap 'rm -rf "$TMPDIR"' EXIT

git -C "$TMPDIR" init -q
git -C "$TMPDIR" config user.email test@example.com
git -C "$TMPDIR" config user.name "Test User"
printf 'base\n' >"$TMPDIR/base.txt"
git -C "$TMPDIR" add base.txt
git -C "$TMPDIR" commit -qm base
git -C "$TMPDIR" branch -M main

git -C "$TMPDIR" switch -q -c feature
printf 'feature\n' >"$TMPDIR/feature.txt"
git -C "$TMPDIR" add feature.txt
git -C "$TMPDIR" commit -qm feature
feature_sha="$(git -C "$TMPDIR" rev-parse HEAD)"

git -C "$TMPDIR" switch -q main
printf 'main\n' >"$TMPDIR/main.txt"
git -C "$TMPDIR" add main.txt
git -C "$TMPDIR" commit -qm main
main_sha="$(git -C "$TMPDIR" rev-parse HEAD)"
stale_base_sha="$(git -C "$TMPDIR" rev-parse HEAD~1)"

files_at() {
  local sha="$1"
  git -C "$TMPDIR" switch -q --detach "$sha"
  (cd "$TMPDIR" && "$HELPER" "main...HEAD")
}

# 1. Branch head: three-dot against live main is the PR files, not main's extra file.
git -C "$TMPDIR" switch -q --detach "$feature_sha"
branch_head="$(files_at "$feature_sha")"
test "$branch_head" = "feature.txt"

# 2. Local merge, branch as first parent.
git -C "$TMPDIR" switch -q --detach "$feature_sha"
git -C "$TMPDIR" merge --no-ff -q --no-edit "$main_sha"
branch_first="$(files_at HEAD)"

# 3. GitHub pull_request merge ref: BASE as first parent.
git -C "$TMPDIR" switch -q --detach "$main_sha"
git -C "$TMPDIR" merge --no-ff -q --no-edit "$feature_sha"
base_first="$(files_at HEAD)"

test "$branch_first" = "feature.txt"
test "$base_first" = "feature.txt"
test "$branch_head" = "$branch_first"
test "$branch_first" = "$base_first"

# A stale left-hand SHA (the event payload base) is not silently rewritten to
# first-parent. Three-dot against it honestly includes main's later commits.
stale="$(cd "$TMPDIR" && "$HELPER" "$stale_base_sha...HEAD")"
printf '%s\n' "$stale" | grep -qx 'feature.txt'
printf '%s\n' "$stale" | grep -qx 'main.txt'

echo "changed-files three-dot parent-order test passed"
