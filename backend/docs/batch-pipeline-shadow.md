# Real-upload batch shadow

## 2026-10-29 projection planning and proposed 25% window

The worker's successful result now makes one private OIDC
`/v2/batch-pipeline/shadow-project` call on the existing recovery CPU role.
The transcript exists only in the HTTPS body and request memory. There is no
task queue, application retry, transcript artifact or result document. The
intake reserves at most 200 shadow attempts per UTC hour across replicas in
the existing `_shadow_spend` TTL collection using disjoint `projection-<hour>`
keys, before copying/decoding/staging or GPU compute. Quota-denied offers are
dropped, not artificial speech loss. The CPU endpoint consumes that unit's
reservation once, with a fresh normal privacy check; already admitted work
keeps its permission across hour rollover. Lost replies consume the attempt.
At most three plans execute per CPU process. Admission and execution hours can
differ; the admission cap is not a hard execution-time dollar ceiling.

Planning uses the real VAD result partitioner, incoming-conversation builder
and `assign_in_transaction` body. Its reference adapter can read only the
bound owner's supported document collections, at most 16 reads with one-second
RPC timeouts and a two-second read/part boundary budget. Planned sets/updates
are counted and discarded. No SDK reference, client, writer or commit is
available to the assignment body. Commit/delete attempts fail. The adapter
clears cached transcript reads when the request ends; no planned payload is
retained. Normal projection still refuses all shadow jobs before side effects.

This covers result geometry and assignment planning against bounded real
snapshots. It does not cover the whole owner-chain walk, transactional
contention, durable projection, claims, enrichment or publication. Multi-part
plans each see the same real snapshot, without simulating prior discarded
parts. Replay remains required for owner-chain ordering and structural gates.
A planner error is an observation; it cannot fall through to normal serving.
Worker errors and paid recovery retain their existing isolated outcome path.

The RPC client allows at most 8 MiB and 50,000 words, a 4 KiB receipt and a
five-second transport timeout. A transport timeout is not a server cancellation
or a hard CPU-time limit. The call currently runs in the worker's result sink,
so up to that timeout adds to a non-preemptible shadow flight; measure ordinary
queue latency and shadow GPU wall time before expanding. No additional GPU
nodes or autoscaler capacity are requested.

Lead-only proposed change, after deploying compatible CPU and worker images:

```text
BATCH_PIPELINE_SHADOW_PERCENT=25
BATCH_PIPELINE_SHADOW_LANGUAGE_ONLY=false
BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR=0
```

Apply the same shadow settings to all four intake/recovery Cloud Run roles and
the batch workers. Keep serving batch admission at its separately approved
percentage and keep the existing three L4 workers/node cap unchanged. The
shadow cohort is 25% of eligible non-serving owners, not 25% guaranteed audio.
Busy/late offers still drop. Roll back with `BATCH_PIPELINE_SHADOW_PERCENT=0`
on those same roles. Already running CUDA/RPC work drains; normal cleanup and
privacy erasure stay active. This proposal does not authorize a production flip.

For a 30-minute first window, use existing isolated staging qualification,
zero customer-data writes/publication tests, then bind metrics to exact running
image/config identity. Measure
`omi_batch_shadow_projection_total{status}`, `_cpu_seconds_total`,
`_wall_seconds_total`, `_reads_total` and `_payload_bytes_total` alongside
normal queue latency, shadow outcome/speech/GPU counters and node count.
No identifiers are metric labels. Fresh hard-three and errclass/replay entry
checks remain owned by the batch rollout owner; shadow does not prove them.

Lead41be4b requires T2 qualification from at least3,600 measured shadow speech
seconds while serving remains0%. The read-only collector
`backend/scripts/rollout/batch_shadow_t2.py` uses masked numeric/state fields
from the shadow control table, complete bounded pagination and one server
readTime across settled and overdue reads. It emits aggregate counts only,
never owner/job IDs, audio or transcript. Dropped offers do not enter the
denominator. Recovered speech requires a machine-written `projection_status=planned`
receipt; an old inference-only outcome cannot qualify projection. Unknown VAD,
malformed receipts or unfinished attempts older than
15 minutes make T2UNKNOWN; a page/read failure makes the sample BLIND.
Speech lost to the cap0 paid-recovery refusal remains loss, never clean.

