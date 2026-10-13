#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PERF_SCORECARD_DIR="${PERF_SCORECARD_DIR:-/tmp/omi-perf}"
export PERF_BUDGET_FILE="${PERF_BUDGET_FILE:-$APP_DIR/integration_test/perf/budgets.json}"
cd "$APP_DIR"
exec flutter test --no-pub -d flutter-tester --concurrency=1 \
  --dart-define=OMI_APP_PROFILE=local_dev \
  integration_test/perf/perf_main.dart "$@"
