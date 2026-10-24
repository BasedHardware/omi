# Batch pipeline worker

Default-off PR #21674. Claude leads shipment; Grok reviews pushes. Local tests,
index declarations, GPU benchmarks and production qualification are separate evidence.

## Current flow and measured bottlenecks

The legacy sync router saves uploads, claims a 45-day content ledger, creates
Redis progress and dispatches Cloud Tasks. The backfill sequencer serializes
owners before decode/VAD/STT and conversation merge. Redis run epochs fence
worker mutations. `diarizer/batch_main.py` is an independent batch service.

Lead's October 15 aggregate snapshot: approximately 1.07M jobs, 983 owners,
oldest six days; David reports 47 hours. Unbound/LEGACY capture classification
routes approximately 99% to backfill. One job per owner, queue concurrency
40 (now 60), and 18 Cloud Run instances × 6 concurrency at approximately
13 seconds/job constrain dispatch. Supplied GPU utilization is approximately
7%; batch pyannote T4 RTF is 0.04 and Parakeet L4 RTF 0.0025. The supplied
1.5 seconds/audio-hour batch estimate is not qualified full-chain capacity.
`SYNC_LEGACY_FRESH_ENABLED` remains independently owned; its classification
feeds this queue unchanged.

## Target, ownership and work units

Uploads land before compute; dedicated GPU workers pull across owners. Fresh
has strict priority over recent backfill (known age ≤7 days), then deep backfill
(older/unknown age). Duration-cost deficit round robin prevents one heavy owner
from monopolizing admission to compute. Compute is parallel per owner; merge
and projection preserve the order of admitted captures.

A owns cohort config, intake, scheduler/store, ordered log, serving supervision,
heartbeat, metrics, query/index declarations and associated tests. B owns GPU
chain, encrypted artifact adapters, model/runtime packaging and dedicated GPU
chart. C owns legacy-compatible projection, content-ledger integration,
enrichment and client completion. D owns deletion/protection fences, erasure
and retention. Shared types meet in `utils.batch_pipeline.contracts`; commits
name owned paths, preserve peers' edits and never stash or force-push.

Intake strictly decodes every uploaded frame to canonical PCM WAV, retaining
capture clocks. Consecutive files are packed into conversation/capture spans
up to one hour; small gaps become silence, larger gaps/overlaps start another
unit. Longer captures split at exact sample boundaries. These are queue units,
not five-minute chunks; B independently packs short model windows by length.
Original geolocation, recording-lineage and capture proof metadata are frozen
in a bounded ancillary WAV context chunk, encrypted with the audio.
Malformed/missing capture clocks or incomplete decode refuse the upload.
BYOK refuses cloud batch intake until a private worker path exists.

## Durable model and admission

Production/dev namespaces match explicit runtime stage and customer-data
Firestore; test namespaces require injected loopback emulator clients.
Jobs contain immutable segment/owner/capture identity, duration, priority,
unit kind, source conversation, privacy generation and encrypted audio URI.
Mutable state contains attempt, fenced token/deadline, retry time, result URI,
queue link and merge status. No transcript/audio bodies enter queue metadata.

One transaction binds content-ledger `dispatch_protocol=batch_v1`, the complete
sibling set and frozen projection binding, queue entries and durable
`intakes/bp_<job>` status. Simultaneous legacy/batch claims serialize on that
same content document. A duplicate follows its existing owner. Preexisting legacy receipts retain
the original cap, retry and missing-Redis recovery path; they never enter batch
staging. This is recorded protocol selection, not fallback after batch failure. Legacy claim,
bind and release paths refuse batch ownership even after Redis expiry or
cohort rollback. Pending batch claims have no TTL; completion starts retention.
An ambiguous admission reply never releases or dispatches a legacy twin.

Owner/class FIFO queues retain a 30-second duration DRR deficit. Owner-hash
selects one of 64 control documents, each holding three priority rings. Pull
queries eligible shards by minimum per-class virtual service, then transacts
only the selected shard. Service advances by audio seconds/active owners,
sharing capacity fairly across differently populated shards; DRR shares within
a shard. Idle shards rejoin at the indexed maximum service frontier, preventing
stale-history penalties or repeated empty/rejoin credit resets. Fresh shards are exhausted before lower classes. Ineligible heads
rotate; pool-specific 30s pauses avoid hot polling. Admission unpauses its shard.
Recovery migrates old global rings in bounded metadata-only transactions.

## Lease, merge and late-capture policy

