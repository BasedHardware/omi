# Held audio durability and server redrive

Owner: backend sync. Source incident: #21488 / #22198 (held recovery depended on
process-local continuations). This runbook describes code defaults, not a deployed
rollout. The enforcement cohort deadline remains **2026-10-19 18:00 UTC**; neither
`STT_CAP_DISPATCH_ENFORCEMENT` nor `LADDER_V1_BUDGET_ENFORCEMENT_ENABLED` is enabled
by this change.

Held-choice API acceptance and its separate DEC-BTR-005 graduation schedule are
tracked by the [hermetic acceptance and ramp protocol](held-content-acceptance.md).
The dated dispatch-enforcement ramp below does not authorize that API rollout.

## Admission scope and original custody lane

The [cohort/lane contract and dazheng-owned ramp](../stt-cap-dispatch.md#cohort-and-lane-rollout-david-2026-10-18)
is authoritative: coordinator test accounts -> 1% -> 5% for three hours -> 25% ->
100%, live only. The checkpoint remains 2026-10-19 18:00 UTC; report a missed soak
or checkpoint rather than widening automatically. Monitor held-audio count,
backlog stalls, live STT errors and client 5xx at every expansion. Non-live stays
disabled pending the GPU-lock authorization change blocked by Nemotron #22352 and
approved widening. Neither admission switch bypasses this scope.

Recovery reads encrypted `origin=live|sync|batch` before claim/download and passes
that original lane to every segment admission/retry. Legacy absent origin means
sync (all live custody versions explicitly wrote live); explicit unknown/null
origin stays paused. Never infer origin from device source, freshness, or the
batch execution method. Excluded owners/holds retain audio and consent without
consuming the chosen estimate. Rollback both admission switches false or clear
the cohort, preserving current custody readers and sealing/cleanup redrive.
A reserved excluded source yields to selected work only after the worker/store
transaction proves no dispatch ever started, rechecks choice ownership and the
current month, and atomically refunds its chosen estimate once. Unlimited choices
stay unlimited. Source rows remain queued; cursor rewind preserves widening.
Any audio receipt/ingest, nonzero lease, presence of a `lease_token` or
`piece_plan` key (including empty/null), missing/nonzero `next_attempt_at`, text
claim history, unknown
origin, missing source/legacy lease proof or failed read retains the reservation;
these narrower ambiguous cases can still block the choice. No usage-ledger refund
or automatic provider repeat is introduced. See the dispatch contract for the
exact proof and lost-response behavior. Page completion consumes an accepted
same-month pending upgrade before retaining/rewinding skipped scope; an actual
reservation still blocks upgrade consumption. No wrong-month intent creates
consent, and excluded rows alone never finish the choice to waiting-choice.

This change adds no scheduler lifecycle or indexes; the pre-existing job and
index prerequisites below are unchanged and are not deployed by this lane.

## Deployment prerequisites

1. Merge and approve the production Firestore index apply. Three new ascending
   collection-group field indexes are declared: `processing_backlog.state`,
   `stt_cap_holds.state`, and `stt_cap_holds.staging_cleanup`. The generated manifest
   retains collection indexes in both directions. Wait for readiness before images
   that use the new queries ship. The emulator does not establish index readiness.
2. Ship the updated backend sync reader/recovery image before listen starts
   emitting fragment sources; then ship listen and pusher through their existing
   image workflows. With both enforcement flags still off, admit all updated
   readers before activating the planned cap cohort.
   Pusher receives only the lightweight shutdown registry (stdlib dependencies).
   Listen owns denied capture PCM; pusher receives admitted audio/transcripts and
   has no second cap-held PCM buffer. Both entrypoint shutdowns flush registered
   sinks before draining background tasks and closing HTTP clients.
3. Reconcile the new production-only Scheduler-as-code job
   `cap-hold-durable-redrive`. It POSTs `/v2/cap-hold-recovery/sweep` every two
   minutes with the existing sync Tasks invoker OIDC identity/audience. Its attempt
   deadline is 1740 seconds; the backend HTTP bound is 1710 seconds. Do not create
   a dev job: dev shares the customer data plane. No new queue/IAM secret is needed.
4. Verify the deployed source SHA, scheduler receipt and `event=cap_hold_redrive`
   logs before enabling the already-planned enforcement cohort. Verify a consented
   synthetic backlog progresses across instance replacement without client traffic.
   This implementation lane did not run those deployment checks.

Kill switches default **on**: `CAP_HOLD_DURABLE_REDRIVE_ENABLED=false` stops all
sweep reads/work; `CAP_HOLD_LIVE_FRAGMENT_ENABLED=false` restores the original
60-second immutable source writer for new sessions. Turning fragments off does
not retire already durable staging rows: leave redrive on so they seal/clean up.
The existing admission flags still own paid processing and user eligibility.
Use the writer kill switch for rollback; retain the updated reader while staged
or composed sources exist. An old binary does not understand the explicit
fragment clock layout and is not a qualified reader rollback for those sources.

## Recovery ownership and bounds

A committed `processing_backlog/current` choice is the queue. The sweep never
calls choose, creates upgrade intent, extends cutoff or adopts a new month. It
visits existing `state=processing` summaries, then awaits the existing worker
with up to five owners concurrently on existing executors. Each visit considers
up to 100 candidates in ten-row audio/text pages, with a monotonic 900-second
budget checked before each next candidate and frozen audio piece. A reserved
item resumes first and also obeys the piece budget. No new compute is added. Current reservations are retried before a new page;
the existing UID worker lease and per-hold/per-text leases deduplicate concurrent
sweeps/client paths. The month, chosen estimate, reservation, cursors, allowance
and abuse checks remain authoritative. A busy or killed worker's 30-minute lease
must expire before another owner may run. There is no 60-second timer or
fire-and-forget self-respawn. A productive bounded visit leaves its choice processing. Pre-cutoff staging/sealing
sources are visible in the same bounded audio query and keep the choice open
without advancing past that source. Sealing preserves the original creation and
listing times; it does not move authorized audio beyond the cutoff. A source
created after cutoff remains excluded. Waiting-choice users are never processed.

Each of three independent discovery streams (choices, staging/sealing, cleanup)
reads at most five rows per sweep, ordered by full document name with a durable
keyset cursor. Each wraps on a short/empty page. The cursor advances before work,
so a blocked owner cannot hide later existing users. A crash can defer that page
until the next rotation; it cannot erase intent. For N queued owners, discovery
latency is roughly `ceil(N/5)` successful scheduler executions; blocked choices
also consume visits. A long request delays subsequent scheduler delivery.
[Cloud Scheduler's Job.schedule contract](https://docs.cloud.google.com/scheduler/docs/reference/rpc/google.cloud.scheduler.v1#job)
serializes regular executions of the same job: a later scheduled execution waits
for the current one to finish. This is bounded fair recovery, not a per-user
two-minute SLA. A single owner's 100
short items can now drain in one visit (plus a later no-op finish visit at an exact
100-item boundary), rather than a minimum 200 minutes. Slow calls constrain this:
900 seconds permits about three 300-second provider calls before the next-piece
check stops the visit. Modulate has a 300-second read timeout (Parakeet 120),
plus connect/write/pool timeouts; these are per-phase IO limits, not an absolute
wall deadline for a trickling response. A call started just before budget expiry
may still add its adapter timeouts plus URL download/codec/ingest/finalization IO. Concurrent owner visits
avoid multiplying this provider tail by five; the 1710-second endpoint and
1740-second scheduler deadlines remain outer guards, not guaranteed completion
for arbitrary slow storage/LLM service. Existing executor queues can add latency;
no throughput or two-minute SLA is claimed under saturation. Budget expiry does
not cancel a billable call mid-flight or clear a reservation. A killed owner can
still wait for its 30-minute lease plus a discovery rotation. Endpoints await work;
failed requests may be retried and never acknowledge memory-only work as done.

## Provider spend and uncertainty

Current serving Modulate and Parakeet adapters POST synchronous batch requests.
They expose no implemented idempotency key, job lookup or replay/result retrieval
contract. The [official Modulate batch OpenAPI](https://github.com/modulate-ai/modulate-velma-transcribe-batch/blob/main/docs/velma-2-stt-batch-openapi.yaml)
declares a completed synchronous response and no retrieval/idempotency parameter
for this exact endpoint; Parakeet's in-tree `/v1/transcribe` and `/v2/transcribe`
return synchronous results without such a contract. A local request ID or dispatch marker cannot prove whether the vendor
accepted/charged/completed a request when a process dies before the reply.

Held recovery now disables nested URL/provider retries, persists dispatch-started
under the exact lease/attempt, and checkpoints an **encrypted** nonempty provider
result before parsing/ingestion. A restart reuses this result and the original
provider/model/usage identity, then uses the normal idempotent ingest proof and
usage key. An empty response is checkpointed as `provider_empty` with
`provider_completed_at` and is never cached as a replayable result; because that
fenced checkpoint proves the vendor finished, recovery settles the piece as a
transcribed, no-content receipt (`settled_empty`) with no usage and no second
dispatch, on the same pass or when a later pass resumes the `dispatched` receipt.
The checkpoint is written only for a reply the adapter validated as the
provider's success shape with zero words; a 2xx body that is missing or mistypes
those fields raises inside the adapter, so no completion checkpoint exists and
the dispatch takes the ambiguous path below rather than settling and purging.

Caching measures the **whole proposed Firestore document** using the installed
SDK encoded-map Value envelope, including existing encrypted results, plan and
receipts. Its serialized size conservatively exceeds the document field encoding
by the outer map wrapper (verified with the real SDK/emulator).
A new cache may grow it to at most **768 KiB**, leaving 256 KiB of the 1 MiB
Firestore limit for ingest proofs and subsequent receipt fields. Existing cached
results are preserved. Ingest proofs omit duplicate result ciphertext, and a
known successful transcription receipt retires that piece's cache only after
ingestion succeeds. This is a cache-addition budget, not a new bound on arbitrary
pre-existing plan/response metadata.

An oversized single result or an aggregate budget miss records
`provider_cache_omitted` under the same lease/attempt, emits shared degraded
fallback telemetry, and immediately continues ordinary parsing/ingestion with
the usable response. It neither raises a size error nor dispatches again for
cache capacity. For these uncached responses the residual uncertainty window
extends **through atomic ingest proof**, rather than ending at result checkpoint.
A crash within it can spend once more under the same two-attempt bound. A marker
alone cannot reconstruct the transcript; no data is silently acknowledged or
left in an endless cached-empty loop. Cache-omitted results add no GCS objects,
retention/delete authorities or storage quotas.

The irreducible window is vendor acceptance through successful result checkpoint.
After a kill there, recovery waits 30 minutes and checks the atomic ingest proof.
Without proof, it permits one additional funded application dispatch. Therefore
one frozen piece can cause **at most two billable STT POST attempts** (one duplicate)
under these current adapters, excluding vendor-internal billing behavior. Parakeet
may probe v2 then v1 after 404; the 404 is routing discovery, not completed STT.
A second uncertain attempt (no completion checkpoint) becomes explicitly
`failed_reconciliation` and retains audio; it is terminal, not a silent
successful transcript. This residual
operator reconciliation obligation remains visible in the held summary. Do not
clear markers or purge audio to force progress, and do not promise exactly-once
vendor spend without a supported provider contract. Provider-result checkpoints
add two fenced writes/six authority+receipt reads per fresh successful piece;
ordinary ingest, usage and source-recovery operations are separate.

## Live custody, immutable publication and capacity

Accepted volatile PCM is bounded to **15 seconds aggregate per sink**. Ingress
splits at the exact sample and awaits persistence before accepting the tail. A
one-second updater flushes aged partial buffers, so a nearly-full partial can be
up to about 16 wall seconds old during scheduler jitter, plus bounded codec/IO
latency; accepted sample duration remains at most 15 seconds. SIGKILL can still
lose the not-yet-durable fragment. This is not a client acknowledgement protocol.

Every at-most-15-second fragment is independently encoded at 16 kbit/s Opus,
limited to 32 KiB plus its 32-byte encryption frame. Four fragments share one
owner/rate/channel/month/continuous-clock group. Each fragment is immutable and
its durable staging document records exact byte/frame layout. Only staging rows
may grow. Seal first freezes the row as `sealing`, then composes ciphertext frames
into one generation-zero immutable minute source and atomically publishes the
hold plus summary. Recovery decrypts the framing and decodes each Opus clock
separately before joining exact PCM frames. No re-encoding, second recovered-audio
copy, changed VAD offsets or mutable published sources are introduced.

Writer expiry is 120 seconds. The independent sweep seals abandoned staging or
sealing rows even with enforcement off or no processing choice. A separate
cleanup stream resumes deletion after a kill following publication. Original
privacy/deletion fences span append/freeze/compose publication; existing account
deletion still owns every generation under `chunks/{uid}/` and these subcollections.
Cleanup never recreates a source. Purged receipts prevent late publication.

Reserve 64 retained-source slots plus **one overlap slot** per writer block. Each
slot is 128 KiB + 128 bytes; the extra covers four fragments coexisting with their
composed source. A writer cannot advance until that group's cleanup succeeds.
Slots are consumed after durable stage/publication receipt, never before upload.
Retries keep the same fragment and acquisition identities. An unresolved reply
prevents refund; clean partial close refunds unused slots plus the overlap slot.
A full block conservatively leaves one spare reserved. A killed writer strands
its whole block, covering bounded orphan objects even when killed between GCS
upload and the transaction commit. Such unreachable orphans remain until account
deletion; no unbounded retry identity/object creation is allowed. The **8 GiB /
100,000 group quota per user/capture UTC month** remains hard, shared across
sessions/channels. It is cumulative reservation capacity, not replenished by STT.
Old v3 sources keep their prior reservation rules. Retained months accumulate;
there is no lifetime retention cap.

Socket close flushes/seals tails. Owner cancellation leaves the sink-owned
publication task holding its scratch files and lock until the executor completes;
subsequent close awaits that lock. Both lifespans give registered tails a 30-second
flush window before their existing 10-second background drain. After the 30-second
wait the coordinator cancels close waiters and returns without an unbounded
cancellation gather, even if a waiter suppresses cancellation. It retains and
observes their completion; the separately shielded publication keeps scratch,
PCM and the sink lock during normal waiter cancellation. Scratch creation,
encoding, upload and cleanup belong to one synchronous storage-executor leaf, so
even direct event-loop cancellation of the publication task cannot unlink a file
still used by the executor. A cancelled waiter leaves uncertain capacity reserved
and stable publication IDs available for retry. It does not delete the upload's
file to meet the coordinator deadline. GKE listen and pusher have a 120-second
termination grace. Listen's preStop sleeps for 15 seconds; pusher first calls its
drain endpoint with `curl -m 5`, then sleeps for 15 seconds, so budget up to
20 seconds for pusher preStop. Allowing the full 60-second uvicorn connection/session
drain leaves nominal lifespan margins of `120 - 15 - 60 = 45` seconds for listen
and `120 - 20 - 60 = 40` seconds for pusher, before process and scheduling overhead.
Budgeting 30 seconds for coordinator flush followed by 10 seconds for background
drain consumes pusher's nominal margin; completion before hard termination is not
guaranteed. Pusher owns no second cap-held PCM sink.
SIGKILL and a flush exceeding the grace can lose the last volatile
fragment, while staging remains recoverable after the 120-second writer expiry
and its next bounded staging discovery rotation. The 30-second coordinator bound
is not a guarantee that a parked upload finishes before process termination;
Cloud Run hard termination may supply less grace than the GKE configuration. Flush errors log and propagate to
socket close (1011); they never increment the published counter or report custody
success. Closing clients does not authorize deleting undurable PCM.

## Measured operation cost and tradeoff

`backend/scripts/cap_hold_durability_emulator_test.py` runs only against a loopback
`demo-held-audio` Firestore emulator. Actual SDK reads/transaction writes/direct
cleanup writes and nested privacy fences are counted; GCS is a deterministic
adapter. For 64 continuous full minutes including summary readiness and quota
acquisition: **1221 reads / 514 writes / 256 fragment uploads / 64 composes / 256
fragment deletes / 64 retained objects**. Per minute: **19.078125 reads, 8.03125
writes, four uploads, one compose and one retained source**. Short sockets,
clock/owner/channel/month boundaries, retries and contention add operations.

Using the prior v4 report's illustrative 2026-10-18 us-central1 list rates (not a
new invoice/rate verification): Firestore $0.03/100k reads, $0.09/100k writes;
GCS Class A $0.005/1000, Standard $0.02/GiB-month, deletes free. This gives roughly
**$0.002277/capped hour in custody operations**, versus v4's $0.000450 for hourly
sockets. Add roughly $0.000147/hour of retained source storage at the 128 KiB +
128-byte ceiling for a full normalized retention month, and the unchanged 8 KiB
per-hold metadata/index planning allowance (~$0.000070/hour): **~$0.00249/capped
hour**, excluding STT, recovery, compute, egress, backup/PITR and retries.

This deliberately pays about $0.00183/hour more for a fourfold smaller volatile
window while retaining one full source object/minute. Four permanent short objects
would multiply metadata/retained objects as well. Compose adds no plaintext
processing. Temporary fragment byte-days are small without version retention;
seven-day soft-delete retention of staged fragments can add roughly 7/30 of the
retained-source storage term (~$0.000034/hour at the ceiling). Noncurrent versions,
regional settings and actual compression/wear duration must be measured before
cohort expansion. No production data or bucket settings were read for this model.


## Close 1006 code-path investigation (2026-10-22)

This is a local source inspection and protocol-only probe, not a reproduction
or an attribution of the 2026-10-21 test-account close. No production calls,
logs or Firestore were read.
`ListenReceiver.receive_data` records ASGI disconnect before entering its
teardown, then awaits `LiveHeldAudio.finish_updates` through a shielded,
supervised task. `close()` takes the publication lock, drains every PCM tail,
seals the group and releases unused capacity. It no longer repeats the empty
flush/seal barrier. A server-initiated close in `ListenSession._teardown_components`
can occur later, after receiver/drain work and usage persistence.

The Docker entrypoint uses uvicorn's automatic WebSocket protocol selection.
The locked uvicorn 0.30.5 / websockets 12 implementation handles Close control
frames in `WebSocketCommonProtocol.read_data_frame` and echoes the Close before
ASGI's `websocket.disconnect`; wsproto's `handle_close` likewise responds before
queuing the ASGI disconnect. Once the protocol reader reaches a **client Close frame**, it can acknowledge
without waiting for application tail persistence. However, uvicorn defaults to
`ws_max_queue=32`; websockets' `transfer_data` pauses its reads while the inbound
message queue is full. Listen awaits custody inline between receives
(`receiver.py`'s `_flush_stt_buffer` / `_emit_stt_cap_live_held`). A slow flush can
therefore delay reaching a queued Close frame, although the event loop is free.
A local protocol-only probe with the locked packages held the ASGI consumer at
an async barrier: one PCM message closed 1000 in 2 ms; 100 queued messages
closed 1006 in 403 ms with the probe client's 200 ms close timeout. This proves
the queue/backpressure mechanism, not its occurrence in the reported session.
A transport EOF without a completed handshake can also report 1006. Executor queueing or remote I/O in cap
publication does not synchronously block the event loop: encoding, encryption,
upload, summary, capacity, stage append and seal use worker leaves. PCM copies
and bounded identity hashing still run on the loop. This inspection cannot prove
that the reported session received a Close frame, or exclude unrelated loop or
transport delays. Final sealing after ASGI disconnect is already after the
protocol reply; moving it later would not unblock a reader stalled before
disconnect. Decoupling ingress from persistence needs a bounded custody queue
and backpressure policy, so this PR makes no speculative close-order change.

Budget: each pending fragment has at most two 4 s upload waits (including
executor queue/encode/encrypt/put), with a 1.5 s socket inactivity timeout per
attempt: **8 s per fragment**, not per close. Pending fragments drain serially;
summary migration can wait 30 s, lock waits and Firestore publication have
separate budgets, and staging compose/reload/cleanup RPCs each use 10 s timeouts
(with publication transaction retries). Receiver STT teardown uses a 28 s
delivery + 2 s cleanup bound, but final cap custody runs outside that bound.
There is no aggregate 8 s close deadline. Moving custody to an unowned detached
task would weaken audio retention; it remains supervised and awaited.


## Capture-order sliver regression (2026-10-22)

The first `ro-prod` read of the fixed test account projected only hold shape
fields; no encrypted metadata or content was read/decrypted, and no production
logs or writes were used. Before recovery, it showed:

| Created (UTC) | Seconds | Source frames | Stage part frames |
| --- | ---: | ---: | --- |
| 03:31:53.619 | 0.03 | 480 | 480 |
| 03:31:54.462 | 0.03 | 480 | 480 |
| 03:31:55.491 | 0.01 | 160 | 160 |
| 03:32:08.191 | 44.9 | 718400 | 240000, 240000, 238400 |

The first three capture starts were 03:31:57, 03:31:56 and 03:31:57 (the stored
integer projection), not creation order. No plaintext session/group/owner keys
were present in these projected rows. Sample indices and owner identities in
encrypted metadata remain unread. The replay uses synthetic capture coordinates,
not decrypted production metadata.

`LiveHeldAudio.observe` previously appended unique denied pieces in callback
order. `_append` queued the old run at a >100 ms wall discontinuity, bypassing
`TailGrace.ready`. The 1 s updater published that pending run. `_flush` sealed
its source at the next group-continuity mismatch and allocated another
`Publication`; `live_cap_staging.append` creates the row at that group ID.
Neither an updater tick itself nor a per-conversation/session document key
creates a new hold. `live_cap_manifest` is the legacy fragment-off path.
Thus a later receiver decision spanning the early pieces could deduplicate
those bytes, but could no longer put the already-published pieces back in
capture order. That is why the prior grace metric stayed zero.

The behavioral regression drives the real `observe` / `observe_async` and
publication coordinator with three 1 s-spaced early decisions, then an
overlapping denied suffix. Unmodified source produces exactly the table's
0.03/0.03/0.01/44.9 s, one/one/one/three-part shape. Ordered unpublished capture
produces one 44.97 s source with 240000/240000/239520-frame parts, preserving
all 719520 denied samples byte-for-byte while excluding the funded prefix.
No new custody capacity or volatile-age allowance is introduced. Incompatible
owners, rates, capture holes, months and wall discontinuities remain separate
runs. The transition-tail counter now also observes coalesced/sealed tiny runs
in this capture-order queue, rather than only explicit forced-seal grace.
