# Money-safety review: proposal #4 (card declined row on Home)

Branch `mux/2026-10-29-card-declined` (worktree ~/projects/omi-mux-p4-card-declined), merged with origin/main 92bff3c2d5; reviewed through c69f08a0a2.
Verdict: **no charge path.** The app never charges, retries, cancels or changes a subscription. It reads one new
optional field and opens the existing Stripe-hosted billing portal; card details and payment happen only on Stripe's page.

## What the backend does (read-only)
`backend/utils/billing_recovery.py` (new), called once from `_user_subscription_response` (`routers/users.py`):
- Runs only when the stored plan is Basic, the stored row still points at a Stripe subscription (`sub_`, never an
  org-grant `pi_`), its stored period has not ended, and subscription UI is shown (`show_subscription_ui`).
  A sub canceled by choice ends at its period end, so former subscribers cost no Stripe call.
- Stripe calls: `Subscription.retrieve(stored id)` and, only for past_due/unpaid, `Invoice.retrieve(latest_invoice)`.
  No `modify`, `pay`, `cancel`, `create`, checkout or schedule call anywhere in the diff
  (`git diff origin/main...HEAD -- backend | grep -E "\.(modify|pay|cancel|create|delete)\("` = nothing).
- Reports `payment_issue {status, plan}` only if ALL hold: status past_due or unpaid; no `cancel_at_period_end` /
  `cancel_at` (chose to cancel); `collection_method` charge_automatically (not an emailed invoice); `metadata.uid`
  matches when present; price resolves to a paid Omi plan in the catalog; not a trial's first charge
  (`trial_end` set and period start <= trial_end); latest invoice `open`, `attempted`, `amount_remaining > 0`.
- Any Stripe error: no field (fail-open to "no row"), `record_fallback(other, stripe_payment_issue -> none)`, log
  carries the error type only.
- No payment URL in the response; nothing stored. Entitlement unchanged: past_due still projects to Basic
  (`utils/subscription_state_machine.py` untouched); `payment.py` untouched.

## What the app does
- `PaymentIssueRow` (Home, above Today) renders only when `showSubscriptionUI` and `paymentIssue != null`.
- Update -> `UsageProvider.openCustomerPortal()` -> existing `POST /v1/payments/customer-portal` (unchanged; same
  call Plans & Billing uses) -> `PaymentWebViewPage` (Stripe-hosted portal) -> on return `fetchSubscription()`.
- Double tap: `OmiButton` ignores taps while its future runs; `openCustomerPortal` also returns early while a payment
  call is loading. A portal that cannot open shows "Could not open payment settings. Please try again." and the row stays.
- Copy states a fact the backend verified ("Your card was declined"); no price, no discount, no new offer.

## Compatibility (contracts/client-compat)
- Old app + new backend: `payment_issue` is optional and omitted when absent (serializer pop), so every unaffected
  body is byte-identical; affected bodies add one key that released decoders ignore.
  `check_app_client_openapi_compatibility.py --base-ref origin/main`: passed.
- New app + old backend: no field -> no row. Nothing else changes.

## Edge cases checked in tests
backend `tests/unit/test_billing_recovery.py` (35) + `tests/routers/test_users_payment_issue.py` (4): past_due and
unpaid report; active/trialing/canceled/incomplete/incomplete_expired/paused do not; cancel_at_period_end, cancel_at,
send_invoice, other uid, unknown price, no items do not; trial first charge does not, renewal after a converted trial
does; invoice none/paid/draft/not attempted/zero remaining/void/uncollectible do not; non-basic, no sub id, `pi_`,
ended period cost no Stripe call; Stripe failure -> no field + fallback; hidden subscription UI -> no field, no call;
entitlement stays `basic` in the HTTP body.
app `test/pages/home/payment_issue_row_test.dart` (10): row for past_due; legacy plan named; no row for active,
no issue, hidden UI; Update opens the portal and the row leaves after the invoice is paid; portal failure keeps the row. The largest-text regression failed on the original row and passes with the Update action stacked below the copy. The shared OmiButton supports an opt-in pill shape; its 5 existing behavior tests pass.

## Simulator proof (offline Stripe stub, local backend)
Verified on c69f08a0a2: three Update visits created exactly 3 portal sessions and 0 charge or subscription-change calls. Two unpaid returns keep the row. A paid invoice fixture removes it on the first app refresh, and it remains absent after relaunch. A 503 portal error keeps the row and shows an error; retry opens it. Proof: runs/2026-10-29/p4/after/light/{checks.txt,stripe-requests.jsonl}, after/error/{checks.txt,stripe-requests.jsonl}, and result.txt. The app never calls invoice pay or changes the Stripe subscription; paid state is injected only through the offline fixture control.

## Not verified
- Real Stripe portal UI for a past_due customer (the stub serves a placeholder page). Stripe documents that the
  portal lets customers update payment methods and pay open invoices; Smart Retries also retry after a new card.
- A user with more than one Stripe customer: the portal opens for the stored `stripe_customer_id` (existing behavior).
