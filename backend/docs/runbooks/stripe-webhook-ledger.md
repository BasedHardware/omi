# Stripe delivery ledger (dark)

`BILLING_WEBHOOK_LEDGER_ENABLED` defaults to false. No deployment declaration,
activation, TTL policy, alert or production write was performed in this sprint.
The flag gates all storage access and duplicate suppression. Signature checking
still precedes the ledger; the flag-off adapter executes the original handler.

## Storage and correctness

`stripe_webhook_events/{sha256(event_id)}` contains event id/type, Stripe creation
time, subscription id, processing outcome, attempt, owner token, lease and expiry.
It never retains a payload, UID, customer, signature, key or exception text.
`stripe_webhook_subscription_order/{sha256(subscription_id)}` holds the maximum
successfully acknowledged Stripe creation timestamp. Point reads and transactions need no query
indexes. The storage/client/transaction pattern follows `database/sync_ledger.py`.

A transaction claims a delivery for five minutes. An acknowledged event is a
no-op; an in-flight duplicate gets 503 so Stripe retries. A successful return is
acknowledged only after a durable completion receipt. Unknown-price entitlement
skips return HTTP 200 but complete as `failed`, so the same event id re-enters
the handler on resend after price resolution is restored. Missing owners,
stale-guard preservation and duplicate checkout remain permanent acknowledgments. Exceptions release the
claim as failed; process death permits recovery when the lease expires. Tokens
prevent an old worker completing a newer worker's receipt.

The initial protected set is customer.subscription.created/updated/deleted and
checkout.session.completed. Schedule and creator-app invoice handlers swallow
storage/provider failures today: a returned 200 cannot prove success, so these
remain **unprotected** and get best-effort `legacy_unprotected` observations.
The separate named schedule-retry bug fix extends protection to schedules only
after their transient failures become retryable. Creator-app renewal semantics
remain outside this Omi subscription-state change.

Claim and completion failures return 503. This is required for idempotency:
running without a durable claim could race another worker; acknowledging without
a durable completion could replay all effects. Auxiliary unprotected observation
failures never change the legacy response. Each ledger wait is bounded to two
seconds; a running SDK RPC can still finish in its worker after HTTP timeout.
No handler runs without a confirmed claim. Completion after a timeout is safe to
recognize on retry, and missing completion stays retryable.

This is **not exactly-once execution** across Firestore, Stripe, Redis, unlocks
and notifications. A crash after effects but before completion can replay those
effects. Receipt tokens fence ledger completion, not legacy user writes; a
worker surviving beyond its lease can overlap recovery. Different event ids
still race. Those require a later fenced/atomic entitlement write design and
Firestore-emulator contention acceptance before claiming stronger guarantees.

Out-of-order events are detected on claim and completion and counted. They are
**not discarded or reordered**: changing the legacy last-delivery-wins outcome
would be a separate named behavior fix. Equal-second timestamps do not establish
order; Stripe event ids are not a sortable clock. Read-path healing and manual
subscription writes are not governed by this ledger.

## Retention and write budget

Receipts and watermarks carry `expires_at` at 90 days. The deduplication boundary
checks expiry itself, so delayed TTL deletion does not define correctness. An
operator must separately authorize TTL policies on both collections' expires_at
fields; **no policy is created here**, so physical storage is not yet bounded.
Events older than retention can execute again; review retention before activation.

Estimate (not measured live): 3,000 monthly paid subscriptions imply about 100
renewals/day. Budget conservatively for four first deliveries per renewal plus
churn/checkouts/changes: approximately 400 first deliveries/day before extra
mutations. A protected subscription event uses three ledger writes (claim receipt
then completion receipt and watermark), normally four point reads; duplicates cost one
read and zero writes. Events without a subscription use two writes. Unprotected
observations use one write/delivery. At 400 all-protected deliveries: about 1,200
additional writes/day, up to about 2,000 including a conservative two future TTL
deletes/event; failures/retries add attempts. Existing entitlement/unlock/cache
writes are excluded. Watermarks generally survive monthly renewals, so actual
TTL deletes are lower than that upper estimate. Rough steady receipt population:
36,000 at 90 days plus subscription watermarks. No monetary cost or measured
webhook volume is claimed; confirm actual deliveries before enabling.

## Observability and proposed alert (not created)

`omi_billing_webhook_ledger_total{outcome}` has a closed, zero-initialized label
set: claimed, duplicate, busy, acknowledged, out_of_order, claim_error,
finish_error, handler_error, retryable_skip, unprotected, observe_error. No subscriber or event
label exists. Existing delivery lifecycle/product metrics remain at their
original handler positions; completed duplicates do not re-emit them.

Propose a five-minute alert when
`sum(increase(omi_billing_webhook_ledger_total{outcome=~"claim_error|finish_error"}[10m])) > 0`,
with this runbook as the action link. Review out_of_order and sustained busy
separately; neither authorizes automatic account repair. Drift categories and a
separate proposed drift alert are in [billing reconciliation](billing-reconciliation.md).
No monitoring resources are created.
