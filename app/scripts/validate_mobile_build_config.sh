#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --flavor <dev|prod> [--profile <profile>] [--env-file <path>]" >&2
}

flavor=''
profile=''
env_file=''
while (($#)); do
  case "$1" in
    --flavor)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      flavor="$2"
      shift 2
      ;;
    --profile)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      profile="$2"
      shift 2
      ;;
    --env-file)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      env_file="$2"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

case "$flavor" in
  dev)
    expected_profile='local_dev'
    default_env_file='.dev.env'
    ;;
  prod)
    expected_profile='mobile_beta'
    default_env_file='.env'
    ;;
  *)
    echo "ERROR: unsupported mobile flavor '${flavor:-<missing>}' (expected dev or prod)." >&2
    exit 1
    ;;
esac

if [[ -n "$profile" && "$profile" != "$expected_profile" ]]; then
  echo "ERROR: mobile flavor '$flavor' requires OMI_APP_PROFILE=$expected_profile, got '$profile'." >&2
  exit 1
fi

env_file="${env_file:-$default_env_file}"
if [[ ! -f "$env_file" ]]; then
  echo "ERROR: missing $env_file; run setup_app_env $expected_profile before building." >&2
  exit 1
fi

read_setting() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { value = $2 } END { print value }' "$env_file"
}

for key in USE_WEB_AUTH USE_AUTH_CUSTOM_TOKEN; do
  if [[ "$(read_setting "$key")" != 'true' ]]; then
    echo "ERROR: $env_file must contain $key=true for the supported $flavor/$expected_profile mobile build." >&2
    exit 1
  fi
done

echo "mobile build config valid: flavor=$flavor profile=$expected_profile env=$env_file"