Leases last 120s; concurrent heartbeats renew every 20s. Lost ownership forbids
publication. Explicit worker failures retry with exponential backoff capped at
600s until the lease attempt reaches `BATCH_PIPELINE_MAX_ATTEMPTS` (default 5,
valid integer 1–20; invalid values use 5). Configure the same ceiling on GPU
workers and serving API hosts; a restart is required to change it. Policy denials
and fatal-GPU deferrals refund the lease attempt. Lease expiry alone remains
recoverable and does not quarantine; the ceiling is checked on explicit failure.
Alert on first-failure age over 600s until success or terminal quarantine.
Fenced recovery records move to `privacy_blocked` in a separate transaction
that rechecks the fence; other owners continue. D still owns erasure.
Authenticated internal `redrive-dead` and owner status polling redrive historical
dead heads without skipping audio. Shutdown drains non-preemptible compute.

Merge selects the earliest currently pending `(capture_at, segment_id)`, fenced
by the owner revision. Each entry has a stable ID, predecessor and sequence;
C follows predecessors idempotently. A late capture is admitted normally (202),
retains its original clock and appends after the committed log tail. The capture
high watermark never regresses; committed history is never rewritten. Ordering
covers available pending captures, not unknown device audio.
`conversations.dart:810-923` handles only `sync_content_in_progress`409;
`local_wal_sync.dart` retains audio after202 and deletes only after completion.
No new client error contract is required.

| Firestore step, one segment | Reads (approximate) | Writes |
| --- | --- | --- |
| Authorize/register encrypted artifact |10|1|
| Admit |6 plus one frontier read on idle-shard activation|7; one owner shard|
| Pull |9 plus visited-owner privacy checks|job, queue, one shard|
| Heartbeat20s |6|1|
| Complete + ordered merge |14|4|
| Projection complete |15 plus conversation reads|ledger, usage, job, expiry|

Counts exclude retries/contention; empty priority probes add index reads.
Each metric refresh uses nine bounded queries (GPU pump cadence 15s). No ordinary admission/pull
writes the legacy global control; shard contention/load still needs qualification.

## Terminal quarantine and the visible gap

At the ceiling, one fenced transaction records `state=quarantined`,
`quarantine_reason=worker_failed`, `quarantined_at` and `recovery_state=held`.
`worker_failed` is a closed scheduler code; the worker's content-safe diagnostic
log owns any more specific model reason. The transaction clears the lease token,
clears `merge_pending`, removes retry age and increments the owner revision.
This serializes the skip against admission/merge; it does not manufacture a
result URI, silence receipt, successful log entry or projection watermark.
Stale completion, heartbeat, historical-dead redrive and repeated status polls
cannot revive this unit. Existing retries above the ceiling quarantine on their
next explicit failure, rather than on deployment or a metadata scan.

The successful result log links the successful unit before the gap directly to
the next successful unit. Earlier unfinished successful captures still block;
late-capture/high-watermark semantics are unchanged. A successful sibling of the
failed upload still persists/enriches through normal assignment. Once ready it
moves to `projection_state=quarantine_held`, retaining its ready receipt/cursor
but leaving the bounded projection sweep. Later uploads can project normally.
The failed upload cannot pass all-sibling accounting/client completion.

**What the conversation shows:** the quarantined unit performs no conversation
or transcript mutation. Existing live/legacy words remain; if none exist for
that span, it has no batch transcript words and no invented placeholder. Other
successful units use normal assignment. The durable upload status is `failed`,
with `failed_segments` and the closed `batch_worker_quarantined` error, no success
result and no further polling delay. This is a transcript gap, not recovery.
Once fenced recovery (below) owns the unit, recovery states `held`, `prepared`
and `running` poll as `processing` with a nonzero `poll_after_ms`; only a
terminal quarantine such as `failed_held` reports `failed`.

No legacy transcription is dispatched in this change. The upload-wide
`dispatch_protocol=batch_v1` claim and run fence remain intact; duplicate
uploads and legacy run binding cannot create a second projection. Quarantined
units and their held siblings retain registered encrypted artifacts/metadata
without completion TTL or cleanup. Privacy deletion still overrides retention.
Successful siblings' upload-wide usage completion also remains held. Operators
must track these retained obligations until recovery ships; flag rollback does
not release them or erase their audio.

`omi_batch_pipeline_events_total{event="quarantined"}` and
`{event="recovery_held"}` count accepted transitions, with content-free
`event=batch_quarantined reason=worker_failed attempt=<integer> recovery=held`
and `event=batch_recovery outcome=held reason=handoff_not_implemented` logs.
They emit after the transaction, outside worker exception scopes, with swallowed
telemetry failures. Repeated/stale fail calls do not emit again. Counters/logs
are best effort; durable quarantined job records are the authoritative census
(including an ambiguous commit reply or process death before telemetry).

### Fenced recovery follow-up

