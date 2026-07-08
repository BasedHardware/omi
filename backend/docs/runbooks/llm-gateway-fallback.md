# LLM Gateway — fallback rate elevated (ticket)

**What it means:** The LLM gateway is serving a higher-than-normal share of requests via fallback routes (upstream model/provider issues). This is **dependency health**, not a product outage — chat may still succeed via fallbacks.

**PromQL:** `rate(llm_gateway_requests_total{fallback_used="true"}[30m]) / clamp_min(rate(llm_gateway_requests_total[30m]), 1e-9)`

**Owner:** llm-gateway / platform team.

**First checks:**
1. Upstream provider status and 5xx/429 rates on primary routes.
2. Gateway logs for `fallback_used=true` and circuit-breaker events.
3. Whether a single feature or model lane is driving the spike.

**Severity:** Ticket — investigate during business hours unless user-facing chat error rates also rise.
