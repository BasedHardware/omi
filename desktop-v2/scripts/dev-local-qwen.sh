#!/usr/bin/env bash
#
# dev-local-qwen — wraps `pnpm tauri:dev:signed` with the env vars that point
# the coding-agent's Pi sidecar at a self-hosted vLLM endpoint instead of the
# cloud backend. Use this when iterating on the agent against a local Qwen.
#
# Configure your endpoint by creating `desktop-v2/.env.local` (gitignored):
#
#     NOOTO_DIRECT_LLM_URL=http://192.168.x.y:8000/v1
#     NOOTO_DIRECT_LLM_MODEL=qwen3.6-27b
#
# Or pass them inline:
#
#     NOOTO_DIRECT_LLM_URL=http://… ./scripts/dev-local-qwen.sh
#
# When NOOTO_DIRECT_LLM_URL is set, the coding-agent extension swaps the
# cloud-model dropdown for a green "<model> · local" badge and routes every
# request to the configured endpoint with no Firebase / OpenRouter hops.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Source `.env.local` if present so users can persist their endpoint without
# editing this script. `.env.local` is in .gitignore so personal IPs stay out
# of the repo.
if [ -f "$PROJECT_DIR/.env.local" ]; then
  set -o allexport
  # shellcheck source=/dev/null
  source "$PROJECT_DIR/.env.local"
  set +o allexport
fi

if [ -z "${NOOTO_DIRECT_LLM_URL:-}" ]; then
  cat >&2 <<EOF
NOOTO_DIRECT_LLM_URL is not set.

Create $PROJECT_DIR/.env.local with:

    NOOTO_DIRECT_LLM_URL=http://<your-vllm-host>:<port>/v1
    NOOTO_DIRECT_LLM_MODEL=qwen3.6-27b

…or run with the variables inline:

    NOOTO_DIRECT_LLM_URL=http://<vllm-host>:<port>/v1 \\
    NOOTO_DIRECT_LLM_MODEL=qwen3.6-27b \\
        ./scripts/dev-local-qwen.sh
EOF
  exit 1
fi

export NOOTO_DIRECT_LLM_URL
export NOOTO_DIRECT_LLM_MODEL="${NOOTO_DIRECT_LLM_MODEL:-qwen3.6-27b}"

cd "$PROJECT_DIR"

echo "→ NOOTO_DIRECT_LLM_URL=$NOOTO_DIRECT_LLM_URL"
echo "→ NOOTO_DIRECT_LLM_MODEL=$NOOTO_DIRECT_LLM_MODEL"
echo "→ pnpm tauri:dev:signed"

exec pnpm tauri:dev:signed
