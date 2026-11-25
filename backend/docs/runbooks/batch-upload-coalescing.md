SCA-1800 adds a dark server-side pre-unit hold. Only
`BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED=true` creates holds; false, unset and
all other values use ordinary per-upload admission for new uploads. No runtime
value, rollout approval or savings is established by the code change.

## Tiered windows (defaults preserve 60 seconds)

`BATCH_PIPELINE_COALESCING_FREE_WINDOW_SECONDS` and
`BATCH_PIPELINE_COALESCING_BACKLOG_WINDOW_SECONDS` both default to **60**.
Only a positively free effective allowance entitlement may use them. Paid,
trial, exempt and unknown entitlement retain today's 60s/four-member/300s
packing profile, including for historical uploads. Trial is a reserved closed
metric label; current Subscription has no distinct trial status and retired
desktop trial metadata must not be used to infer one. Lookup errors are unknown.
The classification lookup uses `provision=False`, includes effective promotions,
and reads no allowance usage. It is additional intake overhead to measure.

The backlog setting applies to existing backfill-lane or non-FRESH-priority
uploads; it does not unpark, drain, re-drive or promote anything, including R7
work. No backlog admission rule or scheduler changes here. Values above 900
clamp to 900; malformed, nonfinite or below-60 values use 60. Both back to 60
is the class rollback. Already accepted holds keep their first-member deadline;
new requests can shorten a predecessor on profile change, and the authenticated
release endpoint remains available. Global OFF retains the existing individual
drain/committed-merged repair semantics.

A window above 60 requests an extended profile: <=16 members, <=600 source-audio
seconds AND <=600s outer capture span. Per-member 2MiB/300s, group 20 files/8MiB,
64 global/two-owner groups and 120s lease remain unchanged. The first member
pins the profile/deadline. Class/window changes release the predecessor without
overtaking it. Quota exhaustion returns the exact legacy ordinary per-upload
fallback (None before custody), never a capacity refusal. Joining an existing
group spends no new quota. Existing incompatible/predecessor ordering retries
are distinct from capacity exhaustion.

### Mixed-version gate: explicit complete reader inventory

An old completion writer rejects more than four original members. This change
therefore **refuses extended creation** until all inventoried readers advertise
protocol 2. With no proof it still accepts eligible input under the legacy 60s
profile; it never assumes the elected drainer proves the whole fleet upgraded.

New projection instances and GPU runtimes advertise once under
`<namespace>_coalesce_capabilities/<OMI_BACKEND_RELEASE_SHA>`:
`{"protocol":2,"max_members":16}`. An absent/invalid full source SHA cannot
advertise. Workers must have a source-bound release identity too; do not invent
one to pass this gate. Readers accept 16-member completion manifests regardless
of their local window env values, including unset/60 and producer OFF.

The release owner must first inventory **every** revision receiving traffic,
standby/active drainer and completion writer, and all worker image source SHAs.
Then, and only then, the owner may publish the following operational readiness
receipt (no producer publishes or renews it):

```json
{
  "inventory_complete": true,
  "verified_at": 1794902400,
  "valid_until": 1794903300,
  "reader_releases": ["0000000000000000000000000000000000000000"]
}
```

This is a schema example, **not executable rollout data**. Replace timestamps
with the verified current inventory's UTC epoch and source SHAs with the actual
complete fleet; store at `<namespace>_coalesce_capabilities/roster`. The window
is at most 900s, cannot start in the future, and every required SHA must already
have a protocol-2/16-member advertisement. An old or unadvertised SHA blocks.
The owner must reverify the complete live inventory before renewing it; new
traffic or worker rollout invalidates the old attestation. Ads alone cannot
discover an old binary, so **an incomplete inventory is not clearance**. No
runtime inventory, roster write or capability activation occurred in this PR.
Production data/account documents are not part of the inventory.

### Measurements and first canary

`omi_batch_pipeline_created_units_total{entitlement="paid|trial|free|unknown"}`
counts non-shadow unit creation only after durable admission, not transaction
retries or receipt re-ACKs. Unclassified/native adapters report unknown rather
than guessing. This is a post-commit observation and can undercount a lost reply.
`omi_batch_pipeline_upload_to_transcript_seconds{entitlement=...}` retains each
original sync request-arrival timestamp (before multipart parsing) through a hold, merged admission
and completion. It observes one sample per first original terminal receipt,
including all hold/queue/processing time; replays do not refresh the clock or
observe again. Merged units do not replace N originals with one latency sample.
Deleted sources and legacy uploads lacking the original clock do not contribute.
The endpoint is durable server transcript publication, not notes completion or
proof of a client receiving a response. Check actual client receipt separately;
watch oldest unfinished/held obligations as well as completed-sample p90.

