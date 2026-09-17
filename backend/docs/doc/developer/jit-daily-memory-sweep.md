# Daily memory sweep contract

The [admission and deferred-unlock design note](daily-sweep-admission-and-unlock.md)
describes the permanent window lock, required first-deployment drain,
claim-bound operator abandonment, deferred replay design, read bounds and limitations.

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

Eligibility and selection have separate budgets. The `started_at` timestamp
range projects `started_at`, `status`, `finished_at`, `discarded`, and `is_locked`,
ordered by `started_at ASC, __name__ ASC`. At most 100,001 projections are read;
more than 100,000 scanned rows returns `source_scan_over_budget`. The separate
2,000 eligible-row ceiling excludes discarded/locked rows and returns
`eligibility_scan_over_budget`; an unfinished visible row returns
`row_not_eligible`. These results cannot advance the cursor or dispatch.

Projection and subsequent full reads are not atomic. Mutations beyond the
full-read page and late inserts are not rechecked; even selected rows can
change afterward. This is an observed-read eligibility check, not a stable
whole-window snapshot or ingestion seal. Admission protects only code that
participates in the shared admission protocol. The deployment note explicitly
requires draining pre-lock workers for the first transition.

There is no explicit settle margin: the previous local date is eligible as
soon as midnight passes, potentially arbitrarily close to window end. Missing
or string-typed `started_at` values are not covered by the timestamp query.
Conversations are attributed to their start day, not finish day; `finished_at`
is required to be a datetime but is not required to precede window end.

After the scan succeeds, only the first `min(2 * max_conversations, 400)`
eligible IDs in that total order have their full documents read (16 for QA).
Those reads recheck eligibility and the start time; a missing or moved document
returns `source_row_changed`. The selected page ranks structured summaries,
longer summaries, later start times, then IDs. An individually oversized row is
always skipped, even after selection began; remaining rows stop at the first
aggregate budget overflow. Selected rows are finally sorted by ID. Thus a
successful attempt reads at most 100,000 projected and 400 full documents (16 in
QA); a scan-overflow attempt reads 100,001 projections and no full documents.
Firestore projections reduce payload, not billed document reads.

Rows locked in the projection are excluded like discarded rows before full
content reads. Full-document reads recheck locking before building provider
input. This matches chat RAG's exclusion and integration rendering's removal
of locked summaries/evidence. They do not hold the day open;
a day consumed while locked is not revisited after later payment unlocks it.
Replay is deferred to a separate PR; payment unlock is unchanged. Exclusions
are counted without IDs. The completed-day agent rechecks selected rows' locks
before each provider phase (up to 200 additional reads per phase, 8 for QA),
failing closed if a row locks, disappears or cannot be read. A lock committed
after its last check can still race the external request; no atomic cross-system
privacy guarantee is claimed.
Onboarding uses the same lock exclusion before its additional finalization
check, so it cannot route a locked transcript around the completed-day gate.
`rows_seen` counts eligible projected rows, `rows_used` counts selected rows,
and the selection cap no longer treats an exactly-full query as truncation.
Contentless eligible rows are counted as omissions and set the truncation flag.
Source evidence belongs to the producer/stage;
the agent receives a separate dispatch-evidence dictionary. The scheduler and
both QA receipts accept only `SOURCE_REASON_CODES`; other values become
`unknown_reason`.

Both completed-day and onboarding invocations use stable owner/source/window/
generation identity. A durable window admission lease commits before its identity factory runs;
a holder-checked transaction then binds the result independently of mutable text. Both payload
and content-free fence bind a separate input digest; only certified pre-dispatch
release can change it. The existing three-release limit and claim binding remain.
Lease expiry permits another admission holder, never another invocation ID.
See the design note for mutation interleavings, distinct failure reasons, and the
single operator skip exit through the existing repair attestation machinery.

All new lookups use single-field range indexes or equality index merging; no
new composite index is needed. The emulator proves query/transaction semantics,
not the serving index state of a remote deployment.

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
