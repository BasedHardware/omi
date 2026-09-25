#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

source setup.sh

fixture_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-setup-env.XXXXXX")"
trap 'rm -rf "$fixture_dir"' EXIT

printf '%s\n' \
  '# developer-owned setting' \
  'STAGING_API_URL=https://staging.example.test/' \
  'API_BASE_URL=https://old.example.test/' \
  'USE_WEB_AUTH=false' \
  'USE_AUTH_CUSTOM_TOKEN=false' \
  'CUSTOM_FLAG=keep-me' >"$fixture_dir/.env"

(
  cd "$fixture_dir"
  setup_app_env mobile_beta
)

grep -Fx '# developer-owned setting' "$fixture_dir/.env" >/dev/null
grep -Fx 'STAGING_API_URL=https://staging.example.test/' "$fixture_dir/.env" >/dev/null
grep -Fx 'CUSTOM_FLAG=keep-me' "$fixture_dir/.env" >/dev/null
grep -Fx 'API_BASE_URL=https://api.omiapi.com/' "$fixture_dir/.env" >/dev/null
grep -Fx 'USE_WEB_AUTH=true' "$fixture_dir/.env" >/dev/null
grep -Fx 'USE_AUTH_CUSTOM_TOKEN=true' "$fixture_dir/.env" >/dev/null

[[ "$(grep -c '^API_BASE_URL=' "$fixture_dir/.env")" == 1 ]]
[[ "$(grep -c '^USE_WEB_AUTH=' "$fixture_dir/.env")" == 1 ]]
[[ "$(grep -c '^USE_AUTH_CUSTOM_TOKEN=' "$fixture_dir/.env")" == 1 ]]

echo "setup_app_env preserves unrelated keys and updates beta-owned keys"

printf '%s\n' \
  '# developer-owned setting' \
  'API_BASE_URL=https://old.example.test/' \
  'USE_WEB_AUTH=false' \
  'USE_AUTH_CUSTOM_TOKEN=false' >"$fixture_dir/.dev.env"

(
  cd "$fixture_dir"
  setup_app_env local_dev 'http://192.168.1.212:8000/'
)

grep -Fx '# developer-owned setting' "$fixture_dir/.dev.env" >/dev/null
grep -Fx 'API_BASE_URL=http://192.168.1.212:8000/' "$fixture_dir/.dev.env" >/dev/null
grep -Fx 'USE_WEB_AUTH=true' "$fixture_dir/.dev.env" >/dev/null
grep -Fx 'USE_AUTH_CUSTOM_TOKEN=true' "$fixture_dir/.dev.env" >/dev/null
echo "setup_app_env enables web OAuth and custom-token exchange for local device builds"
