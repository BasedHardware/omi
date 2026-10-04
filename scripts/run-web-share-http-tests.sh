#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/web/frontend"
if [[ ! -f node_modules/next/dist/bin/next ]]; then
  npm ci --ignore-scripts --no-audit --no-fund
fi
npm run test:share-http
