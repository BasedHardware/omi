# In-flight capture ledger (C1a)

Adds a write-only, fail-open in-flight ledger for the capture pipeline. One
document per capture lives under `users/{uid}/pipeline_ledger/{capture_id}` and
records the C2 census fields (identity, stage, deadlines, bounded reason, end
type and firing clock, speech basis, revision, terminal, last 16 transitions,
terminal TTL). The stage table is plain data, so the contract can move to
Postgres without changing callers.

Stages: `capturing`, `sealed`, `transcribed`, `noted`, `done`; terminals
`no_speech`, `noise`, `failed:<reason>` with a closed reason vocabulary. Every
nonterminal stage has a deadline and an exit. `advance()` is idempotent for the
same stage and revision, refuses backward transitions, and re-opens a terminal
only with an explicit higher revision. Terminal rows are retained for at least
26 hours (`PIPELINE_LEDGER_TERMINAL_TTL_SECONDS`, default 93600, capped at 7
days) so the C2 24h exact census plus grace can read them.

Instrumented: **seal** (`database/record_audio.py`, after the seal commits),
**notes done** (`database/conversations.py`, after a first durable summary
commits), and **upload failure** (`failed:upload_failed`, `end_type=unknown`).
A deleted capture gets no ledger row. Admission (`utils/batch_pipeline/live.py`)
and transcript landed (`database/batch_pipeline_projection.py`) are deferred to
C1b because #24893 still owns those files; episode composed and the remaining
terminal exits are also C1b.

## Fail-open and atomicity

The ledger is written **after** the real transition commits, in its own
Firestore transaction. A ledger read, plan, write or metric error is caught and
the real transition stays authoritative. The ledger transaction reads the
document before writing it, so concurrent writers are serialized by Firestore's
optimistic concurrency (a CAS fence) and a stale plan cannot overwrite a newer
stage.

The trade-off is explicit: the ledger is **not** atomic with the real
transition. A crash between the real commit and the ledger write loses that
row; the independent admission counter makes the loss visible. Same-transaction
atomicity and fail-open cannot both be guaranteed at these sites, and the brief
requires that an optional ledger failure never turns a successful transition
into a user-visible failure.

## Switch, rollback, metrics, read helper

`PIPELINE_LEDGER` defaults on (`config/refactor_modes.py` `default_on`). Set it
to `false`/`0`/`off` to stop all ledger writes; capture, notes and episode
behavior are unchanged. No data deletion is needed. Terminal documents carry
`expires_at` for a Firestore TTL policy; the policy itself is a deploy step.

Metrics: `omi_pipeline_ledger_admit_total` (independent coverage denominator),
`omi_pipeline_ledger_write_total{outcome}`,
`omi_pipeline_ledger_write_failures_total{reason}`,
`omi_pipeline_ledger_rows{stage}`, `omi_pipeline_ledger_transition_total{from,to}`,
`omi_pipeline_ledger_unknown_end_type_total`, and
`omi_pipeline_ledger_stage_seconds{stage}`. All are content-free.

`pipeline_ledger.iter_window(start, end)` and `census_window(start, end)` yield
rows with `admitted_at` in `[start, end)`. They are read-only, bounded by
`limit`, and raise `LedgerWindowTruncated` instead of silently sampling. C2
reads only through this helper.

`users/{uid}/pipeline_ledger` is in the portability export inventory and is
erased by the recursive account wipe. The document never stores titles,
transcript or overview text, audio paths, secrets or raw content.

C1a covers new captures that reach the seal barrier and first durable notes.
The 99.5% coverage target is measured after C1b adds admission and transcript
landed.
