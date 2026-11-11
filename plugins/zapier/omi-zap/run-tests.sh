#!/usr/bin/env bash
# Deterministic jest lane for the omi-zap Zapier integration
# (checks-manifest: omi-zap-tests).
#
# Reuses the installed dependency tree when it already satisfies package.json so
# the local lane needs no network; a missing or broken tree falls back to a
# lockfile-pinned `npm ci`.
set -euo pipefail

cd "$(dirname "$0")"

if ! npm ls >/dev/null 2>&1; then
  npm ci
fi

exec npm test
