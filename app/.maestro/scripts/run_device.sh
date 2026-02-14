#!/usr/bin/env bash
set -euo pipefail

# Run device-dependent Maestro E2E tests
#
# ⚠️  REQUIRES PHYSICAL OMI DEVICE
# These tests require a physical Omi device powered on and in Bluetooth range.
#
# Usage:
#   bash .maestro/scripts/run_device.sh
#
# Prerequisites:
#   - Maestro CLI installed: brew install maestro
#   - App built and installed on device/simulator
#   - Omi device powered on and in Bluetooth range
#   - Bluetooth enabled on test device

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAESTRO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Check Maestro is installed
if ! command -v maestro &> /dev/null; then
  echo "ERROR: Maestro CLI not found."
  echo "Install with: brew install maestro"
  echo "  or: curl -Ls 'https://get.maestro.mobile.dev' | bash"
  exit 1
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     OMI APP - DEVICE-DEPENDENT MAESTRO TESTS                ║"
echo "║     ⚠️  Requires physical Omi device                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Running all flows tagged 'device_required'..."
echo ""

# Run all device_required-tagged flows via Maestro's tag system.
# Flow tags are defined in config.yaml — no hardcoded list needed.
if maestro test "$MAESTRO_DIR" --include-tags=device_required; then
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  Result: ALL DEVICE TESTS PASSED                            ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
else
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  Result: SOME TESTS FAILED — see output above               ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  exit 1
fi
