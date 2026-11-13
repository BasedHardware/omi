# Finalization replay sweep contention budget

## Family contract

Every Firestore transaction writer on the conversation-finalization lane runs
the same bounded contention budget (`database/firestore_transaction_retry.py`):
`run_with_transaction_contention_retry` replays `Aborted` contention on fresh
transactions with the bounded equal-jitter ladder, and surfaces a drained
budget as the typed `FirestoreContentionExhausted`. Inside
`database/conversation_finalization_jobs.py` the custody writers
(`claim_finalization_job`, `mark_finalization_*`, `abandon_byok_finalization_job`,
`record_meeting_receipt`, `recover_stranded_byok_jobs`, `claim_finalization_replay`)
and five of the six sweep-cursor advances (BYOK reclaim, in-progress content,
stale processing, meeting-receipt backfill, BYOK abandonment) all compose it.

The replay sweep — the recurring pass that rotates the overdue
`reconcile_after_at` window (`get_finalization_replay_candidates`) and backs
off the candidates that failed to make progress (`defer_finalization_replay`)
— races the same documents and is part of this family. Both of its
transactional arms now compose the identical budget:

- the replay cursor CAS advance
  (`finalization_replay_cursor`) — a generation-fenced compare-and-set that
  moves the window past the page it just served;
- the backoff write (`finalization_replay_defer`) — the
  `reconcile_after_at += 60s` (or terminal-`DELETE_FIELD`) update for a
  candidate whose claim made no progress.

## What changed for operators

Before this change both arms ran the decorated transaction bare: the SDK
never retries a read-time abort, so one transient `Aborted` escaped as a raw
SDK error on every burst. On the cursor arm it aborted the whole reconcile
pass before the cursor advanced — the sweep logged
`listen finalization reconciliation query failed` and returned `error: 1`,
and the next pass rescanned the same window from the top, re-reading and
re-claiming the same hot rows. On the backoff arm the reconcile callers
swallowed the abort (`quiet finalization replay backoff failed` /
`listen finalization replay backoff failed`), so the overdue row kept its old
`reconcile_after_at`, stayed at the window front, and was re-claimed by the
very next pass — contention amplified itself instead of backing off.

Now a transient burst replays: a read-time `Aborted` gets fresh transactions
up to the shared five-attempt ladder, an expired-id rejection restarts on a
brand-new id, and the equal-jitter rungs space the chain out of a burst. A
cursor advance that recovers keeps the sweep's page position, so the pass
returns its normal outcome counts instead of `error: 1`, and a backoff that
recovers actually lands, retiring the hot head. Only a budget that exhausts
reaches the callers' existing arms: the reconcile pass bounds it like any
other query failure, and the backoff callers log one exhausted outcome
instead of a raw abort per burst.

## Grid

`tests/unit/replay_budget_grid_*.py` freeze the arms' decision matrices x
contention programs (backoff predicate truth table, candidate-equality truth
table, budget knobs with aborts-then-clean chains, attempt caps and deadline
scopes; cursor shapes x due-window scenarios x programs). Each cell was
cross-verified at emit time against the hand-transcribed model in
`tests/unit/replay_budget_grid_harness.py`, which walks the real engine's
accounting (equal-jitter rungs at the pinned draw, the expired-chain ceiling,
the attempt cap, the reserve gate and the never-past-deadline check).

Failure-Class: FC-replay-sweep-cursor-and-backoff-run-outside-the-shared-contention-budget
