#!/usr/bin/env bash
# Refuse a hermetic app run whose .dev.env (or env) points off-loopback or
# at a flavor/profile pairing other than dev + local_dev.
#
# Does not rewrite the env file. A stale API_BASE_URL that survived
# app/test.sh's "generated files already exist" skip is a fail, not a rewrite.
set -euo pipefail

usage() {
  echo "usage: $0 [--env-file <path>] [--app-dir <path>]" >&2
}

env_file=''
app_dir=''
while (($#)); do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      env_file="$2"
      shift 2
      ;;
    --app-dir)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      app_dir="$2"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$app_dir" ]]; then
  app_dir="$(cd "$(dirname "$0")/.." && pwd)"
fi
env_file="${env_file:-$app_dir/.dev.env}"

is_loopback_api_base() {
  local raw="${1:-}"
  raw="${raw#"${raw%%[![:space:]]*}"}"
  raw="${raw%"${raw##*[![:space:]]}"}"
  if [[ "$raw" == \"*\" && "$raw" == *\" ]]; then
    raw="${raw:1:${#raw}-2}"
  elif [[ "$raw" == \'*\' && "$raw" == *\' ]]; then
    raw="${raw:1:${#raw}-2}"
  fi
  [[ -z "$raw" ]] && return 0
  local rest="$raw"
  if [[ "$rest" == *"://"* ]]; then
    rest="${rest#*://}"
  fi
  if [[ "$rest" == *@* ]]; then
    rest="${rest##*@}"
  fi
  if [[ "$rest" == \[* ]]; then
    rest="${rest#\[}"
    rest="${rest%%]*}"
  else
    rest="${rest%%:*}"
  fi
  case "$rest" in
    localhost|127.0.0.1|::1) return 0 ;;
    *) return 1 ;;
  esac
}

profile="${OMI_APP_PROFILE:-}"
flavor="${OMI_APP_FLAVOR:-}"
if [[ -n "$profile" && "$profile" != "local_dev" ]]; then
  echo "ERROR: hermetic app tests require OMI_APP_PROFILE=local_dev (or unset), got '$profile'." >&2
  echo "       Unset it; this check will not rewrite app/.dev.env." >&2
  exit 1
fi
if [[ -n "$flavor" && "$flavor" != "dev" ]]; then
  echo "ERROR: hermetic app tests require flavor=dev (or unset OMI_APP_FLAVOR), got '$flavor'." >&2
  echo "       Unset it; this check will not rewrite app/.dev.env." >&2
  exit 1
fi

if [[ -n "${OMI_APP_TEST_USE_PROD_API_DEFAULT:-}" && "${OMI_APP_TEST_USE_PROD_API_DEFAULT}" == "1" ]]; then
  echo "ERROR: OMI_APP_TEST_USE_PROD_API_DEFAULT=1 is not allowed for hermetic app/test.sh." >&2
  exit 1
fi

if [[ -n "${OMI_APP_TEST_API_BASE_URL:-}" ]] && ! is_loopback_api_base "$OMI_APP_TEST_API_BASE_URL"; then
  echo "ERROR: OMI_APP_TEST_API_BASE_URL='$OMI_APP_TEST_API_BASE_URL' is not empty or loopback." >&2
  echo "       Hermetic tests refuse a remote API; this check will not rewrite app/.dev.env." >&2
  exit 1
fi

if [[ ! -f "$env_file" ]]; then
  exit 0
fi

api_value=""
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line#"${line%%[![:space:]]*}"}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  [[ "$line" != API_BASE_URL=* ]] && continue
  api_value="${line#API_BASE_URL=}"
done <"$env_file"

if ! is_loopback_api_base "$api_value"; then
  echo "ERROR: $env_file API_BASE_URL='$api_value' is not empty or loopback." >&2
  echo "       Hermetic tests refuse a remote API; this check will not rewrite the file." >&2
  exit 1
fi
