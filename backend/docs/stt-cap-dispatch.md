# Transcription cap at provider dispatch

`STT_CAP_DISPATCH_ENFORCEMENT` is a default-off backend rollout switch. Its
approved activation is a small cohort and live only. The shared cohort/lane
scope below also applies when only ladder budget execution is enabled. Outside
that scope the existing behavior stays unchanged.

## Cohort and lane rollout (David 2026-10-18)

Execution admission requires **both** an admission switch and a selected owner /
original lane. `STT_CAP_DISPATCH_ENFORCEMENT` remains default false.
`LADDER_V1_BUDGET_ENFORCEMENT_ENABLED` alone uses the same scope; it cannot widen
STT execution to the fleet. `STT_CAP_DISPATCH_COHORT` unset or empty admits nobody.
Use `uid:<COORDINATOR_TEST_UID>` (replace the placeholder before deployment),
comma-separated UID tokens, `pct:1`, or a union such as `uid:<UID>,pct:5`.
`all` is the explicit universal cohort. The token grammar and stable
`sha256("free-tier-cohort:" + uid)[:8] % 100` bucket come from the retired free-tier
parser, now shared in pure `config/rollout_cohorts.py`; no PostHog or Firestore
membership call is added. Malformed tokens invalidate the whole cohort.

`STT_CAP_DISPATCH_LANES` accepts comma-separated `live,sync,batch`. Unset, empty
or whitespace-only values select **live only**. Unknown tokens or empty tokens
inside a list (for example `live,` or `live,,sync`) disable the whole selection.
Unknown call-site lanes are never mapped to a permitted lane.

Batch is additionally fenced off by the code-owned `_BATCH_LANE_READY = False`,
for both admission switches and every cohort, even with explicit `batch` and
`all`. Before that constant can change, lane8 must write `provider_reason=byok`
into `binding.policy` at batch admission. This is a source readiness condition,
not an environment flag. A valid lane list containing batch emits one static
warning per process; it does not prevent explicit live/sync selection. Thus
`live,batch` selects only live and `batch` selects nothing while the fence is
closed. No UID or configuration data is included in the warning.
Live receiver and provider constructors pass the authenticated UID and `live`;
v1 intake, v2 coordinator and ordinary segment retries pass `sync`; queued GPU
jobs, quarantine/speech retries and generated/text processing pass `batch`.
Every GPU microbatch checks each owner separately. Generic generated work belongs
to `batch`, so a live-only rollout does not enable its budget denial paths.
Owner-facing summaries, consent and worker entrypoints require membership in at
least one selected lane, then each paid audio dispatch checks the original lane.

Listen checks the raw admission switches and custom-STT bypass before reading
request identity. Active non-custom admission still requires the authenticated
UID and live-lane scope; there is no missing-UID fallback.

Managed compute uses the same batch selection before treating shared admission
as a completed ladder budget check. An excluded UID, empty cohort or live-only
scope falls through the existing paid-plan/free-feature policy without reading
budget snapshots or allowance. Independent Pro feature gates still apply.

### Original held-audio provenance

