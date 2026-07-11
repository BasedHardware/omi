#!/usr/bin/env bash
# Run the checked-in pre-push hook manually without pushing.
#
# Usage:
#   .github/scripts/run-pre-push.sh          # vs origin/main
#   .github/scripts/run-pre-push.sh upstream # vs upstream/main

set -euo pipefail

cd "$(dirname "$0")/../.."

REMOTE="${1:-origin}"
exec scripts/pre-push-singleflight "$REMOTE"