The existing legacy claim/run entry points own an entire upload, not one batch
unit. Clearing that claim or dispatching the whole upload could replay already
projected siblings. Recovery therefore needs a separate per-unit intent, keyed
by the immutable segment ID, atomically created only for a quarantined job with
no result/assignment receipt. The intent must carry a generation/run token and
privacy fence, keep ordinary batch pull/complete denied, and reuse the existing
sync prerecorded STT client on that unit's registered audio. Its result must
publish through the same stable batch assignment identity under the recovery
fence, never through a second whole-upload legacy claim. Repeated or lost-reply
handoffs must reconcile that durable result rather than transcribe/project twice.
Because later captures may already have committed, publish through the existing
late-capture log rules, preserving original clocks. Resume held sibling sweeps
and all-sibling accounting/retention only after every recovered unit has a durable
projection receipt. Validate intent retry, lease loss, privacy revocation,
late capture, crash-after-persist and exactly-once billing before enabling this
path. This follow-up is deliberately outside this quarantine-and-skip PR.

## Worker and protection interfaces

`WorkItem` names segment/owner, capture time, encrypted audio URI, duration,
priority, unit kind, optional conversation and pinned privacy generation.
`LeasedWork` adds token/attempt/deadline. B implements
`process_batch(Sequence[WorkItem]) -> Sequence[WorkResult]`; results may arrive
out of order. Each result supplies segment ID, encrypted URI and success/silence.
Missing/failed items retry up to the quarantine ceiling; decode/provider failures never become silence.

Inside one locked flight, artifact IO overlaps GPU work: up to
`BATCH_PIPELINE_WORKER_IO_CONCURRENCY` (default 3, `1` = serial, max 8) items
fetch/decrypt/decode ahead of the item on the GPU, and as many encrypted result
writes run while later items diarize. Prefetch stays inside the existing
two-audio-hour decode group and, beyond the next item, within 1800 audio seconds
ahead. Model calls, CUDA work and the chain lock stay on the calling thread; a
fatal GPU error waits for outstanding IO before the flight raises.

B's dedicated process composes A's `Pump`, a fresh `PoolCapacity` callback and
CUDA synchronization. Optional service-OIDC pull/heartbeat/complete/fail APIs
use the same contract. Production jobs require an OIDC compute-admission seal from the backend before
inference. Fresh restrictions are rechecked; backfill reserves the full-content
audio upper bound with existing content-idempotent policy. Refusals defer without
using failure attempts. No configured policy client means no GPU spend.
C projection runs on the backend, including durable
sweep and legacy playback/enrichment. D checks account/source deletion,
protection and generation inside each mutation transaction. Encrypted,
owner-bound, generation-pinned objects have a pre-upload deletion outbox.
Completion-only retention never expires pending work.

## Capacity and autoscaling

Conversation units run only on dedicated batch GPUs. Shared-live stays off;
future admission requires explicit capture spans ≤120 seconds, fresh slack,
empty live queue, utilization/memory headroom and one durable reservation per
physical GPU. Expired compute leases do not release GPU ownership: only the
hardware owner acknowledges CUDA idle. Non-preemptible work never moves onto
live Parakeet pods merely because it is 03:00Z. The approximately 25% listen
trough is an opportunity to measure slack, not permission to run.

Export oldest pending/ready/retry age per class, freshness, admission-to-lease owner
wait, transition rates/jobs per second, and GPU utilization/headroom. No owner
labels. Autoscale on ready-age with fresh/recent/deep targets 30/300/3600 seconds;
reject stale samples. B's dedicated chart documents the external-metric HPA.
CPU is not the scale signal; non-preemptible batch latency still needs bounds.

## Stage profiling (metrics-only)

`BATCH_PIPELINE_STAGE_PROFILING_ENABLED` gates the dedicated runtime's
`omi_batch_pipeline_stage_seconds{stage=...}` wall-clock histogram. Default on
only when `OMI_ENV_STAGE=dev`; prod and an unset stage stay off, and an explicit
`true`/`false` (1/0, on/off, yes/no; malformed values fall back to the stage
default) overrides, so local/offline can opt in. The histogram is created once
at worker startup on the worker's own explicit `CollectorRegistry` — the same
`/metrics` endpoint as the queue gauges — and a disabled or unwired
`StageTimings` instance is a pure pass-through: no runtime behavior, precision,
or concurrency change, and no scrape difference outside dev.

