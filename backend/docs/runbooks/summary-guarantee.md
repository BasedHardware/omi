# First summary deadline and summary debt

Code and dev defaults keep both gates false. Production config enables the
first-summary deadline for 100% of owners on all six producing/processing
hosts. Debt repair on the scheduled backend-sync owner is held off in
production (`SUMMARY_DEBT_REPAIR_ENABLED=false`, deferred by David 2026-10-20
until the Nemotron migration completes). These
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
page per 120 seconds, at most 100 documents and **10 admission attempts** per
winning tick. Cursor rotation passes blocked rows instead of permanently
starving later debt. Admission transaction rechecks manual/lifecycle/privacy,
account deletion, BYOK, active outbox lease and generation ownership; it reuses
the same outbox key and transcript generation. The eventual lifecycle write
rechecks repair eligibility and transcript revision. No new finalization job or
revision is manufactured. The original backfill worker binding is retained.

Worst-case document-read budget, excluding transaction retries: 100 scan reads
+ 1 cursor claim + 1 cursor finish + 10 × 8 admission reads = **182 per winning
tick, 131,040/day** at the existing scheduled two-minute cadence. Duplicate
scheduler deliveries cost one cursor read each and are refused by the durable
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
**current bounded repair window**, not a fleet census.
`omi_summary_debt_sample_timestamp_seconds` identifies the winning sampler;
ignore replica samples older than 300 seconds, then alert on oldest age >120s
for ten minutes or sustained overdue debt >0. Use max across fresh replicas;
do not sum windows or include a former sampler's stale gauge.
A healthy window does not establish fleet completeness. These are gauges of
server-provenance debt only; unmarked historical rows are outside the numerator.
No recurring COUNT scan was added. Process death after commit but before metric
emission can lose a Prometheus observation; the durable metadata remains truth.

## Production policy and rollback

The checked-in production policy is ship-on. Keep the six hosts aligned:
backend-listen, pusher, backend, backend-sync, backend-sync-backfill and
backend-integration use `FIRST_SUMMARY_DEADLINE_ENABLED=true` and
`FIRST_SUMMARY_DEADLINE_PERCENT=100`. The scheduled backend-sync owner keeps
`SUMMARY_DEBT_REPAIR_ENABLED=false` until the deferral above is lifted; turning
it on is a prod overlay change, not a hand edit, so the next deploy keeps it.
The bounded repair cost above is unchanged. No new index, scheduler, provider or capacity is required.

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
   `FIRST_SUMMARY_UID_ALLOWLIST=<canary uid>`,
   `FIRST_SUMMARY_DEADLINE_SECONDS=120` on backend-sync, backend-sync-backfill,
   backend-integration and batch projection/enrichment hosts. Keep
   `SUMMARY_DEBT_REPAIR_ENABLED=false` initially. The UID selection is enforced
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
