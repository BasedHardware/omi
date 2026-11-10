# In-flight capture ledger (C1a)

Adds a write-only, fail-open in-flight ledger for the capture pipeline. One
document per capture lives under `users/{uid}/pipeline_ledger/{capture_id}` and
records `stage`, `entered_at`, `deadline_at`, `attempt`, `reason`, `end_type`,
`end_at`, the last 16 transitions, and `expires_at` on a terminal. The stage
table is plain data (`database/pipeline_ledger.py`), so the same contract can
move to Postgres without changing callers.

Stages: `capturing`, `sealed`, `transcribed`, `noted`, `done`; terminals
`no_speech`, `noise`, `failed:<reason>` with a bounded reason set. Every
nonterminal stage has a deadline and an exit; `advance()` is idempotent for the
same stage and refuses backward transitions.

This change instruments two transitions:

- **seal** — `database/record_audio.py` writes `sealed` in the seal transaction.
- **notes done** — `database/conversations.py` writes `noted` in the processing
  result transaction when the receipt is a first durable summary.

Admission (`utils/batch_pipeline/live.py`) and transcript landed
(`database/batch_pipeline_projection.py`) are deferred to C1b because #24893
still owns those files. Episode composed and the terminal exits are also C1b.

## Fail-open and atomicity

The ledger read and plan happen before the real transaction, so the real
transaction stays write-only. A ledger read, plan or metric error returns
`None` and the real transition proceeds unchanged. When a plan exists, the
caller writes it with a plain `set` inside its own transaction, so the ledger
commits with the real transition. The ledger `set` targets a new collection in
the same project and cannot fail independently of that transaction.

## Switch and rollback

`PIPELINE_LEDGER` defaults on (`config/refactor_modes.py` `default_on`). Set it
to `false`/`0`/`off` to stop all ledger writes; capture, notes and episode
behavior are unchanged. No data deletion is needed. Terminal documents carry
`expires_at` for a Firestore TTL policy; the policy itself is a deploy step.

## Metrics

`omi_pipeline_ledger_advance_total{stage, outcome}` counts advance attempts and
`omi_pipeline_ledger_stage_seconds{stage}` records time in a stage before its
next transition. Both are content-free: no uid, capture id, transcript or
reason text. Failure reasons collapse to the `failed` stage label.

## Coverage

C1a covers new captures that reach seal and first durable notes. The 99.5%
coverage target is measured after C1b adds admission and transcript landed.
