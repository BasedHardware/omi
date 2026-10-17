# Transcription cap at provider dispatch

`STT_CAP_DISPATCH_ENFORCEMENT` is a default-off backend rollout switch. This PR
adds no deployment binding and does not enable it. Enabling changes the policy
for existing capped paid plans: exhausted sync uploads wait as audio rather than
being transcribed into locked conversations. Product approval is required before
activation. Ladder budget composition and its independent default-off execution
admission are documented in [the listen pipeline](listen_pusher_pipeline.mdx#ladder-budget-refresh-and-execution-admission-default-off).
No prices or deployment switches change.

## Boundaries

Live receiver creation installs one funded admission state for the session.
Actual Deepgram, Soniox, Modulate, Parakeet and window-provider constructors use
that state, including direct registry endpoints and fallback/recovery legs.
The state debits accepted PCM seconds across channels, replay and successors.
The existing 60-second usage flush refreshes legacy funded allowance; ladder
units use the bounded cadence below.
Root counters retain their received-audio semantics. Timestamp adapters suppress
before recording accepted-provider spans. Denial is a policy pause, not provider
death: receiving, pusher audio and existing private-cloud/raw archive paths
continue. Accepted provider queues drain. Nothing enables cloud audio retention
for live users who did not already opt into it. Custom/on-device STT bypasses the
new state. The existing Plus threshold event still uses its existing wire shape.

Deepgram cloud with a request key is customer funded. Every other provider,
including self-hosted Deepgram and an Omi-funded fallback from BYOK, uses the
ordinary allowance with both BYOK quota and desktop-paywall exemptions disabled.
No key or identity is a metric label.

Known non-ladder accounts keep their monthly credit state and 900-second
membership refresh when only ladder enforcement is enabled; subscription
invalidation still refreshes immediately.

Sync v1 intake and v2 execution hold decoded WAVs before VAD when denied. V2
applies ordinary source-frame and safety-WAL coverage first, so already committed
audio is not enrolled as new recoverable work. Source maps, recording identity
and geolocation travel with the encrypted hold.
The shared segment processor rechecks immediately before each STT invocation,
including its empty-result retry. Late exhaustion holds the remaining segment.
No denied segment reaches cloud STT. Initial holds coordinate database and storage
leaves asynchronously; GCS work does not occupy the sync pipeline pool.
Transient admission/configuration holds do not claim credits are exhausted. A successfully persisted hold is acknowledged
without creating a locked transcript. Hold failures fail the upload/job; callers
must retain/retry their source audio. V1 adds `held_audio` and `held_files` to the
exhausted acknowledgment; v2 adds `held_audio` to its durable result.

Batch compute authorization checks current funded allowance. The worker calls
that authority again after decode/VAD, before each ASR microbatch and immediately
before the full-capture empty-ASR recovery dispatch. With enforcement on,
oversized recovery returns held work without spending a provider-failure attempt;
the unflagged path retains main's empty-result/failure behavior. Oversized recovery
does not reauthorize or record audio it never submits; accepted recovery counts actual
synthetic padding. Missing
worker policy authority holds work. Held work uses the scheduler's existing
`defer`, preserving raw artifacts and refunding the provider-failure attempt.
Quarantine recovery rechecks both before fetching audio and before claiming its
sole provider attempt; a denied prepared intent remains recoverable.

## Durable sync recovery

Encrypted source audio lives under the existing private-cloud bucket's
`chunks/{uid}/cap-held/` owner prefix; encrypted metadata and progress live under
`users/{uid}/stt_cap_holds`. The checkpoint has no application TTL. Existing
account deletion recursively removes the manifest and purges this chunk prefix.
A failed object upload cannot publish a successful manifest or acknowledgment.
Concurrent identical uploads cannot overwrite a recovery checkpoint.

WAV hashing, encryption, upload, download and decryption use bounded chunks;
large decoded recordings are never materialized as whole-file byte buffers.
Large source-map metadata uses an encrypted sidecar under the same owner prefix.
Late per-segment denials are aggregated into the v1/v2 held result and excluded
from post-STT subscription/DG quantities until recovered. Root meter writers and
all flag-off call semantics remain unchanged.

V2 transfers the fenced content ledger into `held`, without a TTL or a completed
transcription proof. Duplicate intake can acknowledge custody without dispatching
another provider. A preparing/failed source job still owns its retry; its holds
cannot race it into STT. Only settlement of every referenced hold completes the
content ledger. Holds that were never acknowledged await the source job's retry.

The existing `locked_content_recovery` authenticated-request path kicks an async
recovery pass independently of its once-per-month unlock receipt and legacy reset
flag. The flagged API sync router registers the recovery callback; auth-only and
pusher images do not load the sync pipeline. A distributed 60-second cooldown
bounds requests; token-fenced renewable leases prevent concurrent processing of
a hold. At reset or upgrade, current
funded allowance and the existing hard abuse restrictions must pass again before
every new recovered provider request. Already persisted receipts can settle at
the cap without another provider call. Recovery
replays WAL coverage and lineage planning, loads speaker embeddings, and reuses
VAD, segment intake, enrichment and optional playback finalization. Token-fenced
piece receipts persist a `dispatched` intent with funding, provider, model,
`dispatched_at` and `attempt=1` **before** STT or ingestion, under the lease fence.
Provider selection is pinned. Before dispatch, recovery freezes encrypted VAD
piece bytes and their lineage context under the existing owner prefix. A later
coverage/VAD decision cannot redefine a piece or suppress a sibling checkpoint.
The original full audio remains retained throughout.

`process_segment` explicitly reports `provider_called`, set immediately before
`prerecorded`, never inferred from an error class. A known non-call atomically
removes its intent (or reverts an unspent second attempt). The next claim retries
normally. If a call may have happened, the piece waits 30 minutes. Then:

1. A proof written in the **same transaction as conversation ingestion** identifies
   the hold, piece and deterministic conversation lineage. Recovery marks that
   piece transcribed, settles its existing idempotent usage key and finalizes it
   without another provider call.
2. Without a proof, current allowance/abuse admission permits **one** additional
   application dispatch, persisted as `attempt=2`. Recovery owns retries; the
   ordinary segment's local empty-result retry is disabled for these checkpointed
   recovery attempts. Provider-internal SDK retries remain outside this ledger.
3. A second ambiguous attempt gets the same cooldown/proof check, then becomes
   `failed_reconciliation`. Its audio and manifest remain retained. Successful
   siblings still settle usage and finalize independently; their paths checkpoint
   finalization progress. A failed piece never publishes an all-success content
   ledger result.

A reconciled ingest also retains raw audio, since playback storage may not have
finished before the interrupted processor returned. Terminal retained manifests
sort after actionable work and cannot dispatch. Successful ledger settlement is
retryable before that terminal transition. Neither retained form has an
application TTL or is silently erased. Ordinary fully successful recovery deletes
source and frozen pieces only after content/usage settlement.

`omi_stt_cap_recovery_reconciliation_total{outcome}` counts `cleared_noncall`,
`reconciled_ingested`, `redispatched`, and `failed`. Structured
`event=stt_cap_recovery_reconciliation` logs include hold id and piece name, never
content. Metric labels contain no uid, hold id or piece name. New recovery and
its signals are inert when both dispatch and ladder enforcement are off. WS-only and inactive
accounts wait for their next authenticated HTTP request; there is no new cron.
Turning both admission switches off pauses recovery, preserving its audio.

## Launch configuration and measurement

With enforcement off, launch-date handling is unchanged. With it on, missing or
invalid `SUBSCRIPTION_LAUNCH_DATE` logs `event=stt_cap_launch_config` and increments
`omi_stt_cap_launch_config_errors_total{reason="missing|invalid"}`. Finite-plan
allowance fails conservatively instead of inventing zero usage. A valid explicit
future date continues to mean intentionally unlaunched.

`omi_stt_cap_provider_audio_seconds_total` is additive provenance:

- `path`: `live` or `sync`;
- `outcome`: `accepted`, `suppressed` (live), or `held` (sync);
- `provider`: a bounded serving family or `unknown`;
- `allowance`: `exhausted` or `other`, at the admission/acceptance observation; `other`
  includes available allowance and untrusted lookups, without claiming availability.

Accepted live quantities count PCM accepted by a provider adapter, including
replay; failed sends do not count. Suppressed quantities count input PCM, before
VAD. Sync successful provider calls count WAV duration, including retries;
quarantine recovery counts its accepted request duration. The GPU worker counts
actual padded microbatch audio and persists additive `cap_dispatch` provenance
with `omi_funded_accepted_provider_audio_seconds` and its compute admission origin.
Held sync quantities count durably retained audio; queue denials count attempted
held quantities and can repeat across policy retries. They are not a distinct
captured-content counter. Provider-internal retries/uncertain failures are not an
exact vendor invoice ledger. Existing root counters and unit projections do not
change, and no new provenance is emitted with both admission switches off.

Admission checks are not distributed quota reservations. Concurrent already
admitted work can drain across the cap; legacy live refresh uses its existing
flush cadence; ladder refresh and local depletion are described below. Do not interpret a zero violation metric as proof against every
cross-process admission race.

## What users see when the flag is on

- **Mobile, on-device overflow flag off:** capture continues as main permits, but
  exhausted managed sessions stop producing new cloud transcripts. Existing Plus
  threshold handling remains. Uploaded offline audio waits durably; this PR adds
  no held-content card or automatic on-device processing of that backlog.
- **Mobile, on-device overflow flag on:** eligible clients keep the existing
  on-device offer/mode switch. Custom/on-device sessions continue normally.
  Already-held server uploads still wait for reset/upgrade recovery.
- **macOS:** the existing threshold handler can stop capture, as it does today.
  The backend also refuses new funded sends if the client continues; accepted work
  drains. There is no new macOS on-device overflow flow in this PR.
- **Web:** no new on-device offer is added. Exhausted funded live transcription
  pauses; supported sync uploads wait for recovery. Existing content stays as it
  was, and current clients do not gain a new waiting-audio view from these additive
  backend fields.

These visible gaps and the change from locked transcripts to held audio are the
activation decision for David; default-off deployment preserves today's policy.

## Ladder-v1 admission in #21488

`LADDER_V1_BUDGET_ENFORCEMENT_ENABLED` independently installs the live provider
suppression and sync hold/recovery paths. Ladder allowance comes from units;
legacy accounts bypass provider dispatch when only the ladder switch is enabled. Both
switches default off. Upload intake never raises the ladder budget 402: v1 holds
the decoded capture before VAD; v2 archives/queues it and holds in the coordinator.
Reset or upgrade recovery rechecks the current ladder budget before dispatch.

Live sessions carry numeric remaining units, debited from accepted provider PCM
at the pinned provider speech rate (silence is conservatively included). Shared
channels, replacements and replay share this estimate. A packet exceeding the local estimate is suppressed; there is no packet-level I/O.
Full snapshots refresh at session start, every 900 seconds, and on subscription
invalidation. Near cap (>=90% used or <=120 seconds at the maximum managed
speech rate), each 60-second refresh reads only the current hour, today's gateway
day and today's API day. The session retains a closed-bucket sum, never monthly
document lists. Hour/day rollover reads the closing buckets once before freezing
them. Backdated writes reconcile at the next full scan. The subscription already
read by the flush is reused; near-cap external spending is detected within one
flush plus persistence latency. Far-away concurrent spending can remain unseen
for 900 seconds; this is not a distributed reservation.

A full ledger scan reads H hourly documents + 2D elapsed-day documents; future
days are never read. With the unchanged one subscription read per minute, the
steady ladder-only document cost is:

| Budget used | Ordinary minute | 15-minute amortized cost |
| --- | ---: | ---: |
| 0% / 50% | 1 (full scan at 900 s) | 1 + (H+2D)/15 |
| 95% | 4 | 1 + (H+2D+14*3)/15 |

At H=408 / D=17, the averages are 30.47 / 30.47 / 33.27 reads/minute,
versus 30.53 / 30.53 / 444 before this follow-up. The 900-second scan
is a 443-read minute (442 ledger + 1 subscription); cold admission also resolves
its subscription once. Hour rollover costs one additional read; day rollover adds
two more, each once per boundary. Batch RPCs reduce latency, not billed reads.
Redis invalidation/fair-use operations are outside these Firestore totals.

An unavailable snapshot retries after 60, 120, 240, 480 and then at most once
per 900 seconds. No ledger read occurs on intervening flushes. Invalidation
bypasses backoff; a successful read resets it. Even a failure after all full-scan
reads is bounded to 30.47 reads/minute in steady state at this ledger size, rather
than 444; earlier failures cost less. Warm retries use the three open buckets
until the full scan is due. A read failure still pauses funded STT and retains
capture; historical coverage ambiguity alone never causes that denial.

Hourly/day writers atomically record unpriced seconds/events separately from
status counts. Only zero-unit missing quantities receive residual proxies;
nonzero missing annotations are already charged. Newly attributed quantities and
units remain separate from history. Each ambiguous historical leaf contributes
`max(historical priced units, unknown-provider quantity proxy)` once, plus any
separately attributed new units. A gateway proxy uses the standard-chat estimate.
Ambiguity does not return 503 or deny an account until reset. Coverage histograms
and the shared degraded/fallback metric remain visible; no history is rewritten.
