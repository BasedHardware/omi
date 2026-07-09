# Sync dispatch — Cloud Tasks fallback

**What it means:** Sync v2 jobs are not running via Cloud Tasks and are falling back to inline processing on the API instance.

**Reasons (instrumentation in `sync.py`; metrics emitted on Cloud Run `backend-sync`):**
- `enqueue_failed` — Cloud Tasks enqueue or GCS staging failed.
- `byok` — expected; BYOK keys cannot follow a Cloud Task. Not actionable.
- `dispatch_disabled` — `SYNC_DISPATCH_MODE` is not `cloud_tasks`. Not actionable in prod.

**Prometheus scrape gap:** Metric definitions and emit sites live in-repo (`utils/metrics.py` + `routers/sync.py` on Cloud Run `backend-sync`), but GKE Prometheus only scrapes `backend-listen` and `pusher`. The Grafana sync panel and the PAGE alert for enqueue_failed share are **paused** until Cloud Run custom metrics are exported into Prometheus.

**Operator signal (until scrape exists):** Cloud Logging on `backend-sync` for structured events matching `omi_fallback_event component=sync_dispatch reason=enqueue_failed` (and `reason=byok` / `dispatch_disabled` for context).

**PromQL (when scrape exists):** `sum(rate(omi_fallback_total{component="sync_dispatch",reason="enqueue_failed"}[10m])) / clamp_min(sum(rate(omi_sync_dispatch_attempts_total[10m])), 1e-9)`

**Owner:** backend-sync team.

**First checks:** Cloud Tasks queue depth/errors, GCS staging permissions, `SYNC_TASKS_*` env on backend-sync.
