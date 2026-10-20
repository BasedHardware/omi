# Sync Cloud Run sizing and phase metrics

Current Train 1 capacity is documented in the concurrency section below. Other sizing, cost and lifetime-audit sections retain their original dated evidence; they are not authorization to apply those older proposals.
Evidence cutoff: 2026-10-04. Production remains read-only in this build lane; deploy only after review through the normal GitHub Actions path. Cost scenarios overlap and must not be added. Figures use 30 days, gross us-central1 list rates, without credits/commitments.

## Metrics and export acceptance

`omi_sync_phase_duration_seconds{lane,phase}` measures each operation, including failures. `omi_sync_phase_calls_per_job{lane,phase}` records operation calls per pipeline/Cloud Tasks attempt, including zero calls, empty-result retries and actual Parakeet HTTP fallback calls. Lanes: `fresh|backfill|unknown`; phases: `decode_vad|gcs|parakeet|speaker_id|firestore`. A retry is a new attempt, not a distinct logical job.

Context propagates through existing executor dispatch. Nested pipeline calls share the outer handler's attempt. The Cloud Tasks handler includes staged downloads and cleanup. Inline attempts cover the pipeline, not admission/staging before it. V1 synchronous sync has no attempt context and is excluded. Firestore timing covers ingest/assignment transactions, processed-conversation persistence and audio-file persistence. Redis job progress/finalization and entitlement/read helpers are excluded. Speaker ID includes embedding/text identification. GCS includes staged object operations, signed-audio downloads and chunk uploads. Operations overlap across threads; their sum is not whole-job wall time. Background effects after an attempt closes are excluded.

Both histograms are available at the existing authenticated `/metrics` endpoint. `SYNC_PHASE_METRICS_EXPORT_ENABLED=true` enables cumulative distribution export to `custom.googleapis.com/omi_sync_phase_*` using runtime ADC. Request completion signals one dedicated daemon worker without awaiting export. A one-slot queue drops redundant signals on overflow; cumulative samples stay in the histograms. Network and ADC work run only in that worker. The existing Cloud Monitoring exporter has filters for both sync services and this custom prefix. Application labels are fixed; the monitored resource includes service/revision/process identity to avoid cumulative-series collisions across replicas. Process churn creates new resource series, as with the existing sidecar; there are at most 30 application label combinations per live process.

Export is best effort and limited to once per five minutes per instance, including failures. A 1s connect / 2s read timeout bounds the write attempt; ADC discovery/refresh can add time. A failed write retains cumulative samples for the next export. Request-based Cloud Run CPU may pause the worker after a response until another request arrives. Instance termination can lose queued signals and the unexported tail. Export can finish after request cancellation; measurements are diagnostic, not an accounting ledger. Do not interpret absent data as zero. The existing metrics sidecar helper is unsuitable here: it forces always-allocated CPU and adds a 1-vCPU/512-MiB collector.

After review:

1. Verify the attached runtime identity has `monitoring.timeSeries.create` and descriptor permissions. An IAM change is a separate owner action; this PR grants nothing.
2. Deploy in dev through the normal path and exercise synthetic sync attempts, including failures/retries. Verify descriptors are CUMULATIVE/DISTRIBUTION, fixed labels, count-preserving buckets and no auth failures. Confirm exporter scrape `up=1` and both services' duration/calls histograms in Prometheus. Determine the actual normalized exporter metric names from the dev scrape before creating dashboard queries.
3. After review, deploy observability alone in prod; compare service request latency/error rate before/after and wait a full day before sizing. Runtime flags require a normal deploy. Never test by reading customer content/logs or invoking api.omi.me.
4. Roll back by setting `SYNC_PHASE_METRICS_EXPORT_ENABLED=false` via the normal reviewed deploy; reverting the observability release also removes instrumentation/export filters.

Observability saves $0 directly and adds ingestion/CPU overhead. At 10 distributions per instance/five minutes, 80 billable bytes/distribution, 18–39 average instances from Oct 2–3 billed hours imply approximately **$31–66/month** ingestion before remaining free allotment, plus modest request/exporter CPU and Monitoring read charges. A sustained 68-instance ceiling with one active lane is ~$116/month. Mixed fresh/backfill/unknown lanes can increase this by up to 3x; dev acceptance must measure the actual active-series count and export overhead. The exporter read window grows from 2 to 10 minutes to cover this cadence; verify collection duration and pod CPU/memory because this also widens reads for existing application metrics.

## Memory headroom

