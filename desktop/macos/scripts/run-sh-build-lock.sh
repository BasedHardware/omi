#!/usr/bin/env bash
# shellcheck shell=bash
# Per-worktree ./run.sh build lock — source this (don't execute it).
#
# Invariant:
#   - Scope is ONE git worktree (prefer OMI_DEV_DIR from scripts/dev-instance.sh;
#     never a per-user global mutex).
#   - Hold through build → stage → /Applications install → seed → open.
#   - Release before the long-running backend wait / Ctrl+C loop so other
#     worktrees (and a later rebuild in this worktree) are not blocked by a
#     live session.
#   - Same-worktree concurrent named-bundle builds still serialize: they share
#     Desktop/.build/. Cross-worktree builds must not block each other.
#   - Explicit OMI_APP_NAME overrides that collide across worktrees are unsupported;
#     /Applications/$APP_NAME.app is machine-global and not cross-locked.
#
# Prefer OMI_DEV_DIR (repo-root .dev/). SCRIPT_DIR fallback is for hermetic tests
# only and resolves to $SCRIPT_DIR/.dev — callers that mirror run.sh should source
# scripts/dev-instance.sh first.

omi_run_sh_build_lock_dir() {
  local base="${OMI_DEV_DIR:-}"
  if [ -z "$base" ]; then
    if [ -n "${SCRIPT_DIR:-}" ]; then
      base="$SCRIPT_DIR/.dev"
    else
      echo "ERROR: omi_run_sh_build_lock_dir needs OMI_DEV_DIR or SCRIPT_DIR" >&2
      return 1
    fi
  fi
  mkdir -p "$base" 2>/dev/null || true
  printf '%s\n' "$base/run-sh-build.lock.d"
}

omi_run_sh_release_build_lock() {
  if [ -n "${RUN_SH_LOCK_DIR:-}" ]; then
    rmdir "$RUN_SH_LOCK_DIR" 2>/dev/null || true
  fi
}

# Acquire the per-worktree build lock. Optional args:
#   $1 = label printed while waiting (default: another ./run.sh in this worktree)
#   $2 = timeout seconds (default: 600)
omi_run_sh_acquire_build_lock() {
  local wait_label="${1:-another ./run.sh in this worktree}"
  local timeout_secs="${2:-600}"
  local waited=0
  local now total_elapsed

  RUN_SH_LOCK_DIR="$(omi_run_sh_build_lock_dir)" || return 1
  export RUN_SH_LOCK_DIR

  while ! mkdir "$RUN_SH_LOCK_DIR" 2>/dev/null; do
    if [ "$waited" -eq 0 ]; then
      if [ -n "${SCRIPT_START_TIME:-}" ] && command -v bc >/dev/null 2>&1; then
        now=$(date +%s.%N)
        total_elapsed=$(echo "$now - $SCRIPT_START_TIME" | bc)
        printf "[%6.1fs]   ├─ Waiting for %s...\n" "$total_elapsed" "$wait_label"
      else
        echo "Waiting for $wait_label ($RUN_SH_LOCK_DIR)..."
      fi
    fi
    sleep 2
    waited=$((waited + 2))
    if [ "$waited" -ge "$timeout_secs" ]; then
      echo "ERROR: timed out after ${timeout_secs}s waiting for ./run.sh build lock ($RUN_SH_LOCK_DIR)" >&2
      return 1
    fi
  done
  return 0
}
