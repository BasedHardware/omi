#!/usr/bin/env bash
# Omi App — Test Runner
# Usage:
#   bash app/scripts/test.sh              # Run unit + widget tests
#   bash app/scripts/test.sh --e2e        # Run Maestro E2E functional tests
#   bash app/scripts/test.sh --e2e --tags all  # Run all E2E tests (incl. device-required)
#   bash app/scripts/test.sh --all        # Run everything

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RUN_UNIT=false
RUN_E2E=false
E2E_ARGS=()

# Parse args
if [[ $# -eq 0 ]]; then
    RUN_UNIT=true
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --e2e)   RUN_E2E=true; shift ;;
        --all)   RUN_UNIT=true; RUN_E2E=true; shift ;;
        --tags)  E2E_ARGS+=(--tags "$2"); shift 2 ;;
        --device-id) E2E_ARGS+=(--device-id "$2"); shift 2 ;;
        *)       E2E_ARGS+=("$1"); shift ;;
    esac
done

# Run unit/widget tests
if $RUN_UNIT; then
    echo "🧪 Running unit & widget tests..."
    cd "$APP_DIR"
    flutter test
    echo ""
fi

# Run E2E functional tests
if $RUN_E2E; then
    echo "🎭 Running Maestro E2E functional tests..."
    bash "$APP_DIR/.maestro/scripts/run_all.sh" "${E2E_ARGS[@]}"
fi
