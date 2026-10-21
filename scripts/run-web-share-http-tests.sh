#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/web/frontend"
if [[ ! -f node_modules/next/dist/bin/next || ! -f node_modules/@omi/note-shared/note-citations.mjs ]]; then
  npm ci --ignore-scripts --no-audit --no-fund
fi
npm run test:share-http
