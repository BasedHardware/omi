#!/usr/bin/env bash
# Source provider secrets for harness shell preflight.
# Child processes receive a fully-formed env from the harness (OMI_HARNESS_INSTANCE set);
# they do not load backend/.env or stage files on disk.
_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
_stage="${OMI_ENV_STAGE:-}"
if [ -z "$_stage" ] && [ "${PROVIDER_MODE:-}" = "offline" ]; then
  _stage="offline"
fi
if [ -z "$_stage" ]; then
  _stage="local"
fi

case "$_stage" in
  local) _secrets_file="$_repo_root/backend/.env.local-dev" ;;
  offline) _secrets_file="$_repo_root/backend/.env.offline" ;;
  *)
    # Non-harness stages: fall back to legacy stage file sourcing for standalone backend runs.
    case "$_stage" in
      dev) _secrets_file="$_repo_root/backend/.env.dev" ;;
      prod) _secrets_file="$_repo_root/backend/.env.prod" ;;
      *)
        echo "Unknown OMI_ENV_STAGE=${_stage} (expected local, offline, dev, or prod)" >&2
        exit 1
        ;;
    esac
    ;;
esac

if [ -f "$_secrets_file" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$_secrets_file"
  set +a
fi

# Optional personal overrides for manual standalone backend runs only.
_personal_env="$_repo_root/backend/.env"
if [ -f "$_personal_env" ] && [ "$_personal_env" != "$_secrets_file" ] && [ -z "${OMI_HARNESS_INSTANCE:-}" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$_personal_env"
  set +a
fi

export OMI_ENV_STAGE="$_stage"

# Firebase emulators require JDK 21+ on PATH (Homebrew keg-only install).
for _java_home in /opt/homebrew/opt/openjdk@21 /opt/homebrew/opt/openjdk@17; do
  if [ -x "$_java_home/bin/java" ]; then
    export JAVA_HOME="$_java_home"
    export PATH="$_java_home/bin:$PATH"
    break
  fi
done
