# First summary deadline and summary debt

Code and dev defaults keep both gates false. Production config enables the
first-summary deadline for 100% of owners on all six producing/processing
hosts. Production source enables debt repair on the scheduled backend-integration
owner (David 2026-11-09, relay 3e764e); the legacy backend-sync sweep stays off. These
settings take effect only when the corresponding artifacts are deployed.
`first_pending_at` is recorded in each outbox obligation even before rollout.
No account content enters scheduling metadata or metrics.

## Contract

For an eligible server-enriched conversation without a first summary, schedule
its existing outbox obligation by the original acceptance time +
`FIRST_SUMMARY_DEADLINE_SECONDS` (120 default, clamped 60–120). Appends,
coalescing, lease/retry and repair retain that original time. This is a dispatch
budget, not a promise that an unavailable provider finishes in 120 seconds.
`FIRST_SUMMARY_DEADLINE_PERCENT` defaults to `0`. A positive percentage adds
owners in the same unsalted batch bucket to the explicit summary allowlist,
independently of batch admission so protection survives admission rollback. At positive percentages an empty list selects only that cohort; at
zero an empty list admits nobody (fail-safe; set `FIRST_SUMMARY_DEADLINE_PERCENT=100` for all owners). Retain the existing allowlist
for a cohort ramp and rollback. Invalid percentages admit no additional owners;
the global flag still kills every owner. This does not enable summary-debt repair.

Ordinary demand priority cannot defer this first wake. Later revisions retain
the existing quiet window and 1,800-second lease.

The first-summary lease is 120 seconds. While the request is alive, a scoped
heartbeat renews that same outbox owner and task token every 30 seconds; it adds
one CAS read/write per heartbeat. The heartbeat stops on request exit or owner/token
replacement. A dead request becomes replaceable after its last renewal expires.
Before model work, the worker conditionally stamps its conversation owner using
the revision it already loaded (one claim write, **zero claim reads**). The lifecycle
transaction refuses a different owner; expiration alone never rejects the still-matching
owner's completed result. The processor persistence observer fences downstream
side effects. The sweep adds a distinct retry wake only after the active lease expires,
preserving the valid token of earlier queued deliveries.

A nonempty overview or section `body_markdown` constitutes a summary. A title,
actions, events, or empty headings do not. Empty kept model output raises before
persistence and retains debt; previously good output survives. Three empty kept
failures exhaust the durable budget: one transaction marks the outbox dormant and
sets `summary_blocked_reason=empty_output_exhausted`, `summary_due_at=null` on the
still-owned conversation. No structured content is cleared. Ordinary appends do
not reset this block; resumption requires an explicit reviewed retry. The failure
cap instead settles the outbox as summary-seen when a prior good summary already
exists, without changing that conversation; its later revisions still coalesce.
The failure
path adds one outbox read per failed attempt and one conversation read on terminal
failure, plus their metadata writes. With the gate on,
notes dedupe treats an empty checkpoint as a cache miss so retries can actually
generate a summary instead of replaying the same empty cached output. Discard is an
explicit separate outcome: its receipt never marks first-summary delivery, and
a later kept revision gets a first-summary deadline. Intake discards are never
indexed as summary debt; an existing due value is cleared when intake discards it.
Once a real summary lands,
a dirty later revision starts its own coalescing window. Local-only, deferred, locked, E2EE, manual title/overview,
client projection, terminal-no-derived and existing finalization generations are
not background repair admissions. BYOK-enrolled accounts remain blocked, with
no credential storage or platform-key substitution. Changing account funding
allows the same debt to be retried on the next repair cycle.

The shared minimum builder records `title_provenance=server_minimum` only with
the first-summary gate on. That server field is omitted when unset and excluded
from model-generation JSON schemas. The existing plaintext write codec stamps
`summary_first_pending_at`, `summary_due_at`, `summary_title_provenance`, lane and
presence without a read. Appends preserve the canonical row's metadata. Historical
rows without that provenance are deliberately not inferred from title text:
this PR does not bulk-enroll previously unmarked conversations. A separately
reviewed, owner-scoped migration is required to establish provenance for those
rows. Enabling the new flag alone is not a historical backlog drain.

