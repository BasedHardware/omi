# Held audio durability and server redrive

Owner: backend sync. Source incident: #21488 / #22198 (held recovery depended on
process-local continuations). This runbook describes code defaults, not a deployed
rollout. The enforcement cohort deadline remains **2026-10-19 18:00 UTC**; neither
`STT_CAP_DISPATCH_ENFORCEMENT` nor `LADDER_V1_BUDGET_ENFORCEMENT_ENABLED` is enabled
by this change.

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
with a one-candidate page. Current reservations are retried before a new page;
the existing UID worker lease and per-hold/per-text leases deduplicate concurrent
sweeps/client paths. The month, chosen estimate, reservation, cursors, allowance
and abuse checks remain authoritative. A busy or killed worker's 30-minute lease
must expire before another owner may run. There is no 60-second timer or
fire-and-forget self-respawn. A productive page leaves its choice processing.

Each of three independent discovery streams (choices, staging/sealing, cleanup)
reads at most five rows per sweep, ordered by full document name with a durable
keyset cursor. Each wraps on a short/empty page. The cursor advances before work,
so a blocked owner cannot hide later existing users. A crash can defer that page
until the next rotation; it cannot erase intent. For N queued owners, discovery
latency is roughly `ceil(N/5)` successful scheduler executions; blocked choices
also consume visits. A long request delays subsequent scheduler delivery. This
is bounded fair recovery, not a per-user two-minute SLA. Endpoints await work;
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
usage key. Empty responses retain existing reconciliation semantics; they are
not cached as reusable completion or treated as proven silence.

The irreducible window is vendor acceptance through successful result checkpoint.
After a kill there, recovery waits 30 minutes and checks the atomic ingest proof.
Without proof, it permits one additional funded application dispatch. Therefore
one frozen piece can cause **at most two billable STT POST attempts** (one duplicate)
under these current adapters, excluding vendor-internal billing behavior. Parakeet
may probe v2 then v1 after 404; the 404 is routing discovery, not completed STT.
A second uncertain/empty attempt becomes explicitly `failed_reconciliation` and
retains audio; it is terminal, not a silent successful transcript. This residual
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
flush window before their existing 10-second background drain. GKE listen/pusher
have 120-second termination grace and 15-second preStop; their uvicorn graceful
session drain is bounded to 60 seconds, leaving at least 45 seconds for lifespan
flush/drain. SIGKILL and a flush exceeding the grace can lose the last volatile
fragment, while staging remains recoverable. Flush errors log and propagate to
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
