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
# The directory contains an owner record while held. This lets a later run
# recover an interrupted launcher instead of waiting the full timeout on an
# otherwise indistinguishable empty directory. The process start stamp avoids
# treating a recycled PID as the original lock holder.
#
# Prefer OMI_DEV_DIR (repo-root .dev/). SCRIPT_DIR fallback is for hermetic tests
# only and resolves to $SCRIPT_DIR/.dev — callers that mirror run.sh should source
# scripts/dev-instance.sh first.

if [ -z "${OMI_RUN_SH_LOCK_OWNER_FILE+x}" ]; then
  readonly OMI_RUN_SH_LOCK_OWNER_FILE="owner"
fi
if [ -z "${OMI_RUN_SH_EMPTY_LOCK_GRACE_SECONDS+x}" ]; then
  readonly OMI_RUN_SH_EMPTY_LOCK_GRACE_SECONDS=5
fi

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

omi_run_sh_process_start_stamp() {
  local pid="$1"
  ps -o lstart= -p "$pid" 2>/dev/null | awk '{$1 = $1; print}'
}

omi_run_sh_lock_owner_file() {
  printf '%s/%s\n' "$1" "$OMI_RUN_SH_LOCK_OWNER_FILE"
}

omi_run_sh_lock_dir_mtime() {
  local lock_dir="$1"
  if [ "$(uname -s)" = "Darwin" ]; then
    stat -f '%m' "$lock_dir"
  else
    stat -c '%Y' "$lock_dir"
  fi
}

# Returns success only when no live process owns the lock. A just-created
# ownerless directory gets a small grace window so a concurrent contender
# cannot delete it between mkdir and the owner-file write.
omi_run_sh_build_lock_is_stale() {
  local lock_dir="$1"
  local owner_file owner_pid owner_start current_start lock_mtime now

  owner_file="$(omi_run_sh_lock_owner_file "$lock_dir")"
  if [ ! -f "$owner_file" ]; then
    lock_mtime="$(omi_run_sh_lock_dir_mtime "$lock_dir" 2>/dev/null || true)"
    now="$(date +%s)"
    [ -n "$lock_mtime" ] && [ $((now - lock_mtime)) -ge "$OMI_RUN_SH_EMPTY_LOCK_GRACE_SECONDS" ]
    return
  fi

  IFS=$'\t' read -r owner_pid owner_start < "$owner_file" || true
  [[ "$owner_pid" =~ ^[0-9]+$ ]] || return 0
  if [ -z "$owner_start" ] || ! kill -0 "$owner_pid" 2>/dev/null; then
    return 0
  fi

  current_start="$(omi_run_sh_process_start_stamp "$owner_pid")"
  [ -n "$current_start" ] && [ "$current_start" = "$owner_start" ] && return 1
  return 0
}

omi_run_sh_recover_stale_build_lock() {
  local lock_dir="$1"
  local owner_file

  omi_run_sh_build_lock_is_stale "$lock_dir" || return 1
  owner_file="$(omi_run_sh_lock_owner_file "$lock_dir")"
  rm -f "$owner_file" 2>/dev/null || true
  if rmdir "$lock_dir" 2>/dev/null; then
    echo "Recovered stale ./run.sh build lock ($lock_dir)." >&2
    return 0
  fi
  return 1
}

omi_run_sh_release_build_lock() {
  local owner_file owner_pid owner_start current_start

  [ -n "${RUN_SH_LOCK_DIR:-}" ] || return 0
  owner_file="$(omi_run_sh_lock_owner_file "$RUN_SH_LOCK_DIR")"
  if [ -f "$owner_file" ]; then
    IFS=$'\t' read -r owner_pid owner_start < "$owner_file" || true
    current_start="$(omi_run_sh_process_start_stamp "$$")"
    if [ "$owner_pid" != "$$" ] || [ -z "$owner_start" ] || [ "$owner_start" != "$current_start" ]; then
      return 0
    fi
  fi
  rm -f "$owner_file" 2>/dev/null || true
  rmdir "$RUN_SH_LOCK_DIR" 2>/dev/null || true
}

# Acquire the per-worktree build lock. Optional args:
#   $1 = label printed while waiting (default: another ./run.sh in this worktree)
#   $2 = timeout seconds (default: 600)
omi_run_sh_acquire_build_lock() {
  local wait_label="${1:-another ./run.sh in this worktree}"
  local timeout_secs="${2:-600}"
  local waited=0
  local now total_elapsed owner_file owner_start

  RUN_SH_LOCK_DIR="$(omi_run_sh_build_lock_dir)" || return 1
  export RUN_SH_LOCK_DIR

  while ! mkdir "$RUN_SH_LOCK_DIR" 2>/dev/null; do
    omi_run_sh_recover_stale_build_lock "$RUN_SH_LOCK_DIR" && continue
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
  owner_file="$(omi_run_sh_lock_owner_file "$RUN_SH_LOCK_DIR")"
  owner_start="$(omi_run_sh_process_start_stamp "$$")"
  printf '%s\t%s\n' "$$" "$owner_start" > "$owner_file"
  return 0
}
