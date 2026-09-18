#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VALIDATOR="$ROOT_DIR/scripts/validate_mobile_build_config.sh"
fixture_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-mobile-build-config.XXXXXX")"
trap 'find "$fixture_dir" -type f -delete; rmdir "$fixture_dir"' EXIT

printf '%s\n' \
  'API_BASE_URL=http://192.168.1.212:8000/' \
  'USE_WEB_AUTH=true' \
  'USE_AUTH_CUSTOM_TOKEN=true' >"$fixture_dir/.dev.env"

valid_output="$(
  cd "$fixture_dir"
  "$VALIDATOR" --flavor dev --profile local_dev
)"
[[ "$valid_output" == *'flavor=dev profile=local_dev'* ]]

if (
  cd "$fixture_dir"
  "$VALIDATOR" --flavor prod --profile local_dev
) 2>"$fixture_dir/mismatch.err"; then
  echo 'FAIL: accepted prod/local_dev pairing' >&2
  exit 1
fi
grep -F "requires OMI_APP_PROFILE=mobile_beta" "$fixture_dir/mismatch.err" >/dev/null

printf '%s\n' \
  'API_BASE_URL=http://192.168.1.212:8000/' \
  'USE_WEB_AUTH=false' \
  'USE_AUTH_CUSTOM_TOKEN=true' >"$fixture_dir/.dev.env"
if (
  cd "$fixture_dir"
  "$VALIDATOR" --flavor dev
) 2>"$fixture_dir/flags.err"; then
  echo 'FAIL: accepted native-auth local build without web auth' >&2
  exit 1
fi
grep -F 'USE_WEB_AUTH=true' "$fixture_dir/flags.err" >/dev/null

printf '%s\n' \
  'API_BASE_URL=https://api.omiapi.com/' \
  'USE_WEB_AUTH=true' \
  'USE_AUTH_CUSTOM_TOKEN=true' >"$fixture_dir/.env"
prod_output="$(
  cd "$fixture_dir"
  "$VALIDATOR" --flavor prod --profile mobile_beta
)"
[[ "$prod_output" == *'flavor=prod profile=mobile_beta'* ]]

rm "$fixture_dir/.env"
if (
  cd "$fixture_dir"
  "$VALIDATOR" --flavor prod --profile mobile_beta
) 2>"$fixture_dir/missing.err"; then
  echo 'FAIL: accepted a production build without its env file' >&2
  exit 1
fi
grep -F 'missing .env' "$fixture_dir/missing.err" >/dev/null

printf '%s\n' \
  'API_BASE_URL=https://api.omiapi.com/' \
  'USE_WEB_AUTH=true' \
  'USE_AUTH_CUSTOM_TOKEN=false' >"$fixture_dir/.env"
if (
  cd "$fixture_dir"
  "$VALIDATOR" --flavor prod
) 2>"$fixture_dir/custom-token.err"; then
  echo 'FAIL: accepted a build without custom-token auth' >&2
  exit 1
fi
grep -F 'USE_AUTH_CUSTOM_TOKEN=true' "$fixture_dir/custom-token.err" >/dev/null

source "$ROOT_DIR/setup.sh" >/dev/null
if validate_flutter_profile_arg mobile_beta --dart-define=OMI_APP_PROFILE=production 2>"$fixture_dir/wrapper.err"; then
  echo 'FAIL: wrapper accepted a conflicting profile define' >&2
  exit 1
fi
grep -F "requires OMI_APP_PROFILE=mobile_beta" "$fixture_dir/wrapper.err" >/dev/null

if validate_flutter_profile_arg mobile_beta \
  --dart-define=OMI_APP_PROFILE=mobile_beta \
  --dart-define=OMI_APP_PROFILE=mobile_beta 2>"$fixture_dir/duplicate.err"; then
  echo 'FAIL: wrapper accepted duplicate profile defines' >&2
  exit 1
fi
grep -F 'pass OMI_APP_PROFILE only once' "$fixture_dir/duplicate.err" >/dev/null

echo 'validate_mobile_build_config rejects invalid flavor/profile and auth settings'
