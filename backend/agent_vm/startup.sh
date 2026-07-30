#!/bin/bash
set -euo pipefail

image="${AGENT_VM_IMAGE}"
auth_token="$(curl -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/attributes/auth-token)"
anthropic_api_key="$(gcloud secrets versions access latest --secret=DESKTOP_ANTHROPIC_API_KEY)"
gemini_api_key="$(gcloud secrets versions access latest --secret=GEMINI_API_KEY)"
data_dir="${AGENT_VM_DATA_DIR:-/var/lib/omi-agent}"
mkdir -p "$data_dir"
gcloud auth configure-docker gcr.io --quiet
docker pull "$image"
docker rm -f omi-agent-vm >/dev/null 2>&1 || true
docker run --detach --name omi-agent-vm --restart unless-stopped --publish 8080:8080 \
  --env ANTHROPIC_API_KEY="$anthropic_api_key" --env AUTH_TOKEN="$auth_token" --env GEMINI_API_KEY="$gemini_api_key" \
  --env PLAYWRIGHT_MCP_COMMAND=playwright-mcp \
  --env PLAYWRIGHT_MCP_ARGS='["--user-data-dir", "/app/chrome-profile", "--headless", "--no-sandbox"]' \
  --volume "$data_dir:/root/omi-agent" "$image"
