# Sync dispatch — Cloud Tasks fallback

**What it means:** Sync v2 jobs are not running via Cloud Tasks and are falling back to inline processing on the API instance.

**Reasons (check `omi_fallback_total{component="sync_dispatch"}`):**
- `enqueue_failed` — Cloud Tasks enqueue or GCS staging failed. **This alert pages** when enqueue_failed share > 20%.
- `byok` — expected; BYOK keys cannot follow a Cloud Task. Not actionable.
- `dispatch_disabled` — `SYNC_DISPATCH_MODE` is not `cloud_tasks`. Not actionable in prod.

**PromQL (page):** `rate(omi_fallback_total{component="sync_dispatch",reason="enqueue_failed"}[10m]) / clamp_min(rate(omi_sync_dispatch_attempts_total[10m]), 1e-9)`

**Owner:** backend-sync team.

**First checks:** Cloud Tasks queue depth/errors, GCS staging permissions, `SYNC_TASKS_*` env on backend-sync.
