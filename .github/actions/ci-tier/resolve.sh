#!/usr/bin/env bash
set -euo pipefail

full_ci=false
if [[ "${EVENT_NAME:-}" != pull_request ]]; then
  full_ci=true
elif [[ -n "${REPO:-}" && "${HEAD_REPO:-}" == "$REPO" ]]; then
  full_ci=true
elif [[ -z "${REPO:-}" || -z "${PR_NUMBER:-}" || -z "${GH_TOKEN:-}" ]]; then
  echo 'CI tier: missing fork PR lookup context; full CI remains disabled.' >&2
else
  # A re-run keeps the original event payload. Read the PR's current labels
  # once so "add ci:full, then Re-run all jobs" works without label events.
  if labels="$(gh api --method GET "repos/$REPO/issues/$PR_NUMBER/labels" --jq '.[].name')"; then
    if grep -Fxq 'ci:full' <<<"$labels"; then
      full_ci=true
    fi
  else
    echo 'CI tier: current labels could not be read; full CI remains disabled.' >&2
  fi
fi
printf 'full_ci=%s\n' "$full_ci" >> "$GITHUB_OUTPUT"
echo "CI tier: full_ci=$full_ci"
