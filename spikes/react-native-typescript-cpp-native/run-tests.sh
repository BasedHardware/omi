#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "1. Building and Running C++ ISO C++17 Host Tests"
echo "=================================================="
cmake -B build -S .
cmake --build build
ctest --test-dir build --output-on-failure

echo ""
echo "=================================================="
echo "2. Running TypeScript Domain & Boundary Tests (Node 22)"
echo "=================================================="
node --experimental-strip-types --test ts/tests/*.test.ts

echo ""
echo "=================================================="
echo "ALL TESTS PASSED SUCCESSFULLY!"
echo "=================================================="
