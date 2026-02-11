#!/usr/bin/env bash
set -euo pipefail

# Run all Maestro E2E functional tests (excluding device-dependent flows)
#
# Usage:
#   bash .maestro/scripts/run_all.sh [--report]
#
# Prerequisites:
#   - Maestro CLI installed: brew install maestro
#   - App built and installed on device/simulator
#   - Device/simulator is running
#
# Options:
#   --report    Generate HTML report in .maestro/report/

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAESTRO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORT_DIR="$MAESTRO_DIR/report"

GENERATE_REPORT=false
REPORT_FLAGS=""
for arg in "$@"; do
  if [[ "$arg" == "--report" ]]; then
    GENERATE_REPORT=true
    mkdir -p "$REPORT_DIR"
    REPORT_FLAGS="--format html --output $REPORT_DIR/"
  fi
done

# Check Maestro is installed
if ! command -v maestro &> /dev/null; then
  echo "ERROR: Maestro CLI not found."
  echo "Install with: brew install maestro"
  echo "  or: curl -Ls 'https://get.maestro.mobile.dev' | bash"
  exit 1
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         OMI APP - MAESTRO FUNCTIONAL TESTS                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Running all flows tagged 'core' (excludes device_required)..."
echo ""

# Run all core-tagged flows via Maestro's tag system.
# Flow tags are defined in config.yaml — no hardcoded list needed.
if maestro test "$MAESTRO_DIR" --exclude-tags=device_required $REPORT_FLAGS; then
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  Result: ALL CORE TESTS PASSED                              ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
else
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  Result: SOME TESTS FAILED — see output above               ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  exit 1
fi

if [[ "$GENERATE_REPORT" == "true" ]]; then
  echo ""
  echo "Report saved to: $REPORT_DIR/"
fi
