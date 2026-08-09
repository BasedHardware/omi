#!/usr/bin/env bash
#
# Reproducible live E2E for the on-prem CHAT LLM path (D32, ADR-0035), run against the compose
# stack exactly as declared (profile `chat`) — no ad-hoc `docker run`. This is the codified version
# of the manual recipe in SELFHOST_NOTES "Chat LLM (on-prem)". It proves the full chain:
#
#   app -> POST /v2/messages -> backend (agentic) -> omi:auto:* LANE
#       -> llm_gateway (resolves lane -> model) -> operator LLM (OPENAI_BASE_URL, Ollama/vLLM)
#       -> streamed answer,  hermetically (the backend has NO internet egress — ADR-0001).
#
# The LLM itself is operator-provided (ADR-0035: not bundled). The gateway is REQUIRED: the backend
# speaks omi:auto:* lane ids, which only the gateway resolves to a concrete model — a plain Ollama
# cannot be the direct target of OMI_LLM_GATEWAY_URL.
#
# Prerequisites:
#   1. llm_gateway.env exists (cp llm_gateway.env.example llm_gateway.env), with OPENAI_BASE_URL
#      pointing at your OpenAI-compatible server and a generated OMI_LLM_GATEWAY_SERVICE_TOKEN.
#   2. backend.env has the matching gateway wiring (see backend.env.example "chat LLM gateway"):
#      OMI_LLM_GATEWAY_FEATURE_MODE=gateway, OMI_LLM_GATEWAY_URL=http://llm_gateway:9080,
#      OMI_LLM_GATEWAY_SERVICE_TOKEN=<same as llm_gateway.env>,
#      OMI_LLM_GATEWAY_ALLOW_PROD_FEATURE_MODE=true  (OMI_ENV_STAGE=offline is prod-like),
#      and LOCAL_DEVELOPMENT=true  (this smoke test auths with `Bearer dev` -> uid 123).
#   3. Your LLM server actually serves the model named in
#      llm_gateway/generated_route_overrides.yaml (edit it to your model).
#
# Usage:  deploy/onprem/run-chat-e2e.sh
#   Override: COMPOSE_PROJECT.
set -euo pipefail

PROJECT="${COMPOSE_PROJECT:-omi-onprem}"
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OVERRIDES="$COMPOSE_DIR/llm_gateway/generated_route_overrides.yaml"

compose() { docker compose -p "$PROJECT" -f "$COMPOSE_DIR/docker-compose.yml" --profile chat "$@"; }
log() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
fail() { printf '\033[31mFAIL: %s\033[0m\n' "$*"; exit 1; }

MODEL="$(grep -m1 -oE 'model: [^}[:space:]]+' "$OVERRIDES" | awk '{print $2}')"
log "on-prem chat model (from override file): ${MODEL:-<unset>}"

log "bring the chat profile up (backend + llm_gateway + deps), wait for health"
compose up -d backend llm_gateway
for svc in backend llm_gateway; do
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "${PROJECT}-${svc}-1" 2>/dev/null)" = healthy ]; do sleep 3; done
done

log "E2E: POST /v2/messages (streamed agentic answer through backend -> gateway -> $MODEL)"
OUT="$(compose exec -T backend curl -sS -N -X POST http://localhost:8080/v2/messages \
  -H 'Authorization: Bearer dev' -H 'Content-Type: application/json' \
  -d '{"text":"Reply with one short friendly sentence confirming the on-prem chat works."}')"

printf '%s' "$OUT" | grep -qiE 'Unable to complete the response' \
  && fail "agentic loop errored (check: gateway healthy, OPENAI_BASE_URL serves $MODEL, backend logs)"

ANSWER="$(printf '%s' "$OUT" | grep -m1 '^done: ' | sed 's/^done: //' \
  | python3 -c 'import sys,base64,json; s=sys.stdin.read().strip(); s+="="*(-len(s)%4); print(json.loads(base64.b64decode(s))["text"])' 2>/dev/null || true)"
[ -n "$ANSWER" ] || fail "no assistant answer in the stream"
printf '  ANSWER: %s\n' "$ANSWER"

log "hermeticity (ADR-0001): the backend must NOT reach the internet"
compose exec -T backend sh -c 'curl -m4 -sS https://api.openai.com/v1/models >/dev/null 2>&1; test $? -ne 0' \
  || fail "backend reached api.openai.com — on-prem egress leak"
echo "  OK: backend cannot resolve/reach api.openai.com (no egress)"

log "PASS — on-prem chat E2E green (model=$MODEL, real streamed answer, hermetic)"