The supplied `backend-sync-backfill-container-memory-utilizations.json` has daily merged linear histograms at 8 GiB. Bucket width is 1% of allocation; the highest nonempty bucket's upper bound is `index * 0.01 * 8 GiB`, not an exact maximum. Oct 2/3 mean is 0.732/0.748 GiB and p99 upper bound is 0.96 GiB. The full Sep 24–Oct 3 range includes an **Oct 1 sample below 1.76 GiB**. The earlier recent-day 1.12 GiB summary omitted that outlier.

At concurrency 3, 4 GiB leaves at least 2.24 GiB relative to that sampled upper bucket. 2 GiB leaves only 0.24 GiB (12%); reject the 2-GiB rollout. Minute samples do not rule out transient decode/PCM copies, downloaded audio or memory-backed temporary files. At concurrency 6, a deliberately conservative doubling of the complete 1.76-GiB sampled footprint is 3.52 GiB: just 0.48 GiB (12%) under 4 GiB, before unsampled bursts. This is a risk bound, not a load-test result; do not approve 4 GiB/concurrency 6 from these aggregates alone. No customer audio was read or replayed.

Memory-only rollout: backfill 8 → 4 GiB, keep 2 vCPU, concurrency 3, min/max 3/18 and request billing. Estimated saving `4 * $0.0000025 * 3600 * (180.8–269.1 h/day) * 30` = **$195–291/month** active memory, with additional idle saving possible. Compare a complete day with baseline for memory upper-tail, instance aborts/restarts, retries, job latency and queue age. Roll back the setting to 8 GiB or the previous serving revision through the normal path on any memory termination or persistent latency/retry regression.

## Concurrency and dispatch

Updated 2026-10-15 for Train 1: `.github/actions/sync-backfill-lifecycle/action.yml` sets revision max 40 **and** service max 40, concurrency 6, CPU 2, memory 8 GiB, min 3. Both queue create/update branches set 90 concurrent dispatches / 15 per second,5–60s retry backoff. This is source configuration; verify the applied revision, traffic, worker capacity and queue separately. The earlier 40/10 and concurrency 3 sizing proposals below are historical, not current settings.

The prior baseline was 60/10 and 18×6 slots. Release worker capacity before queue dispatch. Keep 90/ 15 as the persisted first step; later operator increases 135/20→180/25→200/25 require at least 15 min per step, durable-throughput evidence, <10% latency/retry regression, no OOM/capacity 429, unchanged GPU admission, and observed Firestore/Redis headroom. See [capacity and retirement runbook](sync-backfill-concurrency.md) for the exact queue rollback and flag-off behavior. Retire Redis-absent heads under the new guarded policy instead of consuming a full Cloud Tasks turn per expired job; this recovers capacity but does not itself recover audio or count as a completed transcript.

Do not combine this train with 4 GiB memory, concurrency >6, lower minima, GPU admission increases or fresh request-billing changes. The older cost/packing estimates in this document remain historical hypotheses, not Train 1 savings forecasts.

## Request-based CPU safety audit

**Do not switch backend-sync to request billing now.** Its shared app runs work outside request lifetime even when main sync dispatch uses Cloud Tasks. File/line pointers below name the audited source; additions can shift them. Re-audit on the reviewed deploy SHA.

