#!/bin/bash
set -euo pipefail

image="${AGENT_VM_IMAGE}"

metadata_get() {
  curl -fsS -H 'Metadata-Flavor: Google' "$1"
}

metadata_access_token() {
  metadata_get "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])'
}

secret_access() {
  local secret_name="$1"
  local project_id
  local access_token
  project_id="$(metadata_get 'http://metadata.google.internal/computeMetadata/v1/project/project-id')"
  access_token="$(metadata_access_token)"
  curl -fsS \
    -H "Authorization: Bearer $access_token" \
    "https://secretmanager.googleapis.com/v1/projects/${project_id}/secrets/${secret_name}/versions/latest:access" \
    | python3 -c 'import base64, json, sys; print(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode())'
}

auth_token="$(metadata_get 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/auth-token')"
anthropic_api_key="$(secret_access DESKTOP_ANTHROPIC_API_KEY)"
gemini_secret_name="${AGENT_VM_GEMINI_SECRET_NAME}"
gemini_api_key="$(secret_access "$gemini_secret_name")"
data_dir="${AGENT_VM_DATA_DIR:-/var/lib/omi-agent}"
mkdir -p "$data_dir"

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io
fi
if ! docker info >/dev/null 2>&1; then
  if command -v systemctl >/dev/null 2>&1 && systemctl enable --now docker; then
    :
  elif command -v service >/dev/null 2>&1; then
    service docker start
  else
    echo 'Docker daemon could not be started' >&2
    exit 1
  fi
fi

registry_token="$(metadata_access_token)"
printf '%s' "$registry_token" | docker login --username oauth2accesstoken --password-stdin https://gcr.io >/dev/null
docker pull "$image"
docker rm -f omi-agent-vm >/dev/null 2>&1 || true
docker run --detach --name omi-agent-vm --restart unless-stopped --publish 8080:8080 \
  --env ANTHROPIC_API_KEY="$anthropic_api_key" --env AUTH_TOKEN="$auth_token" --env GEMINI_API_KEY="$gemini_api_key" \
  --env PLAYWRIGHT_MCP_COMMAND=playwright-mcp \
  --env PLAYWRIGHT_MCP_ARGS='["--user-data-dir", "/app/chrome-profile", "--headless", "--no-sandbox"]' \
  --volume "$data_dir:/root/omi-agent" "$image"
