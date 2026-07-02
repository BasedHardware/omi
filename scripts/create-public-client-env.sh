#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/app/.client.env}"
TMP="$(mktemp "${TMPDIR:-/tmp}/omi-public-client-env.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

umask 077

emit() {
  local name="$1"
  local value="${!name:-}"
  if [ -n "$value" ]; then
    case "$value" in
      *$'\n'*|*$'\r'*)
        echo "ERROR: $name contains a newline and cannot be written to $OUT" >&2
        exit 1
        ;;
    esac
    printf '%s=%s\n' "$name" "$value" >> "$TMP"
  fi
}

# Every value emitted here is compiled into public client binaries.
emit PUBLIC_API_BASE_URL
emit PUBLIC_STAGING_API_URL
emit PUBLIC_USE_WEB_AUTH
emit PUBLIC_USE_AUTH_CUSTOM_TOKEN
emit PUBLIC_GOOGLE_MAPS_API_KEY
emit PUBLIC_GOOGLE_CLIENT_ID
emit PUBLIC_POSTHOG_API_KEY
emit PUBLIC_INTERCOM_APP_ID
emit PUBLIC_INTERCOM_IOS_API_KEY
emit PUBLIC_INTERCOM_ANDROID_API_KEY

python3 "$ROOT/scripts/check-public-client-secrets.py" --env-file "$TMP"
mkdir -p "$(dirname "$OUT")"
mv "$TMP" "$OUT"
trap - EXIT
