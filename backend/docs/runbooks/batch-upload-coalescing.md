SCA-1800 adds a dark server-side pre-unit hold. Only
`BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED=true` creates holds; false, unset and
all other values use ordinary per-upload admission for new uploads. No runtime
value, rollout approval or savings is established by the code change.

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
