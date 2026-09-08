#!/usr/bin/env bash
# Single-process regression gate for memory-cluster XCTest suites (#9029).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$MACOS_DIR"

FILTER='MemoryAuthoritativeTierSyncTests|MemoryReconciliationScopeTests|MemoriesViewModelObserverTests'

echo "=== Combined memory suite regression (single process) ==="
xcrun swift test --package-path Desktop --filter "$FILTER"