Only the existing scheduled two-minute sequencer sweep scans indexed overdue `summary_due_at` rows,
including completed kept minimums. A global Firestore cursor/lease permits one
scan per 120 seconds, a configurable fetched-document budget (default 100) and **8 admission attempts
by default** per winning tick shared across two phases. First scan pending times in
`[now - max_age_seconds(), now - max_age_seconds() + REPAIR_NEAR_EXPIRY_SECONDS]`
oldest-first; then scan the rest of the window newest-first. The named margin is
five intervals (600 seconds), allowing up to 40 admission attempts before expiry
at the default cap and configured cadence. This is headroom, not a guarantee
under overload or blocked admissions. With the age gate disabled, preserve the
legacy due-time/name order and flat cursor, including due rows with no pending
timestamp; admission uses their existing due time as the pending-time fallback.
Both order by due time then document name to break pending-time ties.

Version 2 of the same cursor document stores independent `near_expiry` and
`newest` cursors under `phases`. Legacy flat cursors rewind safely, preserving
the existing lease/next-tick fence; flat fields are cleared so older readers also
rewind on rollback. Each phase wraps at exhaustion and passes blocked rows.
A phase stopped by the attempt cap resumes at the last examined row, never the
unattempted fetched tail. Per-owner deferrals retain the cursor immediately
before the first skipped candidate, so it is eligible again next tick even while
other owners later in this bounded page can be served. Near-expiry admissions
consume capacity first; only remaining reads and attempts go to newest-first. A large newer pile cannot
consume the expiry band's budget. Urgent overload can consume all capacity.

`SUMMARY_DEBT_REPAIR_ADMISSION_LIMIT` is a startup setting clamped to 1..60
(default 8; invalid uses 8). At 30 ticks/hour, the configured ceiling is
`limit * 30`: 240 attempts/hour by default, 1,800 at the upper bound. Lead2 ruling `d233ac` (2026-11-10) sets the code
default to 8. Earlier ruling `8b9c8f` keeps the explicit production
backend-integration override at 8: 240 attempts/hour, 5,760/day. The capacity record
`data/run-2026-11-08-retro-fixnow/out-sd-capacity.md` uses a $0.0054/repair
mean, giving $31.10/day at full admission. This is a planning estimate using
a mean, not a hard spend bound. Production cap rollback: 10 in both the prod
runtime overlay and ops values, regenerate the runtime manifest, then deploy
through the authorized lane. No live deployment is performed by this change.
`SUMMARY_DEBT_REPAIR_PER_OWNER_LIMIT` is clamped to 1..10 (default 3; invalid
uses 3). One owner share covers both phases in a tick. Failed/blocked attempts
also consume the share, preventing one owner from spending the global attempt
budget. These limits are configuration, not rollout flags. Unset either setting
to restore its code default on process restart.
Fairness applies to the fetched sample; a heavy owner filling a whole configured scan
budget can still delay discovery beyond the page.

`SUMMARY_DEBT_REPAIR_SCAN_LIMIT` is startup config, default 100, clamped to
1..5,000 (invalid values restore 100). No environment override is added here.
Owner ruling `215fdc` raises the allowed maximum; it does not raise the default.
Both phases share this tick budget. Queries return at most 500 documents per
chunk. Stop fetching at the admission-attempt cap, document budget, or a
90-second scan-work budget checked between rows/chunks. An in-flight RPC can
finish later; this is a soft deadline with headroom before the 120-second lease.
Each durable phase cursor continues after every examined row, including owner
deferrals, across chunks and ticks, then rewinds when exhausted. Admission/time
stops retain the fetched but unexamined tail. Deferred rows stay separately in
the conversation debt store with their original `summary_due_at`; a later pass
or wrap selects them again without a retry queue or a new debt generation.
This keeps an owner quota from pinning discovery before another owner. The
version-2 phase cursor and gate-disabled flat due/path shapes stay unchanged;
older readers can continue them or safely rewind.

At 720 ticks/day, each 100 returned documents/tick means 72,000 document
reads/day at full scan utilization. The 2,800-row target means 2,800 document
reads/tick and 2,016,000/day; the maximum 5,000 means 3,600,000/day. These are
row-read arithmetic, excluding query retries, empty-query minimums, index-entry
charges, cursor transactions and admission/fence/outbox reads. The supplied
`a7dc6f` measurement (~84k rows, mostly refusals) implies an ideal pass of
~28 hours at 100/tick and exactly one hour at 2,800/tick; **under** one hour
requires more than 2,800/tick, before admission/time stops or cursor rewinds.
A debt-only index/filter that skips refusals is the structural fix and is out
of scope. Neither measured production pass time nor read-billing savings are
claimed by this source-only change.

Existing eligibility excludes deleted, discarded and local-only rows. There is
no reliable denormalized Home-today or active-user rank on the debt row. That
preference is deferred; repair adds no per-row user reads for ranking.

