# LLM Gateway — fallback rate elevated (ticket)

**What it means:** The gateway or one of its upstream routes is unhealthy. A short client transport deadline and per-process circuit send new requests directly to the legacy provider after consecutive gateway transport failures, so this is normally a degraded dependency rather than a total chat outage. A circuit-open event still requires prompt investigation: it can mean the gateway is unreachable from Cloud Run even when its pods look healthy.

**PromQL:** `sum(rate(llm_gateway_chat_extraction_requests_total{mode="fallback"}[30m])) / clamp_min(sum(rate(llm_gateway_chat_extraction_requests_total{mode=~"serving|fallback"}[30m])), 1e-9)`

**Client-side signals:** `llm_gateway_chat_extraction_requests_total{mode="fallback"}`, `llm_gateway_circuit_open`, `llm_gateway_client_first_byte_seconds`, and structured `llm_gateway_backend_event` logs with `reason=circuit_open`. The gateway cannot emit a request metric for a TCP black hole it never receives, so inspect client-side fallback/circuit telemetry as the primary signal for reachability failures.

**Alerts:** the deployed LLM Gateway rules page on a client fallback ratio above 5%, any open circuit, zero gateway-serving successes after 10 client attempts, p95 client first-byte latency above 5 seconds, or zero ready production gateway endpoints. The first four are client-visible by design; the fifth is the Kubernetes control-plane corroboration.

**Owner:** llm-gateway / platform team.

**First checks:**
1. Confirm the current Cloud Run revisions are still `OMI_LLM_GATEWAY_FEATURE_MODE=direct` unless a deliberately gated promotion has occurred.
2. Run the same evidence chain used by promotion: `verify-llm-gateway-serving.py` for deployment/Service/EndpointSlice/Ingress/ILB attachment, followed by the Cloud Run VPC probe. Do not treat a reserved IP as proof of reachability.
3. Inspect `llm_gateway_circuit_open`, client fallback ratio, `llm_gateway_client_first_byte_seconds` p95, and `llm_gateway_backend_event` reasons. If the circuit is open, keep/direct-route while repairing the data plane.
4. Then inspect gateway `llm_gateway_requests_total{fallback_used="true"}` by route/model lane and upstream provider status.

**Severity:** Ticket — investigate during business hours unless user-facing chat error rates also rise.
