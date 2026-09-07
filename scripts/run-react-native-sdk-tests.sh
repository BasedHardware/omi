#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/sdks/react-native"

# Provision the locked toolchain without package lifecycle scripts. The Jest
# suite itself uses mocked native boundaries and makes no network requests.
npm ci --ignore-scripts --no-audit --no-fund
npm test -- --runInBand
