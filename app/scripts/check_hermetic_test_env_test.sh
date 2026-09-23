#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CHECKER="$ROOT_DIR/scripts/check_hermetic_test_env.sh"
fixture_dir="$(mktemp -d "${TMPDIR:-/tmp}/omi-hermetic-test-env.XXXXXX")"
trap 'find "$fixture_dir" -type f -delete; rmdir "$fixture_dir"' EXIT

chmod +x "$CHECKER"

"$CHECKER" --app-dir "$fixture_dir"

printf '%s\n' 'API_BASE_URL=' 'USE_WEB_AUTH=true' >"$fixture_dir/.dev.env"
"$CHECKER" --env-file "$fixture_dir/.dev.env"

printf '%s\n' 'API_BASE_URL=http://127.0.0.1:8000/' >"$fixture_dir/.dev.env"
"$CHECKER" --env-file "$fixture_dir/.dev.env"

printf '%s\n' 'API_BASE_URL=http://localhost:8080/' >"$fixture_dir/.dev.env"
"$CHECKER" --env-file "$fixture_dir/.dev.env"

printf '%s\n' 'API_BASE_URL=https://api.omi.me/' >"$fixture_dir/.dev.env"
if "$CHECKER" --env-file "$fixture_dir/.dev.env" 2>"$fixture_dir/remote.err"; then
  echo 'FAIL: accepted a remote API_BASE_URL' >&2
  exit 1
fi
grep -F 'will not rewrite' "$fixture_dir/remote.err" >/dev/null
grep -F 'https://api.omi.me/' "$fixture_dir/remote.err" >/dev/null
grep -F 'https://api.omi.me/' "$fixture_dir/.dev.env" >/dev/null

printf '%s\n' 'API_BASE_URL=http://192.168.1.212:8000/' >"$fixture_dir/.dev.env"
if "$CHECKER" --env-file "$fixture_dir/.dev.env" 2>"$fixture_dir/lan.err"; then
  echo 'FAIL: accepted a LAN API_BASE_URL' >&2
  exit 1
fi

if (
  export OMI_APP_PROFILE=mobile_beta
  "$CHECKER" --app-dir "$fixture_dir"
) 2>"$fixture_dir/profile.err"; then
  echo 'FAIL: accepted OMI_APP_PROFILE=mobile_beta' >&2
  exit 1
fi
grep -F 'local_dev' "$fixture_dir/profile.err" >/dev/null

if (
  export OMI_APP_FLAVOR=prod
  "$CHECKER" --app-dir "$fixture_dir"
) 2>"$fixture_dir/flavor.err"; then
  echo 'FAIL: accepted OMI_APP_FLAVOR=prod' >&2
  exit 1
fi

if (
  export OMI_APP_TEST_USE_PROD_API_DEFAULT=1
  "$CHECKER" --app-dir "$fixture_dir"
) 2>"$fixture_dir/prod-default.err"; then
  echo 'FAIL: accepted OMI_APP_TEST_USE_PROD_API_DEFAULT=1' >&2
  exit 1
fi

echo 'check_hermetic_test_env refuses remote APIs and non-dev pairings without rewriting'
