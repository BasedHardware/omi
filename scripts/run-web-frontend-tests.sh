#!/usr/bin/env bash
set -euo pipefail
shopt -s failglob
node --test web/frontend/src/__tests__/*.test.mjs
