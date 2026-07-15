#!/usr/bin/env bash
set -euo pipefail

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

echo "pre-push final-PR-diff selection tests passed"