Admission transaction rechecks manual/lifecycle/privacy,
account deletion, BYOK, active outbox lease and generation ownership; it reuses
the same outbox key and transcript generation. The eventual lifecycle write
rechecks repair eligibility and transcript revision. No new finalization job or
revision is manufactured. The original backfill worker binding is retained.

Default worst-case document-read budget, excluding transaction retries: 100 scan reads
+ 1 cursor claim + 1 cursor finish + 8 × 8 admission reads = **166 per winning
tick, 119,520/day** at the existing scheduled two-minute cadence. At the maximum
configured 60 attempts, the same formula is 582 reads/tick; owner shares and
short pages can lower actual work. These are calculated ceilings, not measured
throughput or spend. Duplicate scheduler deliveries cost one cursor read each and are refused by the durable
lease/next-tick fence. Batch pump invocations never run the scan or read its cursor.
Queries may additionally bill bounded index-entry batches because the cursor
orders by timestamp and document name. Empty/short pages reduce cost. Both gates
off incur **zero additional repair reads**. There is one minimal content-free
hashed scheduling receipt per successfully summarized conversation, so later
revisions coalesce without another conversation read; dormant receipts clear
owner IDs, conversation IDs, language and dispatch binding and are excluded from
numeric due scans.

## Receipts and alerting

`omi_summary_terminal_total{lane,reason,structured_present}` is emitted **after**
the fenced durable write; durable completion metadata is stored in the same
write. Lanes: live, fresh, backfill, integration, batch, unknown. Reasons:
summary, discarded, accept_unknown, blocked_byok, local_only. Lost outbox acknowledgement or
Firestore retry does not create a second first-summary receipt. An absent
server acceptance timestamp is reported `accept_unknown`; no zero-latency
sample is invented. When known, `omi_accept_to_summary_seconds{lane}` measures
first durable minimum acceptance / server processing admission to durable summary.
It is not capture-duration, ASR-latency or full-upload queue latency.

`omi_summary_debt_overdue` and `omi_summary_debt_oldest_age_seconds` describe the
**current bounded repair sample**, not a fleet census. `expired_seen` remains
sampled without consuming admission attempts. Tick counts include
`near_expiry_admitted` (successful urgent redrives), including zero on unclaimed
or disabled ticks. Both sweep responses expose this count as
`summary_debt_near_expiry_admitted`; `omi_summary_debt_near_expiry_admitted` is
the corresponding gauge for the last claimed tick. Unclaimed/disabled ticks
leave gauges and the sample timestamp unchanged. Both phases retain the existing
overdue/oldest/sample/expired gauges.
`omi_summary_debt_sample_timestamp_seconds` identifies the winning sampler;
ignore replica samples older than 300 seconds, then alert on oldest age >120s
for ten minutes or sustained overdue debt >0. Use max across fresh replicas;
do not sum windows or include a former sampler's stale gauge.
A healthy window does not establish fleet completeness. These are gauges of
server-provenance debt only; unmarked historical rows are outside the numerator.
No recurring COUNT scan was added. Process death after commit but before metric
emission can lose a Prometheus observation; the durable metadata remains truth.

`omi_summary_debt_repair_total{outcome}` accumulates completed-tick counts with
exactly `scanned`, `admitted`, `error`, `expired_seen`, `near_expiry_admitted`.
It increments after cursor completion, outside transactional callbacks; `error`
maps to the returned `errors` count. Transaction retries never recount a tick.
Unclaimed/disabled ticks return zero and add no counter increments. After deploy,
read `rate(omi_summary_debt_repair_total{outcome="admitted"}[10m])` and the
`near_expiry_admitted` outcome alongside release identity and summary receipts.
These are repair redrive admissions, not completed summaries.

The ASC `(summary_first_pending_at, summary_due_at, __name__)` composite remains
for the expiry phase. The additional DESC/ASC/ASC collection-group composite
must be **READY before deploying** this query change. Declare and provision it
through the existing index lane; this code change does not apply indexes.

## Production policy and rollback

The checked-in production policy is ship-on. Keep the six hosts aligned:
backend-listen, pusher, backend, backend-sync, backend-sync-backfill and
backend-integration use `FIRST_SUMMARY_DEADLINE_ENABLED=true` and
`FIRST_SUMMARY_DEADLINE_PERCENT=100`. The scheduled backend-integration owner
has `SUMMARY_DEBT_REPAIR_ENABLED=true` and admission limit 8 in production
source; backend-sync stays disabled. Keep the prod overlay and ops values
aligned and regenerate the runtime manifest. The new DESC index must be READY
before deploying this repair order; the scheduler and provider are unchanged.

