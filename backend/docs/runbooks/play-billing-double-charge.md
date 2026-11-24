# Play Billing: double charge (Stripe and Google Play)

A user can pay twice when a Google Play subscription on hold or paused recovers after they already bought Omi Pro
through Stripe. Since this guard, new Stripe checkout is refused while a Play purchase can still recover, so this
should only come from older data or a race.

When it happens, `utils/play_billing.py` (`_stop_play_for_stripe_conflict`) keeps the Stripe subscription the user
has access through, developer-cancels the Play subscription so Google never charges again, records
`stripe_conflict_at` (and `stripe_conflict_cancelled_at`) on the `play_subscription_purchases` document, and sends the
user a `play_billing_double_billing` notification. It does not refund the Play charge. That is manual.

## Find them

The line is logged at ERROR once per purchase, and again on each retry of a failed cancel. The backend logs in
text mode, so Cloud Logging stores it in `textPayload`:

```
severity>=ERROR AND (textPayload:"play_billing_double_charge" OR jsonPayload.message:"play_billing_double_charge")
```

Each line has `uid=`, `purchase=` (the first 12 hex characters of the purchase document id, the SHA-256 of the
token, never the token), `state=` and `action=` (`cancel_play`, or `already_stopped` when auto-renew was already off).
A failed cancel logs `play_billing conflict cancel failed` at WARNING; Pub/Sub and the reconcile job retry it.

## What to do

1. Find the purchase: the `play_subscription_purchases` document for `uid` whose id starts with `purchase=` and has
   `stripe_conflict_at`.
2. In Play Console, open the order for that purchase and refund the latest Play charge (refund only; access already
   comes from Stripe). The subscription is already cancelled, so Google does not charge again.
3. Never cancel or refund the user's Stripe subscription to fix this.
