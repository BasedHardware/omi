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

The purchase id is the SHA-256 of the token, never the token. If Stripe listing fails before it
finds a qualifying billable subscription and the local row still grants paid access from a recurring, non-prepaid
Stripe subscription, the backend raises the same alert and notice and also stamps
`stripe_conflict_listing_failed_at` the first time this happens. Confirm the current provider state before acting. A successful
listing without a qualifying Stripe subscription still produces no double-charge alert.

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

## Prepaid code next to Google Play

A reader redeemed a prepaid or bundle code (a $0 Stripe subscription carrying the `prepaid_code_redemption`
marker) while a Google Play purchase landed on the same account. Redemption re-reads Google right before it
creates the subscription, so this needs a narrow race. Nothing is cancelled or refunded automatically: the
prepaid subscription charges nothing, and cancelling it would destroy the included term without returning the
single-use code. The user is not notified. The Stripe webhook and every Play notification or reconcile log:

```
prepaid_code_play_overlap uid=<uid> purchase=<first 12 hex of the purchase document id> code=<promotion code id>
```

```
severity>=ERROR AND (textPayload:"prepaid_code_play_overlap" OR jsonPayload.message:"prepaid_code_play_overlap")
```

Fix it: the reader has an included term AND is paying Google.

1. Play Console: cancel the Google Play subscription for that purchase and refund its latest charge.
2. The prepaid term stands. Leave the Stripe subscription alone.
3. Once Google reports the purchase revoked, resend the prepaid subscription's latest
   `customer.subscription.*` event from the Stripe dashboard so the prepaid plan is stored again.
4. Reply to the user: the Google Play purchase was refunded and their included term runs to its end date.
