#!/usr/bin/env bash

set -euo pipefail

REMOTE="${SETUP_REMOTE:-origin}"
BRANCH="${SETUP_MAIN_BRANCH:-main}"
REMOTE_BRANCH="${REMOTE}/${BRANCH}"
LOCAL_REF="refs/heads/${BRANCH}"
REMOTE_REF="refs/remotes/${REMOTE}/${BRANCH}"

echo "Fetching ${REMOTE_BRANCH}..."
git fetch "$REMOTE" "$BRANCH"

if ! git rev-parse --verify "$REMOTE_REF" >/dev/null 2>&1; then
  echo "FAIL: fetched ${REMOTE_BRANCH}, but ${REMOTE_REF} is unavailable." >&2
  exit 1
fi

current_branch="$(git symbolic-ref --short -q HEAD || true)"
remote_oid="$(git rev-parse "$REMOTE_REF")"

sync_current_worktree_branch() {
  if [ -z "$current_branch" ] || [ "$current_branch" = "$BRANCH" ]; then
    return 0
  fi

  local head_oid
  head_oid="$(git rev-parse HEAD)"

  if [ "$head_oid" = "$remote_oid" ]; then
    echo "Current branch ${current_branch} already matches ${REMOTE_BRANCH}."
    return 0
  fi

  if git merge-base --is-ancestor "$head_oid" "$remote_oid"; then
    echo "Fast-forwarding current branch ${current_branch} to ${REMOTE_BRANCH}..."
    git merge --ff-only "$REMOTE_REF"
    return 0
  fi

  echo "Current branch ${current_branch} is not a fast-forward behind ${REMOTE_BRANCH}; left unchanged." >&2
}

if ! git show-ref --verify --quiet "$LOCAL_REF"; then
  git branch "$BRANCH" "$REMOTE_REF"
  echo "Created local ${BRANCH} from ${REMOTE_BRANCH}."
  sync_current_worktree_branch
  exit 0
fi

local_oid="$(git rev-parse "$LOCAL_REF")"

if [ "$local_oid" = "$remote_oid" ]; then
  echo "Local ${BRANCH} already matches ${REMOTE_BRANCH}."
  sync_current_worktree_branch
  exit 0
fi

if ! git merge-base --is-ancestor "$local_oid" "$remote_oid"; then
  echo "Fetched ${REMOTE_BRANCH}; local ${BRANCH} is not a fast-forward, so it was left unchanged." >&2
  sync_current_worktree_branch
  exit 0
fi

if [ "$current_branch" = "$BRANCH" ]; then
  echo "Fast-forwarding current ${BRANCH} branch..."
  git pull --ff-only "$REMOTE" "$BRANCH"
  exit 0
fi

branch_error_file="$(mktemp "${TMPDIR:-/tmp}/omi-setup-refresh-main.XXXXXX")"
trap 'rm -f "$branch_error_file"' EXIT

if git branch --force "$BRANCH" "$REMOTE_REF" >/dev/null 2>"$branch_error_file"; then
  echo "Fast-forwarded local ${BRANCH} to ${REMOTE_BRANCH}."
else
  branch_error="$(cat "$branch_error_file")"
  if [[ "$branch_error" == *"checked out"* || "$branch_error" == *"used by worktree"* ]]; then
    echo "Fetched ${REMOTE_BRANCH}; local ${BRANCH} is checked out in another worktree, so it was left unchanged." >&2
  else
    echo "$branch_error" >&2
    exit 1
  fi
fi

sync_current_worktree_branch