Both collectors live in the default Cloud Run registry and the worker private
registry/multiprocess forwarding. Existing `batch_pipeline_.*` and `omi_.*`
keep-lists retain the counter and every histogram sample; regression tests
evaluate every keep/drop rule in both Cloud Run profiles and the actual worker
health registry. No keep-list widening is needed.

There is still no percentage/cohort gate for this path. Do **not** call the batch
admission percentage a 10% coalescing cohort. Smallest safe first production
step after source/compatibility and synthetic qualification: keep FREE=60, set
BACKLOG=300 on backend-sync producers and every drainer, only for already
admissible free non-fresh work; R7-parked work remains parked. Start with one
<=15-minute verified inventory receipt; if it expires, new holds automatically
fall back to 60. Inventory renewal is an explicit release-owner action after a
new verification, not a permanently trusted flag. No free-fresh expansion until
the margin lead accepts that readout or a stable owner-cohort route exists.

Gate: free upload-to-transcript p90 <1800s and unchanged paid/trial latency,
no missing/duplicate samples or speech, no privacy/erasure/retention regression,
paired transcript/speaker/notes quality, stable oldest outstanding age and
recovery rate, and lower total billed reads per unchanged original-source
audio-hour including entitlement, capability/scan and original-fanout overhead.
At 300/600s units, real canary measurements must include RSS, peak GPU VRAM,
full-unit VAD/diarization latency, ASR padded-batch budgets, claim/lease tail,
provider recovery duration/spend and failed/held originals. Replay tests cover
CPU/windowing/recovery contracts, not CUDA memory or quality. The margin lead
expands; done or reverted by **2026-11-24**. Rollback both windows to 60; keep
compatible readers until extended holds and original receipts are terminal.
No saving is claimed.

The remainder describes the legacy 60s profile unless the tiered section above says otherwise.

The accepted risk contract is SCA-1756's `cuts-3-design-risks.md`, attachment
`01a1d0e2-6ecd-7156-92c3-c1e98e546d56`, reviewed and verified 2026-11-12.
Its product reference `3f98d03e8b95b6cba1b4458b2d467afad444a332` was reconciled
against the implementation base `ac02feb05f0d`: the single-upload decoder,
privacy/retention boundary and per-upload receipt contracts remain present.

The initial cohort is intentionally narrow: ordinary batch, one explicit
conversation and recording session, device/source/batch-family/lock identity,
known supported language, one privacy generation and frozen policy/priority.
Provider/BYOK/native-record, early-clock and capture-coverage-claim inputs do
not enter holds. Location is included in the hashed grouping context. Different
content with overlapping clocks is never deduplicated. Incompatible uploads
release the predecessor and retain phone custody for retry rather than
overtaking it. No client capture, upload or parked-recording behavior changes.

Original files and their original upload arguments are encrypted in the normal
generation-pinned artifact store before a hold can return 202. This does not
depend on the conditional private-cloud archive. The first member fixes the
release deadline at <=60s; subsequent members never extend it. Inspections run
the existing decoder on private copies, since that decoder consumes its inputs.
Only sealed, capture-ordered membership can enter unit admission. A group and
its every source/member have owner, conversation and privacy-generation fields
for account and resumable conversation purge. Erasure remains active OFF.

Each original upload retains its content identity and public job handle. It
stays queued until there are real units, and stays nonterminal until all group
siblings pass the existing persistence/projection bar. Result fanout changes
neither the units' immutable projection binding nor their scheduler priority.
The held source's orphan-reaping exemption lasts through unit conversion.
After conversion its encrypted copy joins the normal unit's completion-led
artifact retention (24h after successful projection); it is not retained
forever for sync-off users. Only converted group/source/head metadata receives
45-day expiry metadata. No pre-unit source or held group gets a TTL.

