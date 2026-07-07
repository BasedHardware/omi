# shellcheck shell=bash
# Per-worktree dev isolation — source this (don't execute it).
#
# Multiple agents/worktrees building the macOS app used to collide: they all grabbed
# the same ports (Python 8080, Rust 10201, automation 47777), the same bundle name
# ("Omi Dev"), and run.sh killed *every* backend by process name. This derives a
# stable, unique "instance" from the current git worktree so each one gets its own
# ports, its own bundle, and its own pidfile — zero cross-talk, automatically.
#
# Exports (an explicit override always wins — set any of these to opt out):
#   OMI_INSTANCE      stable id (git worktree basename)
#   RUST_PORT         desktop Rust backend port   (10201 + offset)
#   PYTHON_PORT       local Python backend port   (8080  + offset)
#   AUTOMATION_PORT   in-app automation bridge     (47777 + offset)
#   OMI_APP_NAME      named bundle                 (omi-<instance>)
#   OMI_DEV_DIR       per-instance pidfile/scratch dir (<worktree>/.dev)
#
# The PRIMARY worktree (a normal `git clone`, not a linked `git worktree add`) keeps
# the historical defaults — offset 0, app name "Omi Dev" — so the main checkout is
# unchanged. Only linked worktrees get isolated values.

_omi_wt="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Linked worktree iff its top-level `.git` is a FILE (a gitdir pointer); the primary
# checkout's `.git` is a directory. Robust regardless of the current subdirectory
# (comparing `git rev-parse --git-dir` vs `--git-common-dir` is NOT — they can return
# different absolute/relative formats from a subdir and give a false positive).
_omi_linked=0
# `if`, not `[ -f ] && …` — the latter returns non-zero when false and would trip a
# caller's `set -e` (run.sh has it) on the primary checkout, aborting it instantly.
if [ -f "$_omi_wt/.git" ]; then _omi_linked=1; fi

: "${OMI_INSTANCE:=$(basename "$_omi_wt")}"

if [ "$_omi_linked" = "1" ]; then
  # Deterministic offset in [1,199] from the instance name (stable across runs/machines).
  # +1 so a linked worktree never lands on the primary's offset-0 ports.
  _omi_off=$(printf '%s' "$OMI_INSTANCE" | cksum | awk '{print ($1 % 199) + 1}')
  : "${OMI_APP_NAME:=omi-$OMI_INSTANCE}"
else
  _omi_off=0
  : "${OMI_APP_NAME:=Omi Dev}"
fi

: "${RUST_PORT:=$((10201 + _omi_off))}"
: "${PYTHON_PORT:=$((8080 + _omi_off))}"
: "${AUTOMATION_PORT:=${OMI_AUTOMATION_PORT:-$((47777 + _omi_off))}}"

OMI_DEV_DIR="$_omi_wt/.dev"
mkdir -p "$OMI_DEV_DIR" 2>/dev/null || true

export OMI_INSTANCE RUST_PORT PYTHON_PORT AUTOMATION_PORT OMI_APP_NAME OMI_DEV_DIR
