# Money-safety review: proposal #4, review round 1

Reviewed source: 4e7904d217f77309af5e37dec83522a2581b8838.

Verdict: **no charge path**. The recovery row only opens the existing customer billing portal. This revision excludes failed plan-change invoices and makes the copy accurate for a user already on Free. No live state was changed.

## Eligibility and Stripe reads

- Only iOS/Android with visible billing UI can receive `payment_issue`.
- The stored Basic row must reference the same Stripe subscription as the snapshot already retrieved by `reconcile_basic_plan_with_stripe`. No recovery Subscription.retrieve call remains. Missing/failed/foreign snapshots produce no row and no retry.
- Stripe status must be past_due/unpaid, with no chosen cancellation, automatic collection, a matching uid when metadata contains one, and a paid Omi catalog price. A trial's first charge stays excluded.
- The latest invoice must be open, attempted, have money remaining, and have `billing_reason == subscription_cycle`. Failed upgrades (`subscription_update`), new subscriptions, manual invoices and missing reasons are excluded.
- Recovery adds only Invoice.retrieve for past_due/unpaid mobile readers. Canceled former subscribers have no extra recovery call. Reconciliation's existing entitlement repair and fallback customer search are unchanged.
- Stripe invoice failure suppresses the row and records the existing fallback without logging provider payloads.

## Portal and copy

- Home says “Your card was declined” / “Update it to get Omi Pro back”. Legacy renewals name their actual plan. Every locale was updated through scripts/l10n.py.
- Update calls UsageProvider.openCustomerPortal -> existing POST /v1/payments/customer-portal -> native PaymentWebViewPage. Return refreshes the subscription. There is no new pay, retry, cancel, subscription change, Checkout, price, coupon or schedule write.
- OmiButton blocks a second tap while the portal request is pending. A failed request shows existing feedback and retains the row.
- Updating a card or paying on Stripe's page can settle an existing renewal under the user's existing subscription. No payment action is performed by this new app/backend path.
- Three typed events use Subscription wire names to match the `subscri` ingestion keep rule: Payment Issue Shown, Update Tapped and Portal Opened. Shown deduplicates unchanged refreshes; Portal Opened requires a successfully finished web-page load and is not a payment outcome. The events contain no billing identifiers, portal URLs, card data or invoice amounts.

## Regression evidence

- Backend decision: 44 passed. subscription_update/subscription_create/manual/missing billing-reason cases failed before the fix and pass after it.
- Real users router + real reconciliation: 19 passed, with Stripe call counting across iOS, Android, macOS, Windows, web and missing platform. The 12 duplicate/platform regressions failed before the fix and now pass. Canceled readers make exactly the one existing Subscription.retrieve; only mobile past_due reads the invoice. Hidden billing UI adds no invoice call.
- Related backend: 515 passed (plans 69, lapsed-paid heal 6, users router 327, BYOK security 43, subscription caches 70).
- Home row: 13 passed, covering the accurate copy, largest text, legacy plan, shown deduplication, pending double tap, loaded-portal timing, paid refresh and failure.
- Native web view: 3 passed; a successful page reports loaded once, about:blank and resource/HTTP error pages do not.
- Native iPhone simulator proof on the committed source: failed-upgrade invoice is hidden; three portal visits load successfully; two unpaid returns keep the row; paid fixture plus app refresh restores Pro and removes it, including after relaunch. Light, dark, largest text and German/Japanese/Arabic copy were viewed. The unmodified 20.48-second MP4 ends with recovery absent.
- All non-GET stub requests were audited: 7 offline fixture controls and 3 existing billing-portal session POSTs during the full light path; zero charge or subscription-change calls. Dark and largest-text runs created no portal sessions. Evidence: p4/round1/after/*/{checks.txt,stripe-requests.jsonl}, money-requests.json and result.txt. No real card entry or payment was attempted.

## Unverified and outside this proposal

- Real Stripe portal/card entry, payment retries and webhook timing; physical iPhone and Android runtime; actual recovered churn.
- The independent review found an existing old-subscription retry risk across multiple subscriptions. This revision excludes failed upgrade invoices from the row; it does not change the existing checkout transition, retry policy or entitlement projection.
- Draft only. No merge, release, rollout, feature flag, live Stripe or Firestore mutation.
