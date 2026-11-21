# Pocket-match referral campaign (dormant)

`omi_pocket_match_v1` implements the authenticated 2026-11-04 Pocket UI amounts:
friend gets 10% off hardware; first 2 distinct purchasers unlock 2 Pro months;
next 3 unlock 3 more; maximum 5 distinct friends and 5 total months.

These **Omi choices are not Pocket facts**: existing accounts may participate;
orders must be created after authenticated attribution and paid after checkout
binding; first attribution wins; a buyer qualifies once per version; any line-item
refund terminally disqualifies that order before claim; unclaimed slots are
released, claimed slots remain consumed; already claimed time is not clawed back.
Each milestone consumes only its required two or three additional purchasers.
`qualified_purchases` remains the truthful current unrefunded count, while
`milestone_progress` retains consumed earned credit plus valid unclaimed buyers.
`earned_months=max(claimed_months, threshold(milestone_progress))` drives both
snapshot and claim. A consumed refund therefore cannot strand the next milestone.
Manual claim starts calendar months, free of a concurrent commercial paid period.
Paid users retain their earned claim until paid access ends and they claim again.
Claim performs a strict read-only Stripe inspection of known recurring billing
identity before its transaction and fences the observed commercial row. A billing
outage or changed identity consumes no reward. The canonical billing writer
serializes with claim and requeues any newly billed overlap beyond the paid period,
including a renewal delivered after the original grant expired. A paid-coverage
interval union prevents duplicate or overlapping renewal delivery extending time twice.
Initial duration uses calendar months; requeued overlap preserves those seconds.
Commercial checkout eligibility uses raw period-valid billing plus its existing
Stripe duplicate/pending-cancellation checks, separately from promotional access.
The policy version configures no link, attribution, or unclaimed-reward expiry;
this is an Omi implementation choice, not evidence that Pocket offers no expiry.
Active grants expire at their stored calendar-month boundary on every admission.
There is no Stripe subscription update, credit, billing-period extension, invented
price, live code creation, payment call, or external reward outbox marked delivered.

## Contracts

- GET `/v2/users/me/referral/campaign`: own snapshot only, authenticated UID.
- POST `/v2/users/me/referral/campaign/claim`: no UID/body; optional `{}` ignored;
  atomically claims all currently unlocked unclaimed months, repeats are safe.
- Both return `{campaign_id, enabled, referral_url, qualified_purchases,
  claimed_months, claimable_months, milestone_progress, earned_months, reward_status, reason}`. Totals come from
  committed ledger documents. Disabled handlers perform no campaign IO or durable writes.
  Readonly authentication still verifies Firebase UID and enforces deletion, cutover
  and BYOK security reads; it never registers platforms/devices or recovers content.
- POST `/v2/users/me/referral/campaign/attribution` `{code}`: authenticated buyer;
  returns `{campaign_id, state:'attributed', checkout_url, discount_percent:10}`
  only after a trusted provider receipt is durably bound. No body UID/email/order.
- `ref2` signs campaign, immutable policy digest, environment, and referrer UID.
  GET `/r/ref2...` opens `https://app.omi.me/referral/hardware?code=...&environment=...`.
  `ref1`, legacy signup/auth ownership, 15-minute legacy eligibility, and existing
  `/v1/users/me/referral*` behavior remain unchanged.
- Attribution errors use `{detail:string}`: invalid code404; self/conflicting
  attribution or unavailable account409; campaign disabled, activation prerequisite
  or provider unavailable503. No fallback shopping URL on failure.
- POST `/v2/referrals/shopify/webhook` verifies raw-body HMAC, exact merchant,
  environment/test bit, paid status, positive USD total, approved hardware variant,
  actual discount application/allocation, finite positive eligible hardware NET value
  after all allocations (USD cents/quantity/currency consistency), then server-stored checkout/customer
  binding. It deduplicates by merchant+order and by UID+Shopify customer, independently
  of webhook delivery IDs. `refunds/create` persists an order tombstone even if
  payment has not arrived. It never accepts a client payment assertion.

## Activation prerequisites (NOT performed or proven)

All remain default off. Setting `OMI_REFERRAL_CAMPAIGN_ENABLED=true` alone cannot
issue a checkout/link or grant: a complete `TrustedCheckoutAdapter` is required.
No campaign configuration, code, webhook registration, flag, price, grant or live
order was written by this implementation. Production checkout is **UNVERIFIED**.

Before any future separately authorized activation:

1. Deploy and audit an Omi-owned trusted checkout service. Configure its HTTPS
   endpoint `OMI_REFERRAL_CHECKOUT_ENDPOINT` and shared secret
   `OMI_REFERRAL_CHECKOUT_SECRET` (at least32 characters). It must independently
   establish Firebase UID -> authenticated Shopify customer ownership, then create
   an idempotent checkout for that customer. Cart attributes, email matching, or
   the referrer token alone cannot establish buyer ownership. Persist/reconcile
   the idempotency key across provider crashes; retries return the same receipt.