| Work | Source | Lifetime and action needed |
| --- | --- | --- |
| Inline fresh pipeline fallback after 202 | `backend/routers/sync.py:1483` | Background pipeline can outlive admission response; remove inline fallback or durably queue it before switching CPU. |
| V1/v2 fair-use classifier | `backend/routers/sync.py:702`, `backend/utils/sync/pipeline.py:2374` | Fire-and-forget classification; durably dispatch and await admission. |
| Deferred syncing-blob janitor | `backend/utils/other/storage.py:550`, `backend/utils/other/deferred_delete.py:41` | 480-second delayed deletion on daemon thread; use durable cleanup/lifecycle with confirmed retention contract. |
| Audio precaching | `backend/utils/sync/playback.py:157`, `backend/utils/sync/playback.py:324` | Fire-and-forget storage/postprocess work after response; durably queue or explicitly disable with cache latency acceptance. |
| Sync reprocess webhook | `backend/utils/sync/pipeline.py:1085` | Submitted, not awaited; durable task or join within request. |
| Conversation vectors, action items, goal updates and webhook | `backend/utils/conversations/process_conversation.py:3291`, `:3293`, `:3305`, `:3310`, `:3342` | Conditional non-reprocess effects outlive parent; reprocess paths await some writes, but vectors/webhooks and shared routes still need audit/durable dispatch. |
| Conversation integration auto-sync | `backend/utils/conversations/process_conversation.py:2246`, `:2251` | Fire-and-forget integrations; queue separately. |
| Transcription shadow | `backend/utils/conversations/transcription_shadow.py:125` | Flag-dependent background work; disable on request-billed worker or use durable jobs. |
| Live STT fleet-health refresh and result/bench writes | `backend/main.py:356`, `backend/utils/stt/live_health.py:394`, `:545`, `:750` | Recurring/background; separate service role or scheduled durable refresh. |
| Batch-pressure refresh | `backend/main.py:357`, `backend/utils/stt/batch_pressure.py:73` | Periodic async task, env-dependent; move/disable by service role. |
| Executor health loop | `backend/main.py:362` | Periodic reporting; use request-bound metrics or worker role gating. |
| Startup deletion, finalization, stale processing/in-progress, BYOK and meeting receipt reconciles | `backend/main.py:365`, `:372`, `:376`, `:380`, `:384`, `:388` | Startup tasks are scheduled without waiting and can exceed startup CPU window; move to durable scheduler/worker. |
| Periodic deletion/finalization reconciles | `backend/main.py:371`, `:392` | Recurring repair work; move to durable scheduled requests first. |
| Proactive message dispatcher | `backend/main.py:393`, `backend/routers/listen/registry.py:49` | Infinite dispatcher loop; split service role / durable dispatch. |
| Prometheus loopback HTTP server | `backend/main.py:355`, `backend/utils/metrics.py:1379` | Thread only if port configured. New request-bound export does not depend on it. Existing sidecar forces instance billing. |
| Inline-run and Cloud Tasks lease heartbeats | `backend/utils/sync/pipeline.py:1978`, `backend/routers/sync.py:1865` | Cloud Tasks heartbeat is canceled/joined in handler finally; inline heartbeat follows the outliving pipeline. Retain request ownership and audit cancellation. |
| Conversation processing lease heartbeat | `backend/utils/conversations/lifecycle.py:347` | Context-managed thread stops/joins at guard exit; safe only if its owning work is request-bound. |
| Awaited sync segment thread-pool work | `backend/utils/sync/pipeline.py:2660` | Normal gather awaits work, but executor work can continue after cancellation/timeout; verify bounded I/O and durable retry/fencing on the final SHA. |

Exact producer callsites with enclosing functions: [static inventory](sync-request-lifetime-inventory.md).

The audit is conservative: all routers are registered on the shared app, so service name alone does not isolate execution. Production fresh currently has `cpu-throttling=false`; backfill has request-based CPU and inherits the same startup concerns already. The new exporter adds a best-effort daemon worker which can outlive a request; it must never be used for required accounting or as evidence that request billing is safe.

Potential fresh switch saves an illustrative **$400–1,500/month** at Oct 2–3 overlap/duty cycle, not an approved change. First make all required effects request-owned or durably queued, gate recurring shared-app work by service role, prove cold idle/retry/cancellation behavior in dev, and re-audit. Rollback if a future reviewed switch qualifies: restore always-allocated CPU and the prior revision.

## Minimum instances

Recommend **backfill 3 → 1** first after backlog and concurrency stabilize; consider 0 only after measuring cold-start and queue-completion acceptance. At 8 GiB, two fully idle minima cost up to **$130/month**; at 4 GiB up to **$78/month**. A 3 → 0 option has respective ceilings **$194/$117/month**. Load can keep those instances active anyway, so realized savings may be zero. One warm instance reduces first-job cold-start exposure; zero is suitable only if delayed historical completion is acceptable. Restore min=3 on queue-age/cold-start regression.

Recommend **fresh revision min 5 → 3**, retaining service min=1; consider 1 only after measured cold-start/admission latency. Revision and service minima are distinct, not additive. At current 2-CPU/8-GiB always-on billing, 5 → 3 idle ceiling is **$270/month**, 5 → 1 **$539/month**. A shared app's cold startup includes dependencies/provider/reconciler initialization; no measured cold-start SLO was supplied. Keep CPU always allocated. Roll back revision min=5 on admission p95/cold-start regression. These are recommendations, not config changes in this lane.

Deploy order: review → dev export/scrape acceptance → observability prod baseline → backfill memory-only 4 GiB at concurrency 3 → isolated concurrency 6 experiment at 8 GiB → qualify 4 GiB/concurrency 6 → lower backfill minimum → lower fresh minimum. Fresh request billing remains blocked pending lifecycle changes.

Sources: [Cloud Run pricing](https://cloud.google.com/run/pricing), [billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings), [metric kinds/types](https://docs.cloud.google.com/monitoring/api/v3/kinds-and-types), [Monitoring pricing](https://cloud.google.com/products/observability/pricing). Aggregate evidence: coordinator-provided `cost-opps/REPORT.md` and `evidence/` under scratchpad `845e572e-a7fa-424b-b7ae-a05320492825`. Current config projected read confirmed both services serving `9bf89d3-37199314132-1` with reported min/max/concurrency/CPU modes; no production mutation occurred.