Freshness cost is up to 60s of deliberate release delay before ordinary
admission/processing, plus ordinary queue, IO, retry and outage latency. Per-unit
privacy/projection work is deferred, never waived. A release deadline is not a
claim that an unhealthy service creates a unit within 60s: the rehearsal must
report actual per-original-upload p50/p95/max latency and missed deadlines.
The 600s Redis detector measures processing silence; this cohort is isolated
before any Redis sync job exists. Neither its timestamp nor its exemptions
change. The budget helper declines unknown/exhausted applicable deadlines and
reserves; callers with a real deadline may not assert the isolated-batch case.

Bounds are code constants: 64 held/sealed groups globally, two per owner, four
members and 20 files per group, <=2MiB raw per member, <=8MiB serialized member
payload per group and <=300 decoded seconds. One pass scans <=8 groups. Drain
leases are 120s, token fenced at unit admission and receipt fanout; a restart
uses durable membership and content idempotency. New holds require a successful
drainer heartbeat within five seconds. Unknown quota, saturation or a stalled
drainer declines new holds; a pending predecessor retains its ordering fence.
The drainer is supervised with the serving loop in both normal and pump modes.
The single-field `scan_at` index is sufficient; completed groups omit it.
Scan order includes the document ID to break deadline ties. A versioned cursor
in the existing global quota row advances before each bounded page, including
pages whose privacy checks fail, and wraps after an empty range. It is scan
progress only: it neither modifies denied holds nor authorizes processing.
Restart and deleted cursor boundaries preserve progress; a stale concurrent
scanner cannot overwrite a newer cursor. Default OFF with no quota creates no
cursor row. The extra quota read and cursor checkpoint are fixed scan costs
that the matched-workload read numerator must include.

Merged admission also records its bounded original membership in the content
ledger before any unit is runnable. The all-siblings projection completion
transaction copies the authoritative terminal result and completion-led expiry
to every original receipt. It reads each original intake/ledger and verifies
its identity before any write; the existing live privacy guard still gates the
transaction. Thus completion survives target TTL without requiring a client
poll. Replays do not extend an original's terminal expiry. Ordinary uploads and
OFF individual conversions use their existing completion path and add no fanout
reads. The extra per-original completion reads/writes must also be measured.

The authenticated `POST /v2/sync-local-files/{job_id}/release-hold` is a precise,
rate-limited, idempotent early-release hint for one original public job. It does
not promote GPU priority or alter member order. Generic status polling and Home
refresh do not release holds. Released clients keep their existing API shape;
this change adds no client call to the new hint. Client UX wiring, if required
for a particular release, must be demonstrated before that release is qualified.

OFF affects producer creation and a drainer's conversion choice. All producer
AND drainer runtimes must read OFF for an OFF rollback; mixed values are not a
verified global kill. An OFF drainer converts pre-unit groups individually with
their original IDs. If a merged intake already committed, even an OFF or
restarted drainer keeps that immutable group and only repairs member receipts.
A partially converted individual group can never switch back to merged.
Compatible status, custody, purge and drainer support must remain until held
depth is zero AND every member receipt is terminal. An active drain lease may
need to expire after process death; OFF does not discard its sources.

`omi_batch_upload_coalescing_total` has closed outcome labels. `accepted` counts
observations (including possible racing receipt re-ACKs), not unique uploads.
Unique admitted source audio is the immutable per-source `source_frames/16000`
captured before grouping, excluding decoder-inserted gap silence. Do not use
post-group unit duration, UI receipt segment counts or download observations as
that denominator. The per-source records also bind original content identities,
object generations, exact arguments and original byte hashes in the encrypted
payload. Production receipt aggregation must use approved aggregate-only
queries; this task reads no account contents.

Qualification remains separate from code tests. The local Firestore rehearsal
uses synthetic PCM and a generation-fenced object adapter. It proves admission,
raw/sample conservation, truthful queued receipts, restart/fanout and OFF paths.
It does not run paid inference or notes generation, establish settled GMP
windows, measure the entire billed read family, or bind a deployed image.
Those gates remain NOT_RUN, never PASS.

Verify an attached packet with
`python backend/scripts/verify_batch_upload_coalescing_packet.py packet.json`.
An incomplete packet must exit 1. `--evidence-only` checks local source and
rehearsal integrity; it grants no production qualification or release authority.

