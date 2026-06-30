#!/usr/bin/env bash
# Export provider secrets for harness shell preflight (safe parse — never `source` the file).
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

_ALLOWED_KEYS=" PROVIDER_MODE OPENAI_API_KEY DEEPGRAM_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY "

_load_allowed_secrets() {
  local file="$1"
  local line key value
  [ -f "$file" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -z "$line" ] && continue
    [[ "$line" == \#* ]] && continue
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    case "$_ALLOWED_KEYS" in
      *" $key "*) printf -v "$key" '%s' "$value"; export "$key" ;;
    esac
  done < "$file"
}

_load_allowed_secrets "$_secrets_file"

# Optional personal overrides for manual standalone backend runs only.
_personal_env="$_repo_root/backend/.env"
if [ -f "$_personal_env" ] && [ "$_personal_env" != "$_secrets_file" ] && [ -z "${OMI_HARNESS_INSTANCE:-}" ]; then
  _load_allowed_secrets "$_personal_env"
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
