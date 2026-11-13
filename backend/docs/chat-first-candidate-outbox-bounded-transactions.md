# Chat-first intent and candidate-outbox bounded transactions

Every transactional entry in `database/chat_first_intents.py`,
`database/chat_first_delivery_attempts.py` and
`database/candidate_integration_outbox.py` now rides the shared bounded
contention engine through `database/bounded_lane_transaction.py`
(`run_bounded_lane_transaction`). This note is the operator-facing summary of
what changed, what it costs, and what to look for in production.

## What was wrong

These lanes handed their bodies to the Firestore SDK's bare transaction
path: one transaction id created per call and handed to
`firestore.transactional`. Under write contention that fails in three
distinct ways:

- The SDK replays a commit `Aborted` on the **same already-poisoned
  transaction id**, so a chain that loses one race usually loses every
  replay inside the same collision burst.
- An `Aborted` raised by a **mid-transaction read** is never retried at all:
  it escapes as an unclassified server error and fails the user-visible flow
  (a Chat-first question card, a cold-start sequence step, a candidate
  dispatch claim) on the first collision.
- A retired transaction id (Firestore's 270s chain lifetime) comes back as
  `400 The referenced transaction has expired`, which the SDK never retries;
  and when the SDK's own attempt budget is gone the caller sees an anonymous
  error with no indication of which flow broke.

One hot user row could therefore fail a whole contention burst's worth of
Chat-first deliveries or candidate integration claims with nothing
attributable in the logs.

## What changed

All twenty-five entries keep their bodies byte-for-byte and only change how
the transaction is run:

- `run_bounded_lane_transaction` mints a **fresh transaction per outer
  attempt** with `max_attempts=1` (one SDK commit attempt each), so the
  bounded engine — five fresh chains, equal-jitter rungs of 0.15s to 2.4s —
  is the only contention budget. Five bodies, not 5 x 5 same-id replays.
- `Aborted` faults and expired-transaction retirements replay on the fresh
  chain; every body already re-reads its documents inside the transaction
  and keeps its idempotency checks in the same atomic scope, so a replay
  cannot double-write.
- With no wall-clock budget in scope, expired-transaction retirement keeps
  the engine's three-fresh-chain ceiling; `Aborted` contention keeps the
  full five-attempt chain.
- Foreign domain refusals — a continuity-key conflict, an exhausted
  proactive turn budget, an unsupported outcome token — are never retried:
  they pass through on the first attempt exactly as before.
- A caller that scoped a deadline (the ambient
  `transaction_retry_deadline_scope`) now bounds these lanes too: a retry
  starts only while the remaining budget covers the reserve, and a jitter
  sleep never runs past the deadline.

## Observability

Every entry passes a static operation label, so an exhausted chain now lands
on the labeled contention channel instead of surfacing anonymously:

- engine channel (`ERROR:database.firestore_transaction_retry`):
  `firestore_transaction_contention operation=<label> attempt=5/5
  outcome=exhausted`, plus `outcome=retry` warnings per rung and
  `outcome=recovered` after a late success.
- lane channel (the owning module's logger):
  `event=<label>_contention_exhausted operation=<label> reason=...
  retry_after_ms=0`.

The labels are `chat_first_intent_*` (14 intent entries, 1 transient
dead-letter requeue) and `candidate_outbox_*` (10 outbox entries).

## Cost and rollback

The bounded retry trades at most a few seconds of wait on a contended write
that previously failed the user's request instantly (the default chain's
four gaps sum to 1.5-3.0s, capped by the five-attempt budget). A request
that would have failed still cannot loop forever: the chain is capped at
five attempts and foreign refusals never retry. Rollback is a single revert;
no schema, config, or feature-flag changes.

Failure-Class: FC-bare-chat-first-and-candidate-outbox-transactions-fail-on-first-contention