Before activation, attach a source/image-bound packet with a fixed original
input manifest and matched admitted-source-audio workload. Hold arrival cadence,
backlog and polling constant. Record total billed batch-family reads, fixed vs
row-dependent vs per-unit components, true units reaching persistence, unique
original uploads, artifact download observations, and per-original-upload
latencies separately. Require sample/provenance equality, no missing/duplicate
speech spans, and a pre-agreed flat paired transcript/speaker/notes factuality
and coverage gate on synthetic or approved evaluation audio. A packing model,
created-unit count or fabricated inference result is not savings/quality proof.

R11 order: ship compatible projection completion writers, readers, purge and
drainers dark first; verify the serving supervisor and indexes/retention setup,
then run dev/staging qualification before enabling a production producer.
Canary topology must isolate producer traffic while all eligible drainers agree
on the switch; an OFF standby drainer otherwise intentionally drains separately.
If that topology is unavailable, do not claim a canary is isolated. Record exact
effective flags and image/source bindings for backend-integration, backend-sync,
backend and the GKE worker (unknown remains unknown). No flag is read by the GPU
worker itself; its effective env value must still be reported rather than guessed.
TTL on converted `coalesce_groups`, `coalesce_sources` and `coalesce_heads`
metadata is a release-owner configuration prerequisite, not provisioning by this
task. New hold/member timestamps must not be added to a TTL field before conversion.

Quote lead2 GO and this complete packet in Release: Omi prod. That release owner
handles merge, deployment, activation, the written order delta against other
levers, and rollback. Stop for a lost/misbound source or receipt, privacy mismatch,
quality regression, unexplained read amplification or missed latency budget.
Then set OFF everywhere, drain individually, and prove zero unexplained residue
before removing compatible readers. Never roll back to an incompatible binary
with nonterminal member receipts. Book $0 until the release-owner live readback
proves reads per unchanged admitted audio-hour down with quality/custody PASS.

## Counts-only production diagnosis

Sync and integration use `deploy/cloud_run_gmp_sync.yaml`, not the shared
`omi_.*` sidecar profile. Retain the explicitly listed coalescing hold/scan
metrics and `omi_batch_leader_lease_total` there. The retention test in
`tests/unit/test_attach_cloud_run_gmp_sidecar.py` covers both the hold outcomes
and the strict scan's counter, histogram and last-success gauge. A registered
zero gauge on a non-draining backend instance does not establish scan health.

After the collector configuration is serving, query the emitting service:

```promql
sum by (service_name,outcome) (increase(omi_batch_upload_coalescing_total[1h]))
sum by (service_name,outcome) (increase(omi_batch_upload_coalescing_scan_total[1h]))
max(omi_batch_upload_coalescing_scan_last_success_seconds{service_name="backend-integration"})
sum by (outcome) (increase(omi_batch_leader_lease_total{role="upload_coalescing_scan",service_name="backend-integration"}[1h]))
```

An absent outcome counter is unknown until ingestion is qualified. Even after
that, `accepted` is an observation count, not a unique-source denominator.
The producer declines when its shared quota heartbeat is absent, older than
five seconds, or more than five seconds in the future. The GMP scrape interval
is sixty seconds, so the last-success gauge alone cannot certify that
five-second admission condition. Positive
`accepted` and `drained_merged` observations establish execution separately.

There is no coalescing-specific percentage or allowlist. Batch admission's
`rollout_cohorts/_ramp` percentage is a different control and must not be reduced
to implement a 5% coalescing canary. A release owner needs an isolated 5% producer
route, with the remaining producers OFF and all shared drainers ON (OFF drainers
intentionally convert individually). If that topology cannot be verified, a
5% isolated canary is not available from the current boolean flag.

For a canary, require attributable hold acceptance and merged draining, healthy
scan/lease outcomes, conserved source samples, terminal receipts, paired quality
acceptance, and fewer total batch-family billed reads per unchanged source audio
hour including scan, artifact and completion-fanout overhead. Measure latency
from each original upload's arrival through delivered transcript, including the
hold. Fresh paid and trial p50/p90 and their existing speed targets must not
worsen against a matched control; adding sixty seconds to an existing target is
not acceptance. Existing unit/processing clocks start too late and queue-age
metrics do not substitute for that measurement. Stop on missed latency budgets,
privacy/custody errors, quality regressions or unexplained read amplification.
Do not activate without an attributable original-upload latency measurement.

Rollback is `BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED=false` on every producer
and drainer, retaining the compatible binary until all existing holds drain
individually and every original receipt is terminal. No saving is claimed.
