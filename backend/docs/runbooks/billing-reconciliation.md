# Billing reconciliation (read-only)

This command only reports drift. It has no repair, deploy, flag flip or provider
mutation mode. Live mode was **not run** in the INF sprint. Neither fixtures nor
the command import `database/users` or its create-on-miss subscription readers.

## Snapshot command

Use complete exports shaped as `{"complete": true, "subscriptions": [...]}` and
`{"complete": true, "users": [...]}`. User rows need only `uid`,
`stripe_customer_id`, and `subscription`; do not export content. An incomplete
Stripe export cannot establish reverse drift, so the command rejects it.

```bash
backend/.venv/bin/python backend/scripts/billing_reconcile.py \
  --stripe-snapshot /private/tmp/stripe-subscriptions.json \
  --users-snapshot /private/tmp/user-subscriptions.json \
  --as-of 1791849600 \
  --prometheus-output /private/tmp/billing-reconciliation.prom
```

The default price map comes from the committed recognized-price catalog. An
optional `--price-map /path/prices.json` supplies price-id-to-plan-id bindings for
fixtures or operator-reviewed additional retained prices. Unknown prices are
reported as uncertainty; they cannot prove paid or reverse drift.

## David's operator command (not executed by agents)

Use a restricted Stripe key with **Subscriptions: Read only**, with other
resource permissions disabled. The script uses only Subscription.list with
automatic pagination. A restricted-key prefix alone does not prove its scopes.
Use the read-only GCP identity; the Firestore client uses raw projection reads,
never a helper that provisions or migrates subscription state. No Secret Manager
access or application authentication is involved.

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
read -r -s -p 'Read-only restricted Stripe key: ' STRIPE_RECONCILE_READ_ONLY_KEY
export STRIPE_RECONCILE_READ_ONLY_KEY
backend/.venv/bin/python backend/scripts/billing_reconcile.py \
  --live --project based-hardware --as-of "$(date +%s)" \
  --prometheus-output /private/tmp/billing-reconciliation.prom
unset STRIPE_RECONCILE_READ_ONLY_KEY
```

Do not enable shell tracing. Output is aggregate counts; no UID, customer id,
subscription payload, key or provider exception body is printed. The script does
not load `.env` files. Provider failures produce a nonzero exit and no report.
Snapshot reads are sequential, not a distributed Stripe/Firestore snapshot;
recent mutations can produce transient drift. Repeat the comparison before an
operator decides to repair anything, through a separately authorized workflow.

## Categories and interpretation

- Paid in Stripe but Basic/effectively expired in Firestore; trials have their own
  category. Active status means paid-plan entitlement, not proof of collected cash.
- Paid in Firestore with no Stripe entitlement; wrong plan; wrong price; stale
  period; subscription id mismatch.
- Multiple entitled subscriptions; unknown price; unmapped owner; missing stored
  price identity. Missing `current_price_id` is common because legacy raw webhook
  projection omits it; it is not evidence of a wrong price.

Organization admin one-time grants carry `subscription_id=pi_...`. They are
reported separately as `manual_payment_entitlement`, not reverse subscription
drift; the restricted subscription reader cannot validate PaymentIntents. No
organization grant is changed or reinterpreted.

Categories can overlap. Multiple subscriptions are compared using the stored id
when possible; the command does not pick a winner arbitrarily. JPY amounts and
discount amounts do not participate in entitlement classification. Creator-app
subscriptions are excluded. Free provisioning and read-path reconciliation do
not run. No historical data is rewritten.

## Metrics and proposed alerts (not created)

`omi_billing_reconciliation_drift_total{category}` counts observations per
comparison, and `omi_billing_reconciliation_runs_total` counts completed runs.
All category children start at zero; labels have no account or event ids. The
optional local Prometheus artifact has no network export. CLI counters are
process-scoped: the artifact alone does not feed existing production monitoring.
Choose an authorized collection/cadence before activating any alert.

Propose a drift alert on a nonzero latest comparison for the four critical
categories (`paid_in_stripe_basic_in_firestore`,
`paid_in_firestore_no_stripe_entitlement`, `wrong_plan`, `stale_period`), held for
15 minutes and linked to this runbook. Keep unknown prices and ambiguity visible
as a separate review signal. Do not sum overlapping counts into affected users.
No alert resource or scheduler is created by this PR.

The older `backend/scripts/support/find_stripe_entitlement_mismatches.py` is an
existing targeted support auditor. This command adds fixture-only execution,
aggregate reverse/price/period categories, explicit complete-snapshot checks,
manual-grant uncertainty and restricted-key mode with projected Firestore reads.
