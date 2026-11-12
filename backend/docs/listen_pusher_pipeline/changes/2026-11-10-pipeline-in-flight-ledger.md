# In-flight capture ledger live hooks (C1b-1)

Wires the first production writers into the write-only, fail-open in-flight
ledger. One document per capture lives under
`users/{uid}/pipeline_ledger/{capture_id}` and records the C2 census fields
(identity, stage, deadlines, bounded reason, end type and firing clock, speech
basis, revision, terminal, last 16 transitions, terminal TTL). The stage table
is plain data, so the contract can move to Postgres without changing callers.

Stages: `capturing`, `sealed`, `transcribed`, `noted`, `done`; terminals
`no_speech`, `noise`, `failed:<reason>` with a closed reason vocabulary. Every
nonterminal stage has a deadline and an exit. `advance()` is idempotent for the
same stage and revision, refuses backward transitions, and re-opens a terminal
only with an explicit higher revision. Terminal rows are retained for at least
26 hours (`PIPELINE_LEDGER_TERMINAL_TTL_SECONDS`, default 93600, capped at 7
days) so the C2 24h exact census plus grace can read them. Nonterminal rows also
carry a bounded `expires_at` (7-day max lifetime, refreshed on every transition)
so a stalled row cannot live forever; the reviewed retention declaration and the
platform provisioning step now include the `pipeline_ledger` collection group.

Instrumented in this change:

- **Seal** (`database/record_audio.py`, after the seal commits):
  `capturing -> sealed`, counted only when the seal actually closes the
  recording. Admission is a durable per-capture fact (`record_admitted_at`), so
  a reconnect that re-opens and re-seals the row does not count a second
  admission or reset the ledger deadline. A partial-seal repair does not count a
  second admission either.
- **Upload failure** (`database/record_audio.py`): `failed:upload_failed` with
  `end_type=unknown`, using `record_upload_failed_at` as `end_at` and falling
  back to the observation time — never last speech and never the ledger-write
  time.
- **Notes done** (`database/conversations.py`, after a first durable summary
  commits): `noted` when the receipt reason is `summary` or `accept_unknown`;
  `discarded` and `local_only` are excluded. The same Home-ready point records
  the `done` terminal, so a noted row cannot sit past its deadline and page
  forever.
- **Deletion** (`database/conversations.py`): the sibling
  `users/{uid}/pipeline_ledger/{conversation_id}` row is removed with the
  conversation, including the merge-source delete path.

Seal and notes callers pass an ordered `source_revision` derived from the source
snapshot's `update_time` with `reopen=True`, so a proof repair can close a
`failed:upload_failed` recording and a stale failure hook loses. A delayed
post-commit write is fenced against source deletion and account erasure: inside
the ledger transaction the source and owner documents are read and the row is
not created when either is missing, deleted or gone. The refusal is fail-open
for the already-committed source transition.

Admission (`utils/batch_pipeline/live.py`) and transcript landed
(`database/batch_pipeline_projection.py`) remain deferred because #24893 still
owns those files; episode composed and the remaining terminal exits are also
still outstanding.

## Write amplification

The budget is bounded and stated per capture: **one document per capture, at
most five transitions**, 26-hour terminal TTL, 7-day nonterminal max lifetime,
and fail-open on every ledger error. The cost is not zero: every `advance()` runs
its own Firestore transaction that reads the owner, the source and the ledger
document (three reads) plus 0–1 write, and the notes hook fires on every
processing persist. The ledger write is one extra small transaction after the
real commit, never a per-frame or per-request read.

## Fail-open and atomicity

The ledger is written **after** the real transition commits, in its own
Firestore transaction. A ledger read, plan, write or metric error is caught and
the real transition stays authoritative. The ledger transaction reads the
document before writing it, so concurrent writers are serialized by Firestore's
optimistic concurrency (a CAS fence) and a stale plan cannot overwrite a newer
stage.

The trade-off is explicit: the ledger is **not** atomic with the real
transition. A crash between the real commit and the ledger write loses that
row; the independent admission counter makes the loss visible.

## Switch, rollback, metrics, read helper

`PIPELINE_LEDGER` defaults on (`config/refactor_modes.py` `default_on`). Set it
to `false`/`0`/`off` to stop all ledger writes; capture, notes and episode
behavior are unchanged. No data deletion is needed. Terminal and nonterminal
documents carry `expires_at` for a Firestore TTL policy; the policy itself is a
deploy step, and the reviewed retention declaration plus the platform
provisioning step now include `pipeline_ledger`.

Rollback is a revert: the ledger is write-only and fail-open, no read path and
no transition depends on it, so a revert restores the previous behavior
exactly. Rows already written expire on their terminal TTL or nonterminal max
lifetime.

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

Contract: [pipeline ledger](../../listen_pusher_pipeline.mdx). This change gives
the ledger its first real writers; the C2 census starts returning non-zero
coverage for new captures. It does not by itself reach the 99.5% coverage
target — that needs the deferred admission and transcript-landed hooks.
