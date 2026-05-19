#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

summary=()

run_step() {
  local label="$1"
  shift
  echo "==> ${label}"
  "$@"
  summary+=("PASS ${label}")
}

run_step "local daemon MVP API flow" \
  "${ROOT_DIR}/desktop/local-backend/tools/e2e_smoke.sh"

run_step "desktop local-mode routing boundary" \
  xcrun swift test --package-path "${ROOT_DIR}/desktop/Desktop" --filter APIClientRoutingTests

echo
echo "Local-only MVP self-test passed:"
printf -- "- %s\n" "${summary[@]}"
