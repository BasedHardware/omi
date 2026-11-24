# Play Billing: double charge (Stripe and Google Play)

A user can be billed twice when a Google Play subscription on hold or paused recovers after they already
bought Omi Pro through Stripe. New Stripe checkout is refused while any Play purchase the user owns can still
charge or recover, so this should only come from older data or a race.

The backend never cancels or refunds either side on its own. When a Play purchase is live next to a paid
recurring Stripe subscription, `utils/play_billing.py` (`_record_stripe_conflict`) keeps both, logs the line
below, stamps `stripe_conflict_at` (first time seen, never overwritten) on the `play_subscription_purchases`
document, and sends the user one `play_billing_double_billing` notification (`stripe_conflict_notified_at`
is set only after it was sent; a failed send is retried on the next observation). A person fixes it.

## Alert and log filter

Every time the conflict is observed (each Play notification and each reconcile, at least daily) this ERROR
line is logged. Its text is stable; the Cloud Monitoring alert matches it:

```
play_billing_double_charge uid=<uid> purchase=<first 12 hex of the purchase document id> state=<Google state>
```

```
severity>=ERROR AND (textPayload:"play_billing_double_charge" OR jsonPayload.message:"play_billing_double_charge")
```

The purchase id is the SHA-256 of the token, never the token. The line is only logged when Stripe itself lists
a recurring `sub_` subscription for the user that is `active` or `trialing`. A one-time `pi_` grant, a stale
local row, an ended or an `incomplete` Stripe subscription logs only
`play_billing Stripe overlap not confirmed as a paid subscription` at WARNING and needs no action.

## Confirm it is real

1. Stripe: the customer has a recurring subscription (`sub_...`) with status `active` or `trialing` and a paid
   latest invoice (or a trial). Not a one-time `pi_` payment, not `incomplete`, not `canceled`.
2. Firestore: the `play_subscription_purchases` document for the uid whose id starts with `purchase=` has
   `stripe_conflict_at`. In Play Console, the order for that purchase is active and was charged.
3. If either side is not really paying, stop: it is not a double charge.

## Fix it

1. Pick the agreement to keep. Ask the user if unclear. Default: keep the one with the later purchase date
   (the one they chose most recently).
2. Keeping Stripe: in Play Console, cancel the Play subscription and refund its latest charge.
3. Keeping Play: in Stripe, cancel the Stripe subscription now and refund its latest invoice. The Stripe
   webhook removes the Stripe row; the next Play notification or reconcile grants Play.
4. Reply to the user with what was cancelled and refunded.
