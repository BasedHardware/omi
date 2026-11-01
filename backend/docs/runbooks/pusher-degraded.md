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

## Shared DB worker saturation

`omi-pusher-db-executor-saturated` fires when every shared DB worker on a pusher
target stays active for 10 minutes. The query sums `omi_executor_task_active`
across task kinds per target and divides by `omi_executor_max_workers`, so the
threshold follows the configured pool size.

Pusher recording metadata uses the separate `record_barrier` pool (16 workers;
`PUSHER_RECORD_BARRIER_EXECUTOR_WORKERS`), with 64 queued calls and asynchronous
capacity waits. Begin, clear, seal and failure-marker transactions retain their
ordering and retry rules. Shared DB work defaults to 32 workers
(`PUSHER_DB_EXECUTOR_WORKERS`). The 2026-10-30 verdict measured a pre-barrier peak
of 20/24 DB workers and sustained post-rollout saturation at 24/24; isolation is
the fix, while 32 supplies 12 workers of headroom above the earlier peak.

Compare active/queued work for `db` and `record_barrier` with transcript drops
and `pusher_queue` backpressure. Escalate sustained pressure to the rollout lead;
preserve custody barriers and check attribution across serving revisions before
mitigation. Worker limits are startup configuration; restore the previous env
values and roll the service through its normal release path to undo a tuning change.
