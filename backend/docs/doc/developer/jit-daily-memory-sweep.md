# Daily memory sweep contract

`utils.memory.daily_memory_sweep` is the dark authority seam for the ratified
once-per-user-local-day memory sweep. The maintenance job contains a bounded
producer/scheduler/adaptor, but its separate backend authority remains closed
by default (`MEMORY_DAILY_MEMORY_SWEEP_ENABLED=false` plus an independent kill
switch).

## Input and output

The server constructs one immutable `DailySweepInput` per completed local day:

- `uid`, `local_date`, and the canonical `account_generation` and
  `source_generation` observed while producing the packet;
- the producer's IANA `timezone_name`, exact DST-aware `window_id`,
  `window_start_utc`, and `window_end_utc`, plus `complete=true`; an empty
  candidate list is valid only when this explicit complete-zero packet is
  durable;
- at most 32 `DailySweepCandidate` values and 16 canonical writes per day;
- bounded content, source identity, metadata-only source references (at most 8,
  matching `LedgerProvenance.quote_refs`), and an
authority of `direct_user_statement`, `agent_reusable_conclusion`, or
`sweep_inference`.

The runtime adapter reads a bounded backend-produced packet at
`users/{uid}/daily_memory_sweep_sources/{local_date}`. Its three typed channels
are `daily_summary`, `onboarding_cold_start`, and
`existing_trigger_reconciliation`; this staging packet is not a memory
authority and is inert while the backend switch is closed. When staging is
absent, the completed-day producer proves an exact UTC window, excludes
discarded and locked conversations, fails closed on processing/unfinished
conversations, and runs ONE bounded two-phase agent pass over the completed day: the conversation SUMMARIES form the bounded spine
(never photos, screen pixels, or today's partial window), and the agent may
request a bounded number of raw transcript excerpts (at most 8, capped per
fetch) to verify specific details before finalizing. Every memory must cite
the conversation ids it came from; memories without provenance into the day's
rows are dropped. The same run assigns folders for the day's unopened,
unfiled conversations (a folder set by the first-open worker or the user
always wins; assignment is idempotent and best-effort). An optional typed
summary packet is accepted only when it explicitly attests completion; a
missing or failed source remains incomplete and cannot advance the cursor.
Model-produced candidates require the separate model/cost authority and
bounded deployment flags `MEMORY_DAILY_MEMORY_SWEEP_MODEL_*`. The onboarding
cold-start channel still reads bounded per-conversation transcript text
through the existing memory extractor.

When the completed-day agent path invokes the model, both phases run inside a
single at-most-once invocation, and the full bounded candidate page (memory
candidates plus folder assignments) and its digest are staged under the
sweep-owned control path before any candidate can be applied. A later retry
reads that exact stage; a missing or malformed stage is incomplete and never
triggers a second, nondeterministic extraction. The one exception is a stage
written under an older `daily_memory_sweep_daily_summary_stage.*` schema
version (a deployment boundary): that deployment owned the window's model
invocation and its own apply path, so the reader attests an empty page and
lets the cursor advance instead of stalling every user on a schema bump. The
cost gate is a ceiling checked before any provider call: twice the spine
characters, plus the full transcript-fetch budget, plus the clamped
model-controlled phase-B additions (draft memories, request reasons, prior-
memory lookup queries and results) must fit
`MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD` (set it to at least ~$0.80 to
cover maximal days; typical days ceiling far lower).


### Completed-day source bounds and invocation ownership

Eligibility and selection have separate budgets. One `started_at` range query,
ordered by `started_at ASC, __name__ ASC`, projects only `started_at`, `status`,
`finished_at`, `discarded`, and `is_locked` (document IDs are implicit). The
query returns at most 2,001 rows: a 2,000-row eligibility ceiling plus one
probe. Overflow returns `eligibility_scan_over_budget`; an unfinished visible
row anywhere in the projection returns `row_not_eligible`. Neither result
advances the cursor or dispatches. At exactly 2,000 rows the scan is complete.
This is a bounded snapshot of the window, not an ingestion seal: a later insert
cannot be observed retroactively, but it cannot reopen a claimed invocation.

After the scan succeeds, only the first `min(2 * max_conversations, 400)`
eligible IDs in that total order have their full documents read (16 for QA).
Those reads recheck eligibility and the start time; a missing or moved document
returns `source_row_changed`. The selected page ranks structured summaries,
longer summaries, later start times, then IDs. An individually oversized row is
always skipped, even after selection began; remaining rows stop at the first
aggregate budget overflow. Selected rows are finally sorted by ID. Thus a
successful attempt reads at most 2,000 projected and 400 full documents (16 in
QA); a scan-overflow attempt reads 2,001 projections and no full documents.
Firestore projections reduce payload, not billed document reads.

Rows locked in the projection are excluded like discarded rows before full
content reads. Full-document reads recheck locking before building provider
input. This matches chat RAG's exclusion and integration rendering's removal
of locked summaries/evidence. They do not hold the day open;
unlocking later does not make a consumed day eligible for another sweep.
Onboarding uses the same lock exclusion before its additional finalization
check, so it cannot route a locked transcript around the completed-day gate.
`rows_seen` counts eligible projected rows, `rows_used` counts selected rows,
and truncation means eligible rows were actually omitted, never just that a
query exactly filled its limit. Source evidence belongs to the producer/stage;
the agent receives a separate dispatch-evidence dictionary. The scheduler and
both QA receipts accept only `SOURCE_REASON_CODES`; other values become
`unknown_reason`.

The completed-day invocation key is `(uid, local_date, window_id,
account_generation, source_generation, sweep_generation)`, with no source-text
or selection digest in its identity. In the same transaction that claims the
durable fence, both the content-free top-level fence and the user invocation
payload record `input_digest`, `claim_id`, generations, window, state `pending`,
and the existing pre-dispatch release count. Ordered IDs are not frozen: this
chooses window ownership with digest-bound replay instead of a stored selection.
The staged page retains its existing transcript and candidate digest checks.

- `pending` / `indeterminate` / `pre_dispatch_exhausted` cannot auto-dispatch.
  An exact-claim operator repair still requires the existing no-provider-call
  evidence, and cannot substitute a different input digest.
- `returned` replays only the matching input digest and validated unexpired
  output. After a failed stage write, the same source can stage that output.
  Late earlier rows, deleted boundary rows, summary edits, or first-open
  enrichment that change selection/text/evidence fail closed, without a new
  invocation or a stage under a different digest. This also closes the
  under-budget summary-edit redispatch path.
- Only `pre_dispatch_released`, certified before the provider-dispatch latch,
  may bind a freshly selected digest under the SAME invocation ID. Claim-ID
  binding and `MAX_PRE_DISPATCH_RELEASES` remain authoritative.
- Overlapping new workers contend on one fence; the loser cannot dispatch.
  Deletion and live account/source generation checks still run transactionally
  before claim/finalize/stage. The top-level fence survives user deletion.

Before creating a new window fence, its transaction also checks for any existing
fence with the same UID, window, and generations, projecting one document ID.
This prevents old transcript-keyed receipts from being bypassed after an
upgrade, even if their user payload was deleted. Historical fences without a
usable stage remain incomplete; they are not automatically adopted or reset.
Drain older workers before activation: an older binary does not honor the new
window key. No rollout or repair is performed by this source change.

No new composite index is required. The source range uses the existing
ascending `started_at` index's implicit ascending document-ID suffix. The
historical-fence query uses only equality filters and automatic single-field
index merging; see [Firestore index ordering and merging](https://firebase.google.com/docs/firestore/query-data/index-overview).
An index/query failure fails closed. The emulator proves query/transaction
semantics, but does not prove the serving index state of a remote deployment.

Onboarding provenance is a server-generated session marker written by the
listen runtime; client `source` and onboarding flags are not trusted. The
producer returns source identities separately from candidates, so a source
with multiple facts is consumed only after every candidate receipt commits,
and a zero-candidate source receives an idempotent completion receipt. The
maintenance inventory reserves a bounded onboarding page and advances its own
cursor independently of the canonical-user registry, preventing cold-start
starvation. Cohort rollout uses a read-only per-user resolver seam and fails
closed by default; it never mutates PostHog.

The runner accepts a mapping of completed local dates, derives the user's
local day through `zoneinfo`, and never consumes today's partial window. It
processes at most three missed dates per invocation. Each date returns through
the canonical ledger writer; the output exposes only counts, dates, status,
and bounded reason codes. Telemetry contains no memory text, transcript,
OCR, image, or pixel content.

The cursor stores the IANA timezone and a deterministic exact UTC half-open
window identity (`start_utc`, `end_utc`, and `window_id`). Spring-forward days
measure 23 hours and fall-back days 25 hours. A timezone change with an
existing completed cursor fails closed with
`timezone_changed_requires_reconciliation`; an operator must explicitly
reconcile rather than silently replaying an overlap or skipping a gap.
Reconciliation transactionally increments the sweep-owned receipt namespace
while preserving the completed-day anchor and leaves canonical
`source_generation` unchanged, so the next bounded catch-up uses the new
timezone without colliding with the old receipt set. The scheduler reaches
this write only after a definite per-user enabled cohort decision; disabled or
unavailable users produce no sweep control or cursor writes.

## Authority and safety

`SweepAuthorityState` is backend-owned and defaults to closed. A separate
`kill_switch_active` field overrides `enabled` on every run. Closing the seam
stops future writes and never deletes already-created user data.

Direct user statements outrank reusable agent conclusions, which outrank sweep
inferences. A lower-authority candidate cannot amend a higher-authority target.
Active canonical fact slots are checked by subject scope/entity before an add:
the sweep idempotently skips an equal/lower-authority occupant or amends it
only when the candidate is stronger. This prevents duplicate facts across
days. Facts may be added or amended automatically. A trigger can only repair
an existing active trigger whose canonical provenance is `standing_trigger`;
an inferred trigger can never be created from passive behavior alone. Trigger
conditions compile through the strict `jit_trigger.v1` schema, and a recursive
validator rejects raw/image/base64/bytes payloads at every nesting level. A
repair replacement remains `standing_trigger`; sweep provenance is recorded
separately in ledger evidence so later explicit repairs remain possible.

Account-deletion, owner, generation, and durable cursor CAS checks fail closed.
Receipt claim, receipt completion, and cursor advancement each transactionally
re-read the durable deletion marker and live account/source generations.
Receipt claims carry a unique per-invocation claimant and a short lease, so a
different concurrent runner cannot steal live work but a next-day retry can
take over an expired exact-digest claim. Receipt IDs include the source
generation; a transactional source-generation rollover preserves the exact
completed-day window identity and rejects stale packets.
The per-user cursor lives under `memory_control/daily_memory_sweep`. Each
candidate additionally gets a content-free receipt keyed by local date, source
key, and generations under `daily_memory_sweep_receipts`; onboarding sources
also receive a source-level receipt after all of their candidate receipts.
A receipt is claimed
before the canonical write and marked committed after it. If a process dies
between those steps, the pending exact-digest date is recovered even after the
wall clock advances; canonical apply idempotency prevents a second
memory/operation/commit/outbox record.

## Verification

Hermetic contract tests:

```bash
backend/.venv/bin/pytest -q backend/tests/unit/test_daily_memory_sweep.py
```

The real Firestore transaction/retry proof is deliberately on-demand and
loopback-only:

```bash
npm run test:memory-daily-sweep:emulator
```

It uses a demo project and exercises isolated synthetic users: a true crash
after canonical apply but before receipt completion plus next-day lease
takeover, a canonical-apply/deletion race, deletion-marker contention during
receipt completion followed by a wipe/retry, source-generation contention and
transactional rollover, and overlapping runners. It verifies no post-wipe
cursor/receipt recreation and no duplicate canonical records. It never targets
a real project and does not activate the production sweep.
