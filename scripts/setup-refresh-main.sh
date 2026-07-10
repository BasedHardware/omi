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
if ! git show-ref --verify --quiet "$LOCAL_REF"; then
  git branch "$BRANCH" "$REMOTE_REF"
  echo "Created local ${BRANCH} from ${REMOTE_BRANCH}."
  exit 0
fi

local_oid="$(git rev-parse "$LOCAL_REF")"
remote_oid="$(git rev-parse "$REMOTE_REF")"

if [ "$local_oid" = "$remote_oid" ]; then
  echo "Local ${BRANCH} already matches ${REMOTE_BRANCH}."
  exit 0
fi

if ! git merge-base --is-ancestor "$local_oid" "$remote_oid"; then
  echo "Fetched ${REMOTE_BRANCH}; local ${BRANCH} is not a fast-forward, so it was left unchanged." >&2
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