After actual25% activation, run every two minutes with a new output directory
and that activation's timestamp, under ro-prod:

```bash
python3 -I backend/scripts/rollout/batch_shadow_t2.py \
  --source-observer "$SERVING_OBSERVER_OUT/watch-latest.json" \
  --since "$ACTUAL_SHADOW_START" --out "$SHADOW_ENTRY_OBSERVER_OUT"
```

This composes **serving T1/T4 plus shadow T2** explicitly; it does not claim
shadow custody/language or full owner-chain qualification. Any known serving
T2 harm remains hard. Both source clocks must be fresh; the earlier readTime
bounds continuity. Lead44cf37 confirms that the30m clock is actual serving
T1/T4 continuity with no serving T2 harm. The collector reconstructs it from
`watch-samples.jsonl`; a supplied timestamp or current row cannot fill history.
Shadow T2 needs its complete measured census, without an additional30m wait
after reaching the speech floor. Use the combined `watch-latest.json` for the single entry packet;
retain exact CPU/worker artifact/config identity
as separate provenance. There are no pins/markers or production writes in the
collector. It must never write into the serving observer's output directory.

### Conditional list-price budget, checked 2026-10-29

Read-only infrastructure inspection found the existing recovery role in
`us-central1` with 2 vCPU, 2 GiB and concurrency 40. At 200 accepted plans/hour,
assuming five billed wall seconds per plan, charging the entire instance with
no concurrency sharing gives **$0.05308/hour** (about $0.02654/30 minutes), using
$0.000024/vCPU-second, $0.0000025/GiB-second and $0.40/million requests.
These are [Cloud Run list prices](https://cloud.google.com/run/pricing), before
free tier/discounts. This is a sizing scenario, not a hard dollar ceiling:
startup, failed/denied requests, transaction retries and work past a client
timeout add cost. Use the measured wall counter and actual billing allocation
to replace this assumption before expansion.

At most 3,200 planner document reads/hour add about $0.00096/hour at the
regional [Firestore read price](https://cloud.google.com/firestore/pricing)
of $0.03/100,000. Privacy/reservation reads and two metadata writes per accepted
plan are additional, as are transaction retries and denied attempts.
No customer transcript is stored. The extra budget documents expire after two
days under the already declared shadow-spend TTL policy; confirm that policy
is installed before activation.

Shadow duplicates encrypted mono 16 kHz/16-bit staging audio, approximately
0.1073 GiB per shadow audio-hour. Cleanup is due after one hour, with normal
cleanup delay/custody rules; it is not a hard one-hour storage cap. For an
illustrative 100 eligible audio-hours and uniform cohort/no drops, 25 shadow
hours add 2.682 GiB-hours if removed after one hour: about **$0.000074–0.000096**
at $0.020–$0.026/GiB-month, plus object operations, metadata and transfer.
These [Cloud Storage list prices](https://cloud.google.com/storage/pricing)
bracket regional US versus US multi-region Standard; bucket metadata was
unavailable to the read-only tier (403), so verify actual location/class and
cleanup lag before the flip. One regional PUT plus GET per staged unit is
about $0.0000054/unit at listed Standard flat-namespace operation prices;
other operations and cross-region transfer are additional.

Incremental GPU node-hours are zero only while the existing fixed three-node
fleet stays fixed. Paid STT calls must be zero under the proposed recovery cap;
the existing providers' production traffic is unrelated baseline spend.
No vendor usage data was read for this proposal and no total-spend claim is
made. Existing staging VAD/decode CPU, object churn and ordinary traffic
contention must be measured in the first window, so the estimate above is
explicitly a projection/storage scenario rather than an all-in bill.

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
