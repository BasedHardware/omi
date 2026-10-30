#!/usr/bin/env bash
set -euo pipefail
shopt -s failglob
cd "$(git rev-parse --show-toplevel)/web/frontend"
if [[ ! -f node_modules/@omi/note-shared/note-citations.mjs ]]; then
  npm ci --ignore-scripts --no-audit --no-fund
fi
node --test src/__tests__/*.test.mjs
