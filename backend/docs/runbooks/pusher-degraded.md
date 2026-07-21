# Pusher — degraded session ratio high

**What it means:** More than 5% of active listener WebSocket sessions are in degraded mode because the listener cannot use Pusher and routes audio elsewhere. This is a likely user-impact signal, not proof that every listener lost data.

**PromQL:** `sum(pusher_sessions_degraded{job="backend-listen-metrics"}) / clamp_min(sum(backend_listen_active_ws_connections{job="backend-listen-metrics"}), 1)`

The degraded-session gauge is emitted by the backend-listen reconnect loop. Do not query the similarly named Pusher-process connection metric: it does not own this outcome.

**Owner:** listen/pusher team.

**First checks:**
1. Pusher pod health and circuit breaker state (`pusher_circuit_breaker_state`, rejections).
2. Recent pusher deploys or upstream STT/diarizer outages.
3. Grafana pusher dashboard — error rates and active connection trends.

**Note:** Degraded sessions are a silent heal path; sustained elevation means pusher is unhealthy for a large share of listeners.
