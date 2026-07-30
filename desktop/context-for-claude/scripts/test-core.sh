#!/usr/bin/env bash
# Hermetic portable-core tests for Context for Claude. Runs on any host with cmake/cxx —
# no Xcode, no FluidAudio, no signing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${TMPDIR:-/tmp}/context-for-claude-core-ci-$$"
cleanup() { rm -rf "$BUILD"; }
trap cleanup EXIT
cmake -S "$ROOT/core" -B "$BUILD"
cmake --build "$BUILD"
ctest --test-dir "$BUILD" --output-on-failure