2. Approve an existing/referral-specific **hardware-only** 10% code. No default
   marketing code is reused. Configure `OMI_REFERRAL_DISCOUNT_CODE`, exact comma
   separated numeric `OMI_REFERRAL_HARDWARE_VARIANTS`, and
   `OMI_REFERRAL_SHOPIFY_SHOP=88f4ed-c3.myshopify.com`. The observed Silver variant
   is53310207000868; runtime catalog is not changed. Verify contextual checkout
   prices and discount combinations including the current automatic offer before
   setting `OMI_REFERRAL_DISCOUNT_REVIEWED=true`. Admin list price is not proof.
3. Configure a matching Shopify app secret `OMI_REFERRAL_SHOPIFY_WEBHOOK_SECRET`
   (at least32 characters), register orders/paid and refunds/create deliveries to
   the verified endpoint, and exercise paid/refund/replay under the actual shop.
   Headers are accepted only for that exact canonical merchant, never an alias.
4. Customer user rows and account-deletion markers must be in the same Firestore
   project/database for atomic admission. The default database adapter refuses a
   split topology; a reviewed authority migration/bridge is needed otherwise.
5. Verify grant admission in all deployment planes and review ledger UID retention
   under deletion/privacy policy before enabling. Minimal replay tombstones are
   retained independently of deleted user rows; they never recreate user accounts.
   Same-person multiple unrelated Firebase/Shopify identities remain an abuse gap.

Trusted service protocol: request canonical compact JSON includes campaign,
environment, authenticated UID, attribution ID, approved variant IDs/code and10%;
header `Idempotency-Key` is the attribution ID, `X-Omi-Signature` is Base64
HMAC-SHA256 over exact request bytes. Response signature covers
`attribution_id + '.' + raw_response_bytes` with the same key. Response must echo
UID/attribution/environment/shop and return actual `customer_id`, `checkout_token`,
`variant_id`, `discount_code`, `discount_percent:10`, `hardware_only:true`,
`combination_verified:true`, `checkout_url`. HTTPS checkout URL hosts are exactly
`www.omi.me` and `88f4ed-c3.myshopify.com`, no credentials/nondefault ports, and
path starts `/checkouts/` or `/cart/`. Redirected provider responses are rejected.
This transport is implemented and unit-testable; the trusted service itself is a
separate deployment prerequisite, not a fake working Shopify integration.

Shopify verification source:
https://shopify.dev/docs/apps/build/webhooks/verify-deliveries

## Authority and tests

Independent `referral_*` documents pin policy, attribution, checkout receipt,
order/refund, purchaser dedupe, bounded5-slot state and deterministic milestone
award. Firestore transactions read all documents before writes, including account
and deletion fences. Policy mismatch fails; transaction exhaustion never grants
through a nontransactional fallback. A committed local award and separate user
`referral_campaign_grant` are written together. Commercial subscription stays raw.
`get_user_valid_subscription` composes active access; shared request projection
includes the grant; raw usage budget, fair-use and sync admission compose it too.
Funded processing, managed compute, messaging and screen-vector authority use the
same valid-subscription resolver. Billing/COGS raw reads keep commercial identity.

Unit suites: `test_referral_campaign.py`, `test_referral_campaign_routes.py`,
`test_referral_campaign_entitlements.py`, existing `test_referrals.py`.
Real transaction contention: `tests/integration/test_referral_campaign_emulator.py`.
Run integration only against a guarded loopback emulator. It covers final-slot
races, concurrent repeated claims, competing referrers, refund/payment ordering,
claim/refund ordering, a concurrent commercial subscription write, old accounts,
pre-attribution purchases, self-referral, and active-grant expiry.

The local fixture adapter never calls Shopify. Golden states are generated by
`tests.unit.fixtures.referral_campaign.golden_states`, through production
attribution/binding/HMAC/qualification/claim/snapshot functions. Fixture code and
checkout URLs are explicitly local fixtures, never issued to production users.

## Interval clock, bounds and dormant prototype migration

Clock version2 commits immutable promotional budget seconds when each of at most
two milestones is claimed. It stores normalized unions of scheduled availability
and known paid coverage. Consumption is elapsed availability minus paid coverage;
gaps after an expired schedule do not consume the obligation. A newly discovered
paid interval restores the unconsumed budget from delivery time, skipping known
paid intervals. Earlier A arriving after later B is not suppressed by B's end.
Identical or subset coverage is a pure replay and never restarts an expired grant.
The commercial snapshot remains last-delivery-wins under its existing contract;
promotional accounting does not rewrite or infer Stripe billing periods.

Both normalized unions are limited to256 disjoint intervals. Adjacent/overlapping
ranges coalesce; ordinary recurring renewals occupy one range. Merge is
O(n log n), consumption/scheduling are linear in normalized ranges, and state
remains bounded well below Firestore's document limit. Overflow fails the entire
commercial/grant transaction without truncating history, consuming an award or
acknowledging successful reconciliation; the durable billing event must be retried
or explicitly reconciled before activation. Capacity and unambiguous history are
operational activation prerequisites, not permission to discard reward time.

This campaign has remained default off and has no deployed legacy grant records.
Unadjusted local initial grants have an unambiguous start/end budget and can be
read as such. An obsolete local prototype containing paid_coverage_end cannot
reconstruct skipped coverage, so it fails explicitly for reconciliation rather
than guessing a migration. Reset/reconcile such synthetic emulator fixtures via
their owner; no production migration, grant rewrite, or activation was performed.
