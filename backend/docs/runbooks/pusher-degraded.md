# Pusher — degraded session ratio high

**What it means:** More than 5% of active pusher WebSocket sessions are in degraded mode (pusher unavailable, audio routed elsewhere).

**PromQL:** `sum(pusher_sessions_degraded) / clamp_min(sum(pusher_active_ws_connections), 1)`

**Owner:** listen/pusher team.

**First checks:**
1. Pusher pod health and circuit breaker state (`pusher_circuit_breaker_state`, rejections).
2. Recent pusher deploys or upstream STT/diarizer outages.
3. Grafana pusher dashboard — error rates and active connection trends.

**Note:** Degraded sessions are a silent heal path; sustained elevation means pusher is unhealthy for a large share of listeners.
