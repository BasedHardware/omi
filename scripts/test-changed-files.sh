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
base_sha="$(git -C "$TMPDIR" rev-parse HEAD)"
git -C "$TMPDIR" branch -M main

git -C "$TMPDIR" switch -q -c feature
printf 'feature\n' >"$TMPDIR/feature.txt"
git -C "$TMPDIR" add feature.txt
git -C "$TMPDIR" commit -qm feature
git -C "$TMPDIR" switch -q main

# Simulate main advancing after the pull request's event base SHA, then let
# GitHub create the synthetic merge with main as its first parent.
printf 'main\n' >"$TMPDIR/main.txt"
git -C "$TMPDIR" add main.txt
git -C "$TMPDIR" commit -qm main
git -C "$TMPDIR" merge --no-ff -q --no-edit feature

changed="$(cd "$TMPDIR" && "$HELPER" "$base_sha...HEAD")"
test "$changed" = "feature.txt"

non_merge_changed="$(cd "$TMPDIR" && "$HELPER" "$base_sha...feature")"
test "$non_merge_changed" = "feature.txt"

echo "changed-files synthetic-merge test passed"
