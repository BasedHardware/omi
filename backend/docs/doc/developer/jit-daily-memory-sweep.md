# Daily memory sweep contract

`utils.memory.daily_memory_sweep` is the dark authority seam for the ratified
once-per-user-local-day memory sweep. It is additive and has no scheduler or
current-writer integration yet.

## Input and output

The server constructs one immutable `DailySweepInput` per completed local day:

- `uid`, `local_date`, and the canonical `account_generation` and
  `source_generation` observed while producing the packet;
- at most 32 `DailySweepCandidate` values;
- bounded content, source identity, metadata-only source references, and an
  authority of `direct_user_statement`, `agent_reusable_conclusion`, or
  `sweep_inference`.

The runner accepts a mapping of completed local dates, derives the user's
local day through `zoneinfo`, and never consumes today's partial window. It
processes at most three missed dates per invocation. Each date returns through
the canonical ledger writer; the output exposes only counts, dates, status,
and bounded reason codes. Telemetry contains no memory text, transcript,
OCR, image, or pixel content.

## Authority and safety

`SweepAuthorityState` is backend-owned and defaults to closed. A separate
`kill_switch_active` field overrides `enabled` on every run. Closing the seam
stops future writes and never deletes already-created user data.

Direct user statements outrank reusable agent conclusions, which outrank sweep
inferences. A lower-authority candidate cannot amend a higher-authority target.
Facts may be added or amended automatically. A trigger can only repair an
existing active trigger whose canonical provenance is `standing_trigger`; an
inferred trigger can never be created from passive behavior alone. Raw
image/pixel markers are rejected at model validation.

Account-deletion, owner, generation, and durable cursor CAS checks fail closed.
The per-user cursor lives under `memory_control/daily_memory_sweep`. Each
candidate additionally gets a content-free receipt keyed by local date and
source key under `daily_memory_sweep_receipts`. A receipt is claimed before
the canonical write and marked committed after it. If a process dies between
those steps, the same deterministic canonical operation is retried and the
receipt completes without a second memory/operation/commit/outbox record.

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

It uses a demo project, seeds one synthetic user, deletes only that user's
sweep cursor to model an interruption after the canonical write, then verifies
the replay adds no canonical records. It never targets a real project and
does not activate the production sweep.
