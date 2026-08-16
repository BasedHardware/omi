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
# Basename must be the per-worktree lock dir, not the legacy omi-run-sh-$USER.lock.d.
lock_a_base="$(basename "$lock_a")"
lock_b_base="$(basename "$lock_b")"
assert_eq "run-sh-build.lock.d" "$lock_a_base" "lock_a basename"
assert_eq "run-sh-build.lock.d" "$lock_b_base" "lock_b basename"
assert_eq "$TMP_ROOT/wt-a/.dev/run-sh-build.lock.d" "$lock_a" "lock_a path"
assert_eq "$TMP_ROOT/wt-b/.dev/run-sh-build.lock.d" "$lock_b" "lock_b path"

# SCRIPT_DIR fallback when OMI_DEV_DIR is unset.
unset OMI_DEV_DIR
SCRIPT_DIR="$TMP_ROOT/fallback-macos"
lock_fallback="$(omi_run_sh_build_lock_dir)"
assert_eq "$TMP_ROOT/fallback-macos/.dev/run-sh-build.lock.d" "$lock_fallback" "SCRIPT_DIR fallback lock path"

# Repo-root OMI_DEV_DIR (what run.sh uses after sourcing scripts/dev-instance.sh)
# must not resolve under desktop/macos/.dev.
REPO_ROOT_FAKE="$TMP_ROOT/repo"
mkdir -p "$REPO_ROOT_FAKE"
OMI_DEV_DIR="$REPO_ROOT_FAKE/.dev"
SCRIPT_DIR="$REPO_ROOT_FAKE/desktop/macos"
lock_repo="$(omi_run_sh_build_lock_dir)"
assert_eq "$REPO_ROOT_FAKE/.dev/run-sh-build.lock.d" "$lock_repo" "repo-root OMI_DEV_DIR lock path"
case "$lock_repo" in
  */desktop/macos/.dev/*) fail "lock unexpectedly under desktop/macos/.dev: $lock_repo" ;;
esac

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

# An interrupted launcher leaves a dead owner record. A later build must
# recover it immediately rather than consume the caller's full timeout.
OMI_DEV_DIR="$TMP_ROOT/wt-stale/.dev"
export OMI_DEV_DIR
bash -c '
  # shellcheck source=/dev/null
  source "$1"
  omi_run_sh_acquire_build_lock "interrupted holder" 10
' _ "$MACOS_DIR/scripts/run-sh-build-lock.sh"
stale_lock="$(omi_run_sh_build_lock_dir)"
[ -d "$stale_lock" ] || fail "interrupted holder did not leave its lock"
omi_run_sh_acquire_build_lock "stale lock recovery" 4
[ -d "$RUN_SH_LOCK_DIR" ] || fail "stale lock recovery did not acquire lock"
omi_run_sh_release_build_lock
[ ! -d "$stale_lock" ] || fail "stale lock remained after recovery release"

# A crash before owner-file creation also leaves an empty directory. Once the
# short creation grace window has elapsed, recover it rather than timing out.
OMI_DEV_DIR="$TMP_ROOT/wt-ownerless/.dev"
ownerless_lock="$(omi_run_sh_build_lock_dir)"
mkdir -p "$ownerless_lock"
touch -t 202001010000 "$ownerless_lock"
omi_run_sh_acquire_build_lock "ownerless stale lock recovery" 4
[ -d "$RUN_SH_LOCK_DIR" ] || fail "ownerless stale lock recovery did not acquire lock"
omi_run_sh_release_build_lock
[ ! -d "$ownerless_lock" ] || fail "ownerless stale lock remained after recovery release"

echo "run-sh-build-lock tests passed"