The master flag also routes summary enrichment on both HTTP adapters through
the existing `postprocess_executor` rather than the STT `sync_executor`.
The sync pool has sixteen workers; an on-time Cloud Tasks delivery can still
wait behind long transcription there. The post-processing pool already hosts
ordinary finalization; this separates work classes without resizing a pool or
adding instances. Flag off restores the original adapter pool. A real-executor
regression fills a transcription pool and verifies a summary can finish.

Rollback the sweep with `SUMMARY_DEBT_REPAIR_ENABLED=false`; rollback deadline
processing with `FIRST_SUMMARY_DEADLINE_ENABLED=false` on every host. Existing
durable work remains retryable. A percentage rollback retains the explicit
allowlist and, where configured, previously admitted deadline protection.

The current finalizer also finishes an eligible completed server minimum
under its existing job lease before terminal fanout. Rich completed rows,
manual/local-only/privacy/discarded rows and exhausted empty-output budgets
are excluded. No second finalization generation is created. A summary failure
keeps the original job retryable. Background repair still refuses every
finalization-owned generation.

Do not bulk-repair a conversation merely because its admission projection
still says `finalization_status=queued` or it lacks a first-pending marker.
Check the authoritative job and actual summary presence first. Live hosts
without the summary gate previously produced rich summaries without these
metadata fields.

`omi_closed_to_summary_seconds` supplements the existing acceptance histogram
using the later of acceptance and `finished_at` (last speech). This excludes
open-speech overlap while retaining silence-close and provider/queue delay.
Missing acceptance/finish or a finish in the future produces no sample. It
does not reconstruct a historical close timestamp or prove fleet-wide SLO
coverage before all processing hosts run the instrumentation.

## Original qualification sequence (historical)

1. Merge the manifest and run/approve `.github/workflows/gcp_firestore_indexes.yml`
   for its exact commit. Wait for the declared collection-group ascending index on
   `conversations.summary_due_at` to be **READY** in the target project. Keep repair
   off. The backend train's firestore-readiness gate requires the manifest to be
   present and READY; shipping the image first is not a valid order.
2. Ship the normal backend train dark to all producers/workers after index readiness.
   Then set `FIRST_SUMMARY_DEADLINE_ENABLED=true`,
   `FIRST_SUMMARY_DEADLINE_PERCENT=<qualification percent>`,
   `FIRST_SUMMARY_DEADLINE_SECONDS=120` on backend-sync, backend-sync-backfill,
   backend-integration and batch projection/enrichment hosts. Keep
   `SUMMARY_DEBT_REPAIR_ENABLED=false` initially. The stable percentage selection is enforced
   at writes, mark/claims and repair. Keep demand/lazy/tool and repeat-work flags
   unchanged during this qualification.
3. For the same canary set `SUMMARY_DEBT_REPAIR_ENABLED=true` on existing repair
   owner (backend-sync; the existing two-minute sequencer endpoint). Produce synthetic
   ended/continuous-append uploads, kill a synthetic worker after minimum commit,
   and verify the same generation gets a real persisted/rendered summary.
   Confirm manual/deleted/local-only/BYOK rows never run managed repair.
4. Check latency/debt, LLM capacity and cost before removing the allowlist.
   Live/backend-listen receipt coverage additionally requires the first-summary
   gate on those processing hosts. Historic unmarked debt requires the separate
   provenance migration described above.
5. Rollback: set `SUMMARY_DEBT_REPAIR_ENABLED=false`, then
   `FIRST_SUMMARY_DEADLINE_ENABLED=false` on every changed host; retain the
   index and metadata. No data rewrite is needed. Existing owner contexts keep
   their persistence fences for already-running workers; future work uses the
   original scheduling/lease policy. At `FIRST_SUMMARY_DEADLINE_PERCENT=0`, an
   empty or omitted allowlist fails closed and admits nobody.

## Local acceptance

Run serially with `nice -n 19`, from backend unless otherwise stated:

- `.venv/bin/python -m pytest tests/unit/test_summary_delivery.py -q`
- `.venv/bin/python -m pytest tests/unit/test_summary_persistence.py -q`
- `.venv/bin/python -m pytest tests/unit/test_sync_reprocess_coalesce.py -q`
- Firestore emulator: `tests/integration/test_summary_debt_repair_firestore.py`
  (loopback demo project only). Covers minimum-before-mark worker death, lost
  enqueue ACK, active/expired lease, replaced writer, empty output, blocked BYOK,
  manual/discard/deletion/privacy fences and rotating deadline repair.
- Repository root: `make preflight`.

This local evidence is not deployment, historical repair or rendered-device
acceptance. The lead's canary must verify those layers before fleet enablement.
