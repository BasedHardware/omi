# Testing subscription currency changes

Moved out of the public docs (docs.omi.me); this is contributor testing
guidance that churns with the billing integration.

The first-party `GET /v1/payments/available-plans` response includes an optional
formatted `billing_total` and a `currency` for each offer. Amounts remain in
Stripe minor units; JPY uses whole yen. Currency-aware clients send
`X-Omi-Billing-Currency: 1` and display the returned total before submitting the
exact selected price to `POST /v1/payments/upgrade-subscription`. Refresh plans
if a stale target returns HTTP 409. A payment decline returns HTTP 402.

For provider integration testing, use a separate Stripe sandbox with synthetic
customers and a test-mode key. The opt-in billing integration test documents its
command and cleans up its disposable subscriptions and customers. Never run a
plan-change test against a customer account or a live-mode key.
