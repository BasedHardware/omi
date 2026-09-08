# Sync dispatch — enqueue uncertainty and deliberate inline modes

**What it means:** A sync v2 upload normally uses a deterministic Cloud Tasks
task. An `enqueue_uncertain` event means the create-task acknowledgement was
lost after two same-name attempts; the task may already exist, so the service
returns a pollable `queued` job while preserving staged GCS audio and the
content claim. It does not start an inline worker.

**Signals (emitted by `sync.py` on Cloud Run `backend-sync`):**

- `event=sync_dispatch outcome=enqueue_uncertain` — actionable hard delivery
  uncertainty. Inspect Cloud Tasks using the job ID from the correlated request
  log before deleting or re-enqueueing anything.
- `omi_sync_dispatch_attempts_total{mode="enqueue_uncertain"}` — bounded
  counter for the same condition. Divide by all dispatch attempts for a rate.
- `omi_fallback_event component=sync_dispatch reason=byok|dispatch_disabled`
  — intentional inline modes, not an enqueue failure. BYOK cannot cross a
  task boundary; an explicitly disabled queue is configuration-controlled.

**Prometheus scrape gap:** Metric definitions and emit sites live in-repo
(`utils/metrics.py` + `routers/sync.py` on Cloud Run `backend-sync`), but GKE
Prometheus does not currently scrape this Cloud Run service. The Grafana panel
and alert are therefore advisory until the source-only monitoring contract in
[#9587](https://github.com/BasedHardware/omi/issues/9587) enables verified
delivery. Until then, use the structured Cloud Logging event above.

**PromQL (when scrape exists):**
`sum(rate(omi_sync_dispatch_attempts_total{mode="enqueue_uncertain"}[10m])) / clamp_min(sum(rate(omi_sync_dispatch_attempts_total[10m])), 1e-9)`

**First checks:** Cloud Tasks queue depth/errors and the deterministic task
name; GCS staging permissions and object presence; `SYNC_TASKS_*` runtime
configuration; then whether the job reaches a terminal state. Do not release
the content claim or unstage blobs while the task outcome is uncertain.

**Recovery boundary:** If staging fails *before* enqueue, the service safely
removes partial blobs, terminalizes the job, and returns 503 so the client WAL
can retry. If acknowledgement remains uncertain after staging, the client keeps
its WAL and polls; a missing/expired job restores normal re-upload recovery.

**Lost-dispatch exit (#10033):** A cloud_tasks job still `queued` with no
attempt ever started (`started_at`/`attempt` unset) goes stale after 30
minutes; the poll route's lease-owned finalizer terminalizes it with
`error=sync_dispatch_lost`, releasing the content claim so the client reverts
its WALs to `miss` and re-uploads from retained local files. Distinct from
`sync_worker_stale` (a died worker) so the two populations stay separable.
Inline queued jobs and worker re-queues between Cloud Tasks retries
(`attempt` set) are never poll-terminalized.

**Owner:** backend-sync team.
