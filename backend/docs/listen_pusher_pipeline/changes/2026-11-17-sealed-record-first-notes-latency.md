# 2026-11-17: a sealed live record's first notes wait for neither the deadline nor a held unit

## What changed

- `ProjectionStore.complete` (eager record notes off, as in production): when a record binding completes, the
  ledger's `transcribed` is written before any notes wake, and each output that passes `capture_end.seal_barrier`
  has its existing open notes obligation moved to due now in the same transaction, then woken after commit.
  Before, the obligation waited for its 120 s first-summary deadline after the first unit's mark.
- `ProjectionStore.hold_for_quarantine`: when a unit is held for recovery and every other unit of the record is
  projected, a row that passes the barrier gets the same move. If the row already has a hold state, the transaction
  stamps `sync_processing_hold.units_settled_seal_at = record_sealed_at`.
- `capture_end.seal_proof` returns `units_held` while that stamp equals `record_sealed_at`; `database.capture_end`
  counts it as `sealed_held` and skips the ledger read. A reseal moves `record_sealed_at`, so an old stamp proves
  nothing.
- `FirestoreEnrichmentOutbox.expedite` / `outbox.expedite_update`: the move never creates, reopens, re-leases or
  unparks an obligation, and ignores empty-blocked or already-due rows.

## Why

Prod, 2026-11-17, one user's batch-owned recording (36 min, 8 units): cut 18:06:05, sealed 18:06:11, 7 units
transcribed at 18:07:11 and projected by 18:10:25. One 92 s unit with 3.5 s of VAD speech returned empty ASR,
was quarantined at 18:07:11, and its recovery started at 19:08:56. The binding's completion (and the ledger's
`transcribed`) waited for it, so the seal proof failed. The first-summary deadline run at 18:13:09 deferred on
`quiet_wait` behind a phone copy that merged at 18:12:38; notes landed at 18:24:54. Records without a held unit
still waited for the 120 s deadline after the first mark (ledger `noted - transcribed` = 137 s on 2026-11-17 11:01).

## Scope

The move and stamp are the first notes only: the barrier refuses rows with notes. A held unit that recovers later is
late content: normal hold epoch, at most one material late run. Accepted tradeoff: an immaterial or capped
(`immaterial`, `late_cap`) recovered unit lands in the transcript but not in the notes. A unit still transcribing
(not quarantined) keeps the existing wait. Partial-record pages and non-record bindings are untouched.

Ordering: the obligation moves to due now inside the completion (or held-unit) transaction; the ledger's
`transcribed` is written after that commit and before the wake. A wake failure on either path is logged and left to
the outbox sweep; it never fails the unit job or skips the completion's post-commit steps.

Writes: one outbox row update per qualifying completion or held-unit hold; one conversation field update the first
time a held row's seal is stamped. Reads: one conversation and one outbox document in the held-unit transaction.

## Kill switch and rollback

`SYNC_UPLOAD_WATERMARK_ENABLED=false` turns off the move, the stamp and both proofs. A left-over stamp proves
nothing once the switch is off or the row reseals. No migration.

## Readback

`omi_sync_capture_end_proof_total{result="sealed_held"}`; `omi_sync_processing_hold_total{outcome="end_proof"}`;
`summary_completed_at - record_sealed_at` on `batch_live_v1` rows.
