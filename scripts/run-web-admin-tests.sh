#!/usr/bin/env bash
set -euo pipefail
shopt -s failglob
node --test web/admin/lib/__tests__/*.nodetest.mjs
