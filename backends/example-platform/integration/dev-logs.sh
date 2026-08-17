#!/bin/bash
# Read the agent-inspectable runtime JSONL logs. Does not require a running stack.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bun "$HERE/dev-logs.ts" "$@"
