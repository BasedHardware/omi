# Real-upload batch shadow

Shadow is shipped off. `BATCH_PIPELINE_SHADOW_PERCENT=0` is the kill switch;
`BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR=200` caps the combined number of
Modulate and Deepgram unit calls per UTC hour, fleet-wide. Invalid values deny
admission/spend. Set the same values on all four Cloud Run backend hosts and
batch-pipeline-worker. No new service, queue, GPU pool, node or HPA signal
is introduced. The lead owns deployment and the first 10% activation.
Worker-only `BATCH_PIPELINE_SHADOW_RECOVERY_API_URL` targets the existing
record-recovery CPU role (`backend-integration`) and is also its OIDC audience.
Both chart profiles copy that role's declared recovery task audience. The
endpoint authenticates the existing GPU worker principal. Blank fails closed;
the pre-compute admission API's role-local policy is never used for recovery.

## Admission and isolation

The salted, stable owner hash selects the configured percentage, subject to
`in_rollout_cohort(uid, 'batch-pipeline-shadow')` with that hash as its fallback.
An explicit cohort denial excludes the owner. Neither an explicit membership
nor a percentage bypasses zero. Current batch admission and the separate
`batch-pipeline` cohort exclude the owner, and the upload hook runs only after
legacy successfully claims new v2 content. The deprecated v1 inline legacy
route offers its raw files before decode through the same isolated intake.
Native record uploads, duplicates,
completed receipts and BYOK do not create a shadow twin.

An idle GPU worker offers one rendezvous for six seconds. At most four offers
exist, within the existing fleet's <=4-node operator limit. Upload staging has
120 seconds to fill an offer; ready work has six seconds to start. No offer or
ordinary ready/leased/retry work means `dropped`, with no queue or later retry.
The worker rechecks ordinary flights and pool admission immediately before
acquiring the existing exclusive GPU lock. Shadow never waits behind ordinary compute.
The exact normal-pull capacity snapshot also gates shadow: no shared-live pool,
stale sample, exhausted slot budget, reserved fresh capacity or oversized unit
can start a shadow chain. A live arrival after CUDA starts waits for that one non-preemptible unit, as with any batch
flight; shadow never starts a second unit ahead of waiting ordinary work.

The upload owns a temporary copy of the raw files. It uses canonical record-lane
decode, VAD, Parakeet, padded/long-speech handoff and diarization. No upload's
legacy file, state, lock, ledger, Redis receipt or Firestore document is mutated
by shadow. It never enters the ordinary scheduler, owner ring, merge log,
projection, enrichment, playback, account allowance or usage accounting.
Projection also explicitly rejects a `shadow` job if one is misrouted there.
The worker's user-spend adapter and live transcript reuse are skipped; left
context has a separate stream key.

Shadow audio uses the existing owner-encrypted, generation-pinned staging
store and privacy fence. Registration creates only a shadow-marked artifact
outbox with cleanup after one hour, independent of successful projection.
Transcript/result payloads are discarded in memory and never uploaded.
`batch_pipeline_{stage}_shadow_jobs` and `_shadow_slots` hold only short-lived
control metadata; terminal job records replace that metadata with hashed-owner
outcomes. Account/conversation deletion includes shadow jobs and their normal
artifact outboxes. Shadow artifact receipts are deleted with their objects,
including raw owner/conversation metadata; the ordinary 45-day receipt rule
does not apply. Stale jobs are settled by the worker after an hour; active
recovery uses its own start time, never the upload age. Raw control metadata
additionally expires after two hours (renewed at recovery start). Terminal outcomes expire
after seven days. The lead must apply the added shadow job/spend TTL declarations
in `deploy/batch-pipeline/retention.json` through the existing TTL operator tool.

## Recovery and spend

