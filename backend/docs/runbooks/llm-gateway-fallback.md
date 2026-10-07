# LLM Gateway — fallback rate elevated (ticket)

**Company-paid generation cutover:** see [JEV and Luna cutover](../llm/jev-luna-cutover.md).
Paid feature and desktop generation now require the gateway. The historical
feature-mode/direct-routing switches described below cannot restore paid Gemini
generation. Repair gateway availability or pause generation during an outage;
do not roll back to a pre-cutover image while the Gemini cutoff is in force.

**What it means:** An active/canary gateway route or provider failed with an eligible bounded failure class and a different provider or the LKG route successfully served the request. Ordinary LKG serving because a candidate is shadowed, disabled, outside its canary bucket, or at 0% is rollout exposure, not fallback.

**PromQL:** `sum(rate(llm_gateway_requests_total{route_serving_class="actual_fallback",fallback_used="true",fallback_reason!="none",outcome="success"}[30m])) / clamp_min(sum(rate(llm_gateway_requests_total{outcome=~"success|error"}[30m])), 1e-9)`

**Rollout exposure:** `sum(rate(llm_gateway_requests_total{route_serving_class="lkg",outcome="success"}[30m])) / clamp_min(sum(rate(llm_gateway_requests_total{outcome="success"}[30m])), 1e-9)`. A high share can be intentional while a candidate is shadowed or at 0%; correlate with `llm_gateway_config_info` and route rollout state.

**Client reachability:** `llm_gateway_chat_extraction_requests_total`, `llm_gateway_circuit_open`, `llm_gateway_client_first_byte_seconds`, and structured `llm_gateway_backend_event` logs remain the primary signals for a TCP black hole the gateway cannot observe.

**Alert source:** `backend/charts/monitoring/alerts/resilience.json` tickets above 5% actual-fallback share for 30 minutes. Repository changes do not update live Grafana until the monitoring source is applied through its normal deployment path.

**Owner:** llm-gateway / platform team.

**First checks:**
1. Confirm gateway URL, service authentication, and the deployed cutover image on every generation host: GKE `backend-listen`, backend/sync Cloud Run, separately released `desktop-backend`, and jobs. Company-paid generation requires gateway routing after BYOK selection.
2. Run the same evidence chain used by promotion: `verify-llm-gateway-serving.py` for deployment/Service/EndpointSlice/Ingress/ILB attachment, followed by the Cloud Run VPC probe. Do not treat a reserved IP as proof of reachability.
3. Inspect `llm_gateway_circuit_open`, client fallback ratio, `llm_gateway_client_first_byte_seconds` p95, and structured `llm_gateway_backend_event` reasons. If the circuit is open, repair the data plane; paid generation must remain on gateway lanes.
4. Inspect `llm_gateway_requests_total` by `route_serving_class`, `fallback_reason`, and bounded from/to route artifact labels. Treat `route_serving_class="lkg"` as rollout exposure unless a separate error signal is present.

## Generation outage response

Company-paid feature and desktop generation are gateway-only. The historical
`OMI_LLM_CHAT_AGENT_ROUTE=direct` and `OMI_LLM_GATEWAY_FEATURE_MODE=off` switches
are not an escape to paid provider generation. Existing optional surfaces
such as embeddings retain their own contracts; see the endpoint inventory.

Repair the route, service authentication, provider quota, or network path.
Pause screen-task generation with `SCREEN_TASK_STOP=1` when needed. A JEV
outage admits the bounded Luna extractor; a Luna outage returns unavailable.
A pre-cutover backend/gateway image restores that image's Gemini behavior,
so do not use that rollback while the paid Gemini cutoff is in force.

`desktop-backend` is separately released; backend-wide deployments do not
update it. Verify its own revision, gateway VPC reachability, and streamed
request evidence before shifting traffic. Deployment changes belong to the
normal release workflow, not this diagnostic runbook.

**Severity:** Ticket — investigate during business hours unless user-facing chat error rates also rise.
