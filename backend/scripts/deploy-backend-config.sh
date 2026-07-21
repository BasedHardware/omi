#!/usr/bin/env bash
# Apply the non-secret backend runtime configuration without exposing values.

set -euo pipefail

: "${ENVIRONMENT:?ENVIRONMENT must be set to dev or prod}"

required_config=(
  CONVERSATION_SUMMARIZED_APP_IDS
  GOOGLE_CLIENT_ID
  MCP_AUTHORIZATION_SERVER_URL
  MCP_OAUTH_CHATGPT_CLIENT_ID
  MCP_OAUTH_CHATGPT_REDIRECT_URIS
  MCP_OAUTH_PUBLIC_CLIENT_ID
  MCP_OAUTH_PUBLIC_REDIRECT_URIS
  MCP_RESOURCE_URL
  RAPID_API_HOST
  REDIS_DB_HOST
  STT_PRERECORDED_MODEL
  STT_SERVICE_MODELS
  TYPESENSE_HOST
  TWILIO_ACCOUNT_SID
  TWILIO_API_KEY_SID
  TWILIO_TWIML_APP_SID
  X_OAUTH_CLIENT_ID
  X_OAUTH_REDIRECT_URI
)

if [[ "$ENVIRONMENT" == "prod" ]]; then
  required_config+=(
    ACCOUNT_DELETION_HANDLER_URL
    MCP_OAUTH_CLAUDE_CLIENT_ID
    MCP_OAUTH_CLAUDE_CLIENT_NAME
    MCP_OAUTH_CLAUDE_REDIRECT_URIS
    SYNC_TASKS_HANDLER_URL
    SYNC_TASKS_INVOKER_SA
  )
fi

missing=()
for name in "${required_config[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done
if (( ${#missing[@]} > 0 )); then
  printf 'Missing required non-secret deployment variables: %s\n' "${missing[*]}" >&2
  exit 1
fi

namespace="${ENVIRONMENT}-omi-backend"
config_map="${ENVIRONMENT}-omi-backend-config"
env_file="$(mktemp)"
trap 'rm -f "$env_file"' EXIT

for name in "${required_config[@]}"; do
  printf '%s=%s\n' "$name" "${!name}" >> "$env_file"
done

kubectl -n "$namespace" create configmap "$config_map" \
  --from-env-file="$env_file" \
  --dry-run=client \
  -o yaml | kubectl apply -f -

echo "Applied non-secret runtime ConfigMap ${namespace}/${config_map} (${#required_config[@]} keys)."
