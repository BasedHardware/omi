# LLM Gateway — fallback rate elevated (ticket)

**What it means:** An active/canary gateway route or provider failed with an eligible bounded failure class and a different provider or the LKG route successfully served the request. Ordinary LKG serving because a candidate is shadowed, disabled, outside its canary bucket, or at 0% is rollout exposure, not fallback.

**PromQL:** `sum(rate(llm_gateway_requests_total{route_serving_class="actual_fallback",fallback_used="true",fallback_reason!="none",outcome="success"}[30m])) / clamp_min(sum(rate(llm_gateway_requests_total{outcome=~"success|error"}[30m])), 1e-9)`

**Rollout exposure:** `sum(rate(llm_gateway_requests_total{route_serving_class="lkg",outcome="success"}[30m])) / clamp_min(sum(rate(llm_gateway_requests_total{outcome="success"}[30m])), 1e-9)`. A high share can be intentional while a candidate is shadowed or at 0%; correlate with `llm_gateway_config_info` and route rollout state.

**Client reachability:** `llm_gateway_chat_extraction_requests_total`, `llm_gateway_circuit_open`, `llm_gateway_client_first_byte_seconds`, and structured `llm_gateway_backend_event` logs remain the primary signals for a TCP black hole the gateway cannot observe.

**Alert source:** `backend/charts/monitoring/alerts/resilience.json` tickets above 5% actual-fallback share for 30 minutes. Repository changes do not update live Grafana until the monitoring source is applied through its normal deployment path.

**Owner:** llm-gateway / platform team.

**First checks:**
1. Confirm the current Cloud Run revisions are still `OMI_LLM_GATEWAY_FEATURE_MODE=direct` unless a deliberately gated promotion has occurred.
2. Run the same evidence chain used by promotion: `verify-llm-gateway-serving.py` for deployment/Service/EndpointSlice/Ingress/ILB attachment, followed by the Cloud Run VPC probe. Do not treat a reserved IP as proof of reachability.
3. Inspect `llm_gateway_circuit_open`, client fallback ratio, `llm_gateway_client_first_byte_seconds` p95, and `llm_gateway_backend_event` reasons. If the circuit is open, keep/direct-route while repairing the data plane.
4. Inspect `llm_gateway_requests_total` by `route_serving_class`, `fallback_reason`, and bounded from/to route artifact labels. Treat `route_serving_class="lkg"` as rollout exposure unless a separate error signal is present.

**Severity:** Ticket — investigate during business hours unless user-facing chat error rates also rise.
