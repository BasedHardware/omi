# LLM Gateway — fallback rate elevated (ticket)

**What it means:** An active/canary gateway route or provider failed with an eligible bounded failure class and a different provider or the LKG route successfully served the request. Ordinary LKG serving because a candidate is shadowed, disabled, outside its canary bucket, or at 0% is rollout exposure, not fallback.

**PromQL:** `sum(rate(llm_gateway_requests_total{route_serving_class="actual_fallback",fallback_used="true",fallback_reason!="none",outcome="success"}[30m])) / clamp_min(sum(rate(llm_gateway_requests_total{outcome=~"success|error"}[30m])), 1e-9)`

**Rollout exposure:** `sum(rate(llm_gateway_requests_total{route_serving_class="lkg",outcome="success"}[30m])) / clamp_min(sum(rate(llm_gateway_requests_total{outcome="success"}[30m])), 1e-9)`. A high share can be intentional while a candidate is shadowed or at 0%; correlate with `llm_gateway_config_info` and route rollout state.

**Client reachability:** `llm_gateway_chat_extraction_requests_total`, `llm_gateway_circuit_open`, `llm_gateway_client_first_byte_seconds`, and structured `llm_gateway_backend_event` logs remain the primary signals for a TCP black hole the gateway cannot observe.

**Alert source:** `backend/charts/monitoring/alerts/resilience.json` tickets above 5% actual-fallback share for 30 minutes. Repository changes do not update live Grafana until the monitoring source is applied through its normal deployment path.

**Owner:** llm-gateway / platform team.

**First checks:**
1. Confirm `OMI_LLM_GATEWAY_FEATURE_MODE` and `OMI_LLM_CHAT_AGENT_ROUTE` on **all three** surfaces: GKE `backend-listen`, the `backend` Cloud Run services, and the separately released `desktop-backend` Cloud Run service. Gateway-on + Luna chat-on is the intended prod default after the 2026-08 fix; chat can be killed alone via `OMI_LLM_CHAT_AGENT_ROUTE=direct` without flipping feature mode.
2. Run the same evidence chain used by promotion: `verify-llm-gateway-serving.py` for deployment/Service/EndpointSlice/Ingress/ILB attachment, followed by the Cloud Run VPC probe. Do not treat a reserved IP as proof of reachability.
3. Inspect `llm_gateway_circuit_open`, client fallback ratio, `llm_gateway_client_first_byte_seconds` p95, and structured `llm_gateway_backend_event` reasons. If the circuit is open, keep/direct-route while repairing the data plane.
4. Inspect `llm_gateway_requests_total` by `route_serving_class`, `fallback_reason`, and bounded from/to route artifact labels. Treat `route_serving_class="lkg"` as rollout exposure unless a separate error signal is present.

## Agentic chat / Luna kill switch (2026-08)

**Outage signature (fixed class):** `unsupported lane surface: anthropic.messages` on `feature=chat_agent` / `model=omi:auto:chat-agent` when the OpenAI-compatible client hit a lane whose surface was still Anthropic Messages.

**Intended prod defaults after fix:**
- `OMI_LLM_GATEWAY_FEATURE_MODE=gateway` — fleet LLM gateway on (Luna lanes for structured/chat_agent/etc. per `generated_route_overrides.yaml`)
- `OMI_LLM_CHAT_AGENT_ROUTE=gateway` — managed agentic/desktop chat uses gateway OpenAI-compatible lane (`omi:auto:chat-agent` → Luna)

**Emergency: turn off Luna/agentic chat only (leave gateway on for other features):**
```text
OMI_LLM_CHAT_AGENT_ROUTE=direct
```
Cloud Run env update on `backend` (+ integration if needed). No need to set `FEATURE_MODE=off`.

**`desktop-backend` is a separate release vector and must be switched separately.**
It serves `/v2/chat/completions` and `/v1/desktop/proactivity/*` from its own Cloud
Run service, its env is declared inline in `.github/workflows/desktop_backend_*.yml`,
and `desktop_backend_recover_prod.yml` only shifts traffic between existing revisions
— it cannot set env. To kill desktop chat only:
```bash
gcloud run services update desktop-backend --region us-central1 \
  --project based-hardware --update-env-vars OMI_LLM_CHAT_AGENT_ROUTE=direct
```
Then land the same value in the workflow, or the next deploy silently reverts it.
Note the fallback is **direct Anthropic** (`claude-sonnet-4-6`), so this trades a
gateway outage for Anthropic spend — it is a kill switch, not a resting state.

**Emergency: turn off all gateway routing:**
```text
OMI_LLM_GATEWAY_FEATURE_MODE=off
```
(optional also set `CHAT_AGENT_ROUTE=direct`)

**Contract:** `should_route_chat_agent_through_gateway()` requires **both** chat-agent route=`gateway` **and** feature mode on. Omi-managed chat-agent traffic is always the OpenAI/Luna runner (`get_llm('chat_agent')`); Anthropic BYOK no longer selects a second Messages path on this lane. `CHAT_AGENT_ROUTE=direct` is the chat-only kill switch onto direct OpenAI.

**Severity:** Ticket — investigate during business hours unless user-facing chat error rates also rise.
