# Quiet-check retirement contention budget

## Family contract

Every Firestore transaction writer on the listen recording-session documents
runs the same bounded contention budget (`database/firestore_transaction_retry.py`):
`run_transactional` restarts an expired-transaction rejection on a brand-new
transaction id, inside `run_with_transaction_contention_retry`, which replays
`Aborted` contention on fresh transactions with a bounded equal-jitter ladder
(`recording_session_open`, `recording_session_lease_renewal`,
`recording_session_lifecycle_event`, `recording_session_empty_delete`).

The quiet-check retirement boundary is part of this family: it is the
post-commit cleanup those lanes call
(`tombstone_and_delete_empty_conversation` in
`database/recording_sessions.py`, `claim_conversation_status` in
`database/conversations.py`, the finalization/recovery/oversized terminals)
and it races the same documents. Both stop lanes now compose the identical
budget:

- `stop_quiet_check_for_conversation` (`database/quiet_check_retirement.py`)
  — the latest-owner fenced retirement after a lifecycle commit. Budget
  exhaustion lands in the existing fail-open arm: the durable replay backstop
  keeps the indexed obligation, the `outcome=deferred` telemetry and the
  `omi_fallback_total` degradation event stay exactly as before, and the
  committed owner result is still never invalidated.
- `stop_quiet_check` — the delivered worker's generation-fenced retirement.
  Budget exhaustion raises the typed `FirestoreContentionExhausted` instead of
  a raw `Aborted`; the dispatched worker's at-least-once redelivery already
  treats the run as transient.

## What changed for operators

Before this change the retirement transaction was a bare
`firestore.transactional` call: the SDK replays a commit abort on the same —
often already retired — transaction id, and never retries an abort raised by
the body's read. A single transient abort during a contention burst deferred
the retirement (conversation lane) or failed a delivered worker's run after
its real work had committed (generation lane). The prod backend-listen
traceback family whose frames end in
`stop_quiet_check_for_conversation ... return stop(client.transaction())`
is that deferral surfacing as a full exception log per burst.

Now a transient burst replays: a read-time `Aborted` gets fresh transactions
up to the shared five-attempt ladder, and an expired-id rejection restarts on
a brand-new id. Only a budget that exhausts reaches the fail-open arms above,
so the deferred-retirement log line becomes a rare exhausted-outcome signal
rather than the routine sound of one abort.

Failure-Class: FC-quiet-retirement-defers-a-replayable-abort-to-the-durable-backstop