The private OIDC `/v2/batch-pipeline/shadow-recover` endpoint uses the record
lane's strict original-audio VAD and provider/response validators. Speech gets
one Modulate call; a valid empty response with the live lane's exact
`skipped_long_speech` worker evidence can get one Deepgram call under the existing
second-provider switch and speech threshold. Terminal empty disposition uses
the pinned recovery policy. Missing/untyped GPU results record `error` without
calling a paid provider. Each call independently needs
an atomic hourly reservation and a fresh privacy check. Duplicate deliveries,
provider errors, lost responses and hour rollover cannot repeat a reserved
provider call. Exhaustion or unavailable/ambiguous spend authority records `paid_skipped` (`shadow_paid_skipped` in the
gate's terminology). It never writes a recovery transcript or bills a user.
Recovery runs outside the GPU lock and pump lanes, with at most one outstanding
shadow recovery per worker, so paid-provider latency cannot occupy every GPU lane.

## Readout contract

Counters appear on existing backend and worker metrics surfaces. Aggregate
across those targets; do not add owner IDs or hashes as Prometheus labels.

| Metric | Labels / meaning |
| --- | --- |
| `omi_batch_shadow_outcome_total` | `outcome=recovered\|empty\|failed_held\|error\|dropped\|paid_skipped`, `class=fresh\|recent\|deep` |
| `omi_batch_shadow_speech_seconds_total` | `vad=worker\|strict`, `class`; original VAD speech union |
| `omi_batch_shadow_speech_loss_seconds_total` | Same labels; whole-unit speech seconds when no words survive; zero on nonempty recovery |
| `omi_batch_shadow_gpu_seconds_total` | Shadow chain wall seconds including decode/result sink and CUDA synchronization |
| `omi_batch_shadow_paid_calls_total` | `provider=modulate\|deepgram`; durable reservations, conservatively includes failed/uncertain calls |
| `omi_batch_shadow_paid_audio_seconds_total` | Same provider labels; reserved input duration, includes silence in provider input |

`recovered` means a nonempty GPU or recovery transcript; `empty` means VAD
silence or the live policy's qualified terminal-empty disposition.
`failed_held` means speech but exhausted valid-empty recovery.
`error` includes provider/validation/infrastructure faults. Dropped/undecoded
units have unknown speech, not measured zero-speech evidence. Metrics and logs
are best effort after transaction commit; terminal shadow job records are the
durable census. Per-owner concentration is a count/group by `owner_key` in those
records or `event=batch_shadow_outcome owner_hash=...` logs. This is an opaque
SHA-256 owner key. The workspace lead owns `fleet_gate.sh --shadow`.

## Expected spend at 10%

The cohort is 10% of eligible owners, not a guaranteed 10% of audio. Busy offers
drop, so the accepted duration and failure fraction must be measured during the
first hour. No additional nodes are requested; shadow uses existing provisioned
GPU slack. Watch GPU busy minutes (`increase(omi_batch_shadow_gpu_seconds_total[1h])/60`)
and normal latency, and keep the fleet within the operator's <=4-node ceiling.

Before production activation, the lead/lane 1 train must qualify the shadow on
isolated staging with staging-soak's synthetic corpus: prove no user-visible
writes, the combined paid cap and dropping under load. Production 10% follows
that staging pass (lead ruling 2026-10-21, bus `dbc28b`). Outcome counters have no
environment or percentage labels; bind reads to external deployment/config
identity. They alone cannot prove the gate's p95, debt, reads or a continuous
same-percentage clean window, and `empty` is not an expected-silence guarantee.

For an illustrative 100 eligible audio hours, uniform owners and no drops give
10 shadow hours. If 5% need Modulate and 1% of all shadow duration also needs
Deepgram, recovery is about $0.0462, excluding storage/CPU: `0.5 * $0.03 +
0.1 * $0.312`. If every shadow hour needs both, it is about $3.42. These are
conditional list-price scenarios, not observed vendor spend or an Omi contract.
Rates checked 2026-10-21: [Modulate multilingual batch](https://www.modulate.ai/api-pricing)
$0.03/audio-hour and [Deepgram Nova-3 multilingual prerecorded](https://www.cloudflare-test.deepgram.com/pricing)
$0.0052/minute ($0.312/hour).

The 200-call cap is shared across providers. With intake units <=1 hour, a
conservative hourly list-price ceiling is $62.40 (all reservations priced at
the more expensive Deepgram rate); first calls also consume that same budget.
This is not a dollar cap or a vendor-billing receipt. Reconcile actual Modulate
and Deepgram usage with their vendor feeds. Lead may lower the cap before 10%.
Roll back by setting the percent to zero on upload, API recovery and worker
hosts; no new GPU or paid work starts, CUDA already in progress drains, and
existing cleanup/privacy erasure remains active.