Pump-side stages: `pump_cycle` (one full maintain+flight pass), `maintenance`
(expired-lease recovery, result_ready sweep, hold pages, leader lease),
`pull` (the claim transaction), `admission` (compute-admission authorization),
`renew` (lease heartbeat rechecks), `publication` (every lease-fenced scheduler
transition: defer/fail/complete/release), `ordered_merge` (per-owner commits),
`projection` (pending projection and on-committed callbacks), and
`worker_flight` (executor wait plus the whole GPU chain, including its CUDA
quiescence `cuda_sync`). The pump's GPU-slot wait precedes `worker_flight`
and is included only in its parent `pump_cycle`, not the worker timer.
Worker-chain leaves: `fetch_decode` (download+decrypt+decode of one unit),
`vad`, `windows` (speech window assembly), `asr` (batched `transcribe_batch`),
`asr_recovery` (the padded retry, including cap-dispatch callbacks),
`flight_segment`/`flight_diarize` (packed pyannote segmentation and packed
embedding+clustering passes), `diarize` (serial per-unit diarization including
speech compaction), `persist` (encrypt+upload), `cuda_sync` (the pre-existing
final synchronize; profiling adds no new GPU synchronization).

Timings include failed operations and executor wait; a prefetched fetch/decode
and a submitted persist are measured where they execute (background IO threads),
not at the later consuming wait. `pump_cycle` contains the whole pass and
`worker_flight` contains the worker leaves and CUDA synchronization: never add
parent and child sums. `asr`, `asr_recovery` and the packed flight stages are
batched across windows/units of several leased jobs, so one observation is not
one lease: divide a stage's `_sum` rate by the worker-scoped leased-event rate
(`omi_batch_pipeline_events_total{event="leased"}`) for an amortized
seconds-per-leased-job view, and use `_count` for per-call means. Model leaves
measure host-observed wall time, not isolated CUDA kernel occupancy. Speaker
embedding is timed at pyannote's existing `get_embeddings` hook (`embedding`),
and at the shared-trunk packed forward (`flight_embedding`). The latter is
nested inside `embedding` on a speech-only shared-trunk call; never add them.
Full-unit packed calls may compute `flight_embedding` before cached per-unit
hook reads. Both are children of diarization, not additional critical-path time.
The worker also exposes `download_metadata`, `download`, `decrypt`, `decode`,
`encrypt`, `artifact_register` and `upload` on the actual artifact IO thread.
Download metadata is a separate GCS request. Encryption/upload/registration are
children of `persist`; download/decrypt/decode are children of `fetch_decode`.
Outside the dedicated worker's active context these artifact timers are no-ops.
Retained-audio manifests also time each generation-pinned source download,
framed decryption and codec decode/resample. One lease may contain several
source objects, so these leaf percentiles are per operation, not per lease.
Per-call p50/p95 for batched stages are batch percentiles; dividing them by
batch size does not produce per-lease percentiles. Use the summed-time/leased
count normalization above for amortized per-lease cost.
Unattributed worker time includes validation, packing, policy callbacks, the
live-reuse lookup, silence inspection and left-context assembly. Optional or
skipped stages (silence units, packed-flight fallbacks, recovery paths not
taken) emit no samples. No owner, segment, URI, or exception labels exist, and
a telemetry failure (clock or observe) is swallowed: it can never invalidate
compute or a durable transition.

## Flags, rollout and rollback

Admission requires `BATCH_PIPELINE_ENABLED=true` plus explicit UID allowlist or
stable SHA-256 percentage; defaults are false/empty/zero. Configuration of
providers alone cannot select real uploads. `BATCH_PIPELINE_SERVING_ENABLED`
and B's worker switch independently default off. Enable qualified drain/worker
infrastructure before a cohort; keep them enabled during admission rollback.
Shared-live and VAD compaction remain off.

Lead's rollout: hermetic/emulator → isolated dev synthetic identity → David
only → 1% → 5% → all, at least 12 hours between cohorts. Require production
indexes READY, retirement of pre-protocol intake revisions, privacy/deletion,
playback, accounting, lineage and full-chain
quality/capacity acceptance before expansion. Inspect per-class age, per-owner
wait, throughput, GPU use, errors, duplicate/projected receipts and live latency.
Multipart projection/deletion still requires rollout qualification.
Turning admission off returns new unowned uploads to legacy; existing batch
claims drain through their recorded protocol. Never copy in-flight work into
legacy or purge pending artifacts to roll back. Detailed RPC/index/operator
settings are in `batch-pipeline-serving.md`; no merge/deploy is authorized here.

With dark `BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED=true`, both exhausted
padded `empty_asr` and `no_owned_words` hand off immediately to the existing
fenced CPU recovery lane. Strict local VAD on the original unit makes the final
silence decision; the GPU worker never infers silence from empty text or from
words outside its core. Speech gets the once-only legacy recovery attempt.
See [serving recovery](batch-pipeline-serving.md#dark-empty-asr-disposition) for
closed diagnostics, historical held-unit disposition and rollback semantics.
