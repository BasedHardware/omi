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
absent, the adapter consults only the persisted completed-day daily summary
for the exact window (never today's partial conversations) and an explicit
onboarding seed channel. Missing summary/source evidence remains incomplete
and cannot advance the cursor. Model-produced summary candidates require the
separate model/cost authority and bounded deployment flags
`MEMORY_DAILY_MEMORY_SWEEP_MODEL_*`.

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
reconcile/reset the cursor rather than silently replaying an overlap or
skipping a gap.

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
key, and generations under `daily_memory_sweep_receipts`. A receipt is claimed
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
