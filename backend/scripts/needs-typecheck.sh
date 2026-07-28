#!/usr/bin/env bash
# Return success when a changed path requires the backend Pyright boundary.
set -euo pipefail

usage() {
  echo "usage: $0 [changed-files-list]" >&2
  exit 2
}

if [ "$#" -gt 1 ]; then
  usage
fi

input="${1:--}"
if [ "$input" != "-" ] && [ ! -f "$input" ]; then
  usage
fi
if [ "$input" = "-" ]; then
  input=/dev/stdin
fi

while IFS= read -r path || [ -n "$path" ]; do
  case "$path" in
    backend/*.py|backend/pyrightconfig.json|backend/scripts/typecheck.sh|backend/scripts/needs-typecheck.sh|backend/requirements.txt|backend/pylock*.toml|.github/workflows/backend-unit-tests.yml|scripts/pre-push)
      exit 0
      ;;
  esac
done < "$input"

exit 1
