# Shadow slot conditional arbitration

The batch shadow rendezvous (four `_shadow_slots` documents deciding which
replica offers, stages and consumes real-upload shadow units) moved from
transaction arbitration to per-slot conditional writes. Shipped default-on
2026-11-03.

## Root cause (prod evidence)

Every `offer`/`reserve`/`take` cycle read **all four** slot documents inside
one Firestore transaction, so any slot write anywhere aborted everyone else's
transaction. Four replicas offer every few seconds, reserve on every admitted
upload and take on every worker cycle, and the five-attempt retry chain then
surfaced:

- `firestore_transaction_contention operation=batch_shadow_offer attempt=5/5 outcome=exhausted`
- `background_task failed: batch_shadow_take — FirestoreContentionExhausted`
- `firestore_transaction_contention operation=batch_pipeline_store attempt=5/5 outcome=exhausted`

These were the three largest signatures in the 30-minute prod sensor window
(2026-11-03: ~1,800 combined events per window).

## The change

`ShadowStore` now arbitrates each state change with per-slot **point reads**
plus **update-time-fenced conditional writes**
(`firestore.LastUpdateOption(snapshot.update_time)`, SDK retries off) — the
same pattern `FirestoreStore.acquire_pull_claim` proved for scheduler shard
claims:

- `offer`: one fenced write per cycle, no transaction at all (it was the
  hottest cycle: ×826/30m). Losers skip the cycle; the next cycle re-reads.
- `reserve`: duplicate refusal via job-document `create`, hourly spend read
  in single-document transactions, admission order committed by winning the
  slot fence, spend bound **after** the fence.
- `take`: identity/privacy re-verified in a read-only single-job transaction
  before the fenced consume, then the running pin in its own transaction.
- `finish`: single-job settlement transactions, keyed only by that job.
- Displaced jobs: an offer cycle that reclaims a slot settles the displaced
  job in its own transaction — but never a `running`/`recovering` job (a
  `take` closes its slot the moment it hands the job over, so the consumer
  owns that settlement; `recovery_transport_failed` documents the same rule).
- The explicit displaced-pointer delete on every merged slot write prevents
  a stale `segment` leaking onto a new owner.

Invariants preserved from the transactional ring: duplicate suppression,
the 200-units/hour shared spend cap, privacy checks before every consume,
hashed-owner-only metadata, the four-slot bound and no pending queue. One
behavioral nuance: under concurrency a unit may skip one cycle the old ring
would have admitted after retries — shadow is disposable by design.

## Rollout and rollback

The shared batch contention kill switch selects the lane:
`BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false` (worker chart value
`worker.contentionRetryEnabled`, already declared in the feature-flag
registry as `ops_kill`/`keep`) restores the transactional ring in one step.
The
transactional ring remains fully wired and certified
(`tests/unit/test_batch_pipeline_shadow.py`), and the fence lane is certified
by `tests/unit/test_batch_shadow_slot_cas.py` (106 tests) on a lane-specific
fence-racing Firestore double
(`tests/unit/fixtures/shadow_slot_cas_firestore.py`).

Failure-Class: new — declaring FC-batch-shadow-ring-contention. The violated
contract: every shadow rendezvous operation read all four slot documents in
one Firestore transaction, so concurrent offer/take/reserve cycles shared one
read set and Firestore aborted them all, surfacing as
`firestore_transaction_contention operation=batch_shadow_offer attempt=5/5
outcome=exhausted` and `background_task failed: batch_shadow_take —
FirestoreContentionExhausted` in production logs. Canonical prevention:
arbitration without a shared transaction read set — per-slot point reads plus
an update-time-fenced conditional write per state change, implemented by this
change and pinned by `tests/unit/test_batch_shadow_slot_cas.py` plus the
arbitration section of `backend/docs/batch-pipeline-shadow.md`.