Encrypted hold metadata owns `origin`. New sync intake and late-segment holds
write `origin=sync`; the live writer already writes `origin=live`. Recovery reads
that value before audio download/claim and propagates it as `cap_dispatch_lane`
through the shared segment processor, per-call allowance and empty-result retry.
It never replaces origin with the execution method (`batch`), device `source`, or
sync freshness (`sync_lane=fresh|backfill`). Legacy metadata **without** `origin`
is sync: all pre-origin hold producers were sync; every live custody version
already supplied `origin=live`: the first live writer in `f6a358902db1` (#21488)
wrote that marker, and the durability rewrite preserved it. An explicit
unknown/null origin pauses recovery
and retains the manifest/audio. No historical rewrite or new index is needed.
Excluded backlog items spend no chosen allowance. The worker scans past disabled
lanes for selected work and rewinds its cursors before stopping, retaining the
choice for widening. A reserved excluded item can yield to later selected work
only when a transaction proves it never started: the active choice token/lease,
current month and exact debit must match; an audio manifest must still match the
decrypted provenance and have `state=held`, zero lease, `next_attempt_at=0`,
and no `lease_token` or `piece_plan` key at all. Key presence records claim/plan
history even when its value is empty or null; the real release writer leaves an
empty token and retry timestamp. Missing/nonzero retry timestamps also retain
the reservation. There must be no dispatch receipts, ingest proofs or completion
markers. Text must have no claim history. The same
transaction refunds the chosen estimate once (preserving unlimited remaining),
clears the reservation and records `scope_skipped`. It does not refund metered
usage or remove the source; cursor rewind keeps excluded work discoverable.
Any intent/receipt (including ambiguous dispatch), audio lease/token, text claim
(even expired), missing legacy lease proof, unknown origin or failed read retains
the reservation. Such ambiguous reservations conservatively block that choice
until their lane is restored and normal recovery resolves them. A lost refund
response leaves the choice active for a fresh read, never a second refund.
At page completion the store refuses any actual reservation first, then consumes
an already-authorized current-month pending upgrade into a fresh token, allowance
and cutoff. Excluded rows do not block that upgrade. Without an eligible upgrade,
skipped scope keeps the choice processing and atomically rewinds its cursors;
it never finishes to waiting-choice solely because excluded rows remain.
Custody sealing/cleanup stays active during rollback because it is
owed persistence, not permission to dispatch STT.

### Controlled expansion and rollback

Both dev and prod runtime manifests bind enforcement `false`, cohort `''`, lanes
`live`. These are inert configuration declarations, not activation. The first
cohort requires the same values on listen and the CPU recovery/sync hosts:

```text
STT_CAP_DISPATCH_ENFORCEMENT=true
STT_CAP_DISPATCH_COHORT=uid:<COORDINATOR_TEST_UID>
STT_CAP_DISPATCH_LANES=live
```

No authorized coordinator-test UID was identified in local project docs; the
placeholder is intentionally unresolved and must never be deployed literally.
Keep the ladder switch at its separately approved value; setting it true still
cannot bypass these cohort/lane controls. Apply the scope consistently to all
serving hosts/readers before enrolling any UID. The dedicated GPU chart exposes
`worker.capDispatchEnforcement`, `capDispatchCohort`, `capDispatchLanes` and
`ladderBudgetEnforcement` with the same dark/live-only defaults; future approved
batch widening must configure it and the CPU policy host together.

Ramp owner **dazheng**: coordinator test accounts -> `pct:1` -> `pct:5` held for
**3 hours** -> `pct:25` -> `all` (100%). At each expansion, record held-audio count,
backlog stalls, live STT error rate and client 5xx against the pre-ramp baseline;
advance only with no unexplained regression and a synthetic consented live hold
recovering across instance replacement. Dazheng owns each expansion and the
**2026-10-19 18:00 UTC** decision/checkpoint; a missed checkpoint or an incomplete
three-hour soak is a blocker to report, never authority to skip a stage. Keep
`STT_CAP_DISPATCH_LANES=live` throughout. Sync and batch require the separate
batch-authorize-outside-GPU-lock change (blocked by Nemotron **#22352**) and explicit
approved widening. Batch also requires the lane8 binding-policy readiness change
above before its code-owned fence can open; configuration alone cannot enable
it. This change does not relocate that authorization.

Rollback: set **both** admission switches false (or clear the cohort to stop only
this execution rollout), preserving audio, processing choice and receipts. Keep
the current reader and custody redrive running to seal/clean owed fragments;
excluded recovery dispatch stays paused until scope is restored. Existing live
sessions use their admitted state until reconnect/revision drain; roll the same
configuration to all hosts and drain old sessions when changing scope. No new
Scheduler jobs or Firestore indexes are introduced here; the existing durability
job/index prerequisites below remain independently owned.

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
continue. Accepted provider queues drain. When dispatch enforcement pauses managed live audio, the server retains that
suppressed PCM for recovery independently of the optional private-cloud archive. Custom/on-device STT bypasses the
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

Monthly reset and ordinary auth no longer start funded backlog work. Subscription
reads resume only an already chosen, current-month run. The authenticated
`POST /v1/users/processing-backlog/process` endpoint requires `Idempotency-Key`;
a durable receipt prevents duplicate consent even after the original job finishes.
A choice captures its month, cutoff and estimated remaining allowance. Renewable
job and hold leases fence concurrent workers. Payment checkout/plan-change intent
starts recovery only if the whole estimate fits; otherwise the same waiting-choice
surface is shown. New recordings after reset process normally; older held audio
and deferred text stay waiting. For every explicitly chosen provider request, current
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
   recovery attempts. Nested URL/provider retries are disabled for held recovery. Nonempty provider
   results are encrypted and fenced before ingest, so a restart reuses them; the
   vendor-acceptance-to-checkpoint crash window remains irreducible. See the
   [durability runbook](runbooks/cap-hold-durability.md) for bounds and rollout.
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
accounts can also resume through the existing durable-redrive sweep after an explicit processing choice.
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
  threshold handling remains. Uploaded offline audio waits durably. The held-audio
  card, rows, live banner and settings row stay hidden.
- **Mobile, on-device overflow flag on:** the conversations list shows held uploads
  with Upgrade and, when this phone can run the on-device engine, Transcribe on
  this phone. That action switches new recordings to the existing on-device mode.
  It does not download or transcribe audio the server already holds. A successful
  upload marks the local WAL synced, but the phone can keep that copy: new installs
  auto-remove synced copies after 30 days, and existing installs keep the setting
  off unless the user opts in. The on-device runner does not transcribe those
  synced copies. Transcribing the waiting backlog on the phone is a follow-up.
  At cap the UI says processing is paused. After reset the server returns a
  waiting choice with estimated allowance hours/percent. Process waiting recordings
  requires explicit confirmation; Not now leaves them waiting. When the estimate
  exceeds remaining allowance, the worker processes newest-first up to what fits
  and leaves the rest waiting. Reset remains 00:00 UTC on the 1st, including legacy Plus. Live capture
  keeps recording while cloud transcription pauses. The first suppressed live
  packet emits a session-scoped `stt_cap_live_held` UI receipt. Its `session_id`,
  `paused` and `held_seconds` fields report only durably published live seconds.
  Periodic receipts update the count; a funded resume flushes the tail and sends
  `paused=false`. Reconnects clear the client's receipt state. No WAL offsets,
  sync marks or client retention policies change. Settings usage
  adds the waiting row beside the existing meter, the existing paid on-phone
  toggle when this phone can run the engine, and See plans. The held total is one
  summary document, not a scan of every hold. The newest 20 rows are listed, with
  a count of the rest.
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

Within the selected cohort/lanes, `LADDER_V1_BUDGET_ENFORCEMENT_ENABLED` installs the live provider
suppression and sync hold/recovery paths. Ladder allowance comes from units;
legacy accounts bypass provider dispatch when only the ladder switch is enabled. Both
switches default off. Upload intake never raises the ladder budget 402: v1 holds
the decoded capture before VAD; v2 archives/queues it and holds in the coordinator.
Explicit-choice or fitting-upgrade recovery rechecks the current ladder budget before dispatch.

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


## Server custody of suppressed live audio (round 4 cost cut)

The receive boundary retains decoded mono PCM only for denied, unique capture
spans. Paid prefixes and replay spans never become holds; the capture observer
and client WAL behavior are unchanged. Owner, rate, channel, UTC capture month
and real clock-gap boundaries remain separate. Source timestamps and conversation
ownership follow the existing recovery/ingestion path. Funded resume publishes
the final tail before forwarding new audio, then the periodic server sweep re-drives existing processing consent. Close and cancellation use supervised, shielded publication.

The default writer now stages at-most-15-second encrypted Opus fragments and
seals/composes them into **one immutable retained source per contiguous minute**.
The sample-duration memory bound is 15 seconds; SIGKILL can still lose its current
unpublished fragment. Expired writer staging is independently sealed by the
periodic server sweep, including when no processing consent exists. Publication
and capacity replies are reconciled before consuming slots or refunding capacity;
privacy/deletion and immutable published-source authority remain unchanged.

The existing 8 GiB monthly quota reserves 64 source slots plus one overlap slot
per writer block. New collection-group indexes and Scheduler reconciliation are
deployment prerequisites. The [durability runbook](runbooks/cap-hold-durability.md)
owns exact retry/shutdown behavior, kill switches, unavoidable vendor-spend window,
measured operation counts and costs. Current 64-minute emulator custody counts are
1221 reads / 514 writes / 256 fragment PUTs / 64 composes, leaving 64 retained
sources. This replaces v4's one-PUT/two-write economics: the explicit modeled
custody increase is roughly $0.00183/capped hour for the smaller volatile window.
The original 60-second path remains available via the fragment kill switch.

Summary v2 lazily rebuilds older/missing totals under a short initializer lease
in transactions of at most 400 rows. Each page fences the cursor and listing
backfill; only the last page publishes v2. Concurrent publishers wait for that
publication, and an expired initializer resumes at the last committed cursor.
The loopback Firestore emulator exercises 805 legacy rows with concurrent
rebuild/publish and deletion/retry fences. Afterwards transactional piece-level
deltas maintain the total. It counts pending frozen-piece seconds, removes successful
or silent receipts immediately, and retains failed-reconciliation seconds.
Subscription HTTP serialization omits only an absent `held_audio`, preserving all
other null fields. `held_audio` remains an additive compatibility view. The
`processing_backlog` state is the authority for new clients: capped, waiting_choice,
processing or none. A funded account with pending holds is waiting_choice until
explicit consent, or a fitting checkout/plan-change intent, creates a run.

Local migration verification (loopback Firestore only):

```sh
firebase emulators:exec --only firestore --project demo-held-audio \
  'backend/.venv/bin/python backend/scripts/held_audio_summary_emulator_test.py'
```
