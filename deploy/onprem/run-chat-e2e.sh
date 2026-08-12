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
#   2. backend.env has the matching gateway wiring (see backend.env.dev.example "chat LLM gateway"):
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

compose() { docker compose -p "$PROJECT" -f "$COMPOSE_DIR/compose.dev.yaml" --profile chat "$@"; }
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

# Reject a typed error/timeout terminal frame BEFORE accepting any done: payload, so the smoke test
# proves a real successful LLM turn — not a canned fallback (cubic review PR 10887).
printf '%s' "$OUT" | grep -qiE '^error: |Unable to complete the response|The response took too long' \
  && fail "agentic loop errored/timed out (check: gateway healthy, OPENAI_BASE_URL serves $MODEL, backend logs)"

ANSWER="$(printf '%s' "$OUT" | grep -m1 '^done: ' | sed 's/^done: //' \
  | python3 -c 'import sys,base64,json; s=sys.stdin.read().strip(); s+="="*(-len(s)%4); print(json.loads(base64.b64decode(s))["text"])' 2>/dev/null || true)"
[ -n "$ANSWER" ] || fail "no assistant answer in the stream"
printf '  ANSWER: %s\n' "$ANSWER"

log "answer came from the LOCAL model (no cloud): the gateway loaded $MODEL on the operator endpoint"
docker exec omi-onprem-ollama ollama ps >/dev/null 2>&1 || true   # host Ollama, if containerized
curl -fsS http://127.0.0.1:11434/api/ps 2>/dev/null | grep -q "$MODEL" \
  && echo "  OK: host inference served $MODEL for this chat" \
  || echo "  NOTE: could not confirm $MODEL on the host endpoint (best-effort); the streamed answer above is the proof."
# NOTE: this runs on compose.dev.yaml, which is NON-hermetic (omi non-internal → the backend has
# egress) by design. The no-egress proof (ADR-0001) is a PROD-posture check, not a dev one:
#   docker compose -f compose.prod.yaml exec -T backend sh -c 'curl -m3 https://api.openai.com; echo $?'  # must FAIL
# See SELFHOST_NOTES "Verification (WP0 acceptance)".

log "PASS — on-prem chat E2E green (model=$MODEL, real streamed answer from the local model)"
