#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$MACOS_DIR/scripts/run-sh-build-lock.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_eq() {
  local expected="$1" actual="$2" label="$3"
  if [ "$expected" != "$actual" ]; then
    fail "$label: expected '$expected', got '$actual'"
  fi
}

assert_ne() {
  local left="$1" right="$2" label="$3"
  if [ "$left" = "$right" ]; then
    fail "$label: expected distinct values, both were '$left'"
  fi
}

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-run-sh-lock-test.XXXXXX")"
cleanup() {
  omi_run_sh_release_build_lock || true
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

# Distinct worktrees must get distinct lock dirs (never a per-user global path).
OMI_DEV_DIR="$TMP_ROOT/wt-a/.dev"
lock_a="$(omi_run_sh_build_lock_dir)"
OMI_DEV_DIR="$TMP_ROOT/wt-b/.dev"
lock_b="$(omi_run_sh_build_lock_dir)"
assert_ne "$lock_a" "$lock_b" "per-worktree lock dirs"
case "$lock_a" in
  *"/omi-run-sh-${USER}.lock.d") fail "lock_a still uses legacy per-user global path: $lock_a" ;;
esac
case "$lock_b" in
  *"/omi-run-sh-${USER}.lock.d") fail "lock_b still uses legacy per-user global path: $lock_b" ;;
esac
assert_eq "$TMP_ROOT/wt-a/.dev/run-sh-build.lock.d" "$lock_a" "lock_a path"
assert_eq "$TMP_ROOT/wt-b/.dev/run-sh-build.lock.d" "$lock_b" "lock_b path"

# SCRIPT_DIR fallback when OMI_DEV_DIR is unset.
unset OMI_DEV_DIR
SCRIPT_DIR="$TMP_ROOT/fallback-macos"
lock_fallback="$(omi_run_sh_build_lock_dir)"
assert_eq "$TMP_ROOT/fallback-macos/.dev/run-sh-build.lock.d" "$lock_fallback" "SCRIPT_DIR fallback lock path"

# Acquire in worktree A must not block acquire in worktree B.
OMI_DEV_DIR="$TMP_ROOT/wt-a/.dev"
omi_run_sh_acquire_build_lock "test holder A" 10
held_a="$RUN_SH_LOCK_DIR"
[ -d "$held_a" ] || fail "worktree A lock dir missing after acquire"

OMI_DEV_DIR="$TMP_ROOT/wt-b/.dev"
omi_run_sh_acquire_build_lock "test holder B" 10
held_b="$RUN_SH_LOCK_DIR"
[ -d "$held_b" ] || fail "worktree B lock dir missing after acquire"
assert_ne "$held_a" "$held_b" "concurrent cross-worktree holders"

# Release is idempotent and clears only the current RUN_SH_LOCK_DIR.
omi_run_sh_release_build_lock
[ ! -d "$held_b" ] || fail "worktree B lock dir still present after release"
[ -d "$held_a" ] || fail "worktree A lock dir should remain until its holder releases"

RUN_SH_LOCK_DIR="$held_a"
omi_run_sh_release_build_lock
[ ! -d "$held_a" ] || fail "worktree A lock dir still present after release"
omi_run_sh_release_build_lock # idempotent

# Same-worktree second acquire must wait / time out while the first holds.
OMI_DEV_DIR="$TMP_ROOT/wt-a/.dev"
omi_run_sh_acquire_build_lock "test holder A2" 10
(
  OMI_DEV_DIR="$TMP_ROOT/wt-a/.dev"
  # shellcheck source=/dev/null
  source "$MACOS_DIR/scripts/run-sh-build-lock.sh"
  if omi_run_sh_acquire_build_lock "test contender A2" 4; then
    omi_run_sh_release_build_lock
    exit 0
  fi
  exit 1
) && fail "same-worktree contender should not acquire while lock is held"

omi_run_sh_release_build_lock

echo "run-sh-build-lock tests passed"
