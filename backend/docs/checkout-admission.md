# Recurring checkout admission

The shared `POST /v1/payments/checkout-session` route owns admission to fresh
recurring checkout for all clients. Storefront rendering stays read-only; it is
not a prerequisite for safe checkout. Existing paid-plan changes use
`POST /v1/payments/upgrade-subscription`, not a second subscription.

## Authority and flow

The route validates the target price, existing eligibility and any promotion
code, then calls `_try_reactivate_subscription` before creating a Checkout
session. That boundary reads the raw stored subscription ID, not only the
effective entitlement projection: an expired paid record can project to Basic
and lose its Stripe ID. A missing root customer ID must not bypass verification
of a stored recurring-subscription ID.

| Verified state | Checkout decision |
| --- | --- |
| No stored ID and no existing customer-based recovery | Existing new-buyer path |
| One-time organization grant (`pi_...`) | Existing path; never retrieve it as a Subscription |
| `canceled` or `incomplete_expired` | Fresh checkout allowed |
| Retrieve returns `resource_missing` with HTTP 404 | Fresh checkout allowed |
| Active, cancel-scheduled, same plan and interval | Reactivate the existing subscription; no new session |
| Any other nonterminal state, including unknown future statuses | HTTP 409; manage the existing subscription |
| Unavailable/malformed Stripe state or failed reactivation | HTTP 503; retry, never fresh checkout |

The definitive-absence exception applies only to retrieval. A missing-resource
error during reactivation cannot fall through. Blocked requests do not rewrite
entitlements or customer IDs. Logs report failure type, not provider bodies.
Fresh-checkout success and reactivation response shapes remain unchanged.

## Scope and verification checklist

Refs #21869. This protects checkout-first stale-record requests; it does not
repair an affected account, prove a rollout, deduplicate already-created
subscriptions, or serialize concurrent first-time purchases. An account with
neither a stored subscription ID nor a customer ID cannot be resolved by this
boundary. The separate subscription-read reconciliation remains responsible
for entitlement healing.

- [x] Extend the existing shared checkout/reactivation boundary, not storefront reads.
- [x] Exercise the real HTTP route, eligibility and Checkout builder with fake
  persistence and Stripe SDK objects; assert no new billing side effects on refusal.
- [x] Cover legacy paid/Basic records, missing customer ID, new accounts, referral
  access, one-time grants, terminal subscriptions, recovery and reactivation errors.
- [x] Validate on current main alone (no bundled prerequisite PRs): `routers/payment.py`
  passes the pinned type check, and the checkout-first HTTP regressions plus the
  20-file billing selection pass under `test.sh`; local fixture-backed curl checks
  preserve all four admission outcomes.
- [x] Clients tell the two 409s apart: checkout's 409 (existing subscription) shows
  that reason on Flutter, macOS, web and Windows; only the upgrade route's 409 means
  a pending cancellation ("Resubscribe first").
- [x] Flutter selects the localized existing-subscription message by checkout
  status 409, never by the server's English detail. All current ARBs and generated
  delegates are updated through `app/scripts/l10n.py`; both purchase surfaces
  have English, German and Arabic regression coverage.
- [ ] Exercise checkout/refusal, same-plan reactivation and manage-existing
  recovery end-to-end with an approved Stripe sandbox and installed client.
- [ ] Final reviewed commit passes required checks; remain draft until this and
  the preceding runtime gate are complete.
- [ ] Review and merge the separate protection PR after checks pass.
- [ ] Separately authorize deployment and verify the serving backend revision.
- [ ] Verify the affected customer's Stripe/entitlement state before closing #21869.

Regression contract: `backend/tests/unit/test_checkout_first_subscription.py`.
Read-only drift reporting: [billing reconciliation](runbooks/billing-reconciliation.md).
