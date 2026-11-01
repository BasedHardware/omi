# Product telemetry scorecard

The read-only `scripts/product-telemetry/scorecard.py` command turns normalized
JSONL events into a versioned scorecard, an experiment comparison, or an agent
evidence packet. It is designed for scheduled analysis jobs and synthetic
fixtures; it does not mutate PostHog, Firestore, feature flags, or production
traffic.

```bash
python3 scripts/product-telemetry/scorecard.py scorecard \
  --input contracts/product-telemetry/fixtures/regression.jsonl \
  --as-of 2026-09-22T00:00:00Z

python3 scripts/product-telemetry/scorecard.py experiment \
  --input contracts/product-telemetry/fixtures/experiment.jsonl \
  --experiment-id ui-v2 --as-of 2026-09-03T00:00:00Z

python3 scripts/product-telemetry/scorecard.py workflow \
  --input contracts/product-telemetry/fixtures/regression.jsonl \
  --baseline-build 1.0.0 --candidate-build 1.1.0 --output packet.json
```

The metric contract lives in
[`contracts/product-telemetry/metric-definitions.json`](../../contracts/product-telemetry/metric-definitions.json).
Event time drives cohorts and maturity. Duplicate event IDs are counted once
within the selected namespace/environment/build isolation boundary. Late
arrival counts are reported from `ingested_at`; they do not rewrite event-time
windows. Missing event time, user, outcome, or denominator produces
`insufficient_evidence`, never a confident zero.

The experiment reader accepts both the shared `experiment_assigned` /
`experiment_exposed` shape and the existing backend `Experiment Enrolled` /
`Experiment Exposed` names. Allocation diagnostics report assigned and exposed
counts separately. The analysis is exposure-conditioned: its denominator is
the mature, unambiguous `experiment_exposed` user set, with actual exposure
variant and exposure time required. Assignment conflicts, multi-variant users,
QA overrides, unexposed assignments, outcomes before exposure, and outcomes
outside the conversion window are excluded. Missing mature outcomes remain in
the denominator and produce `insufficient_evidence` plus an explicit success
rate bound. Allocation imbalance is a descriptive heuristic, not a statistical
SRM test. Product Journey Outcome/Product Value attribution additionally
requires `experiment_context_verified=true` and a registered `$feature/<key>`
variant.

PostHog can be used only with an explicit checked-in HogQL file and
`POSTHOG_HOST`, `POSTHOG_PROJECT_ID`, and `POSTHOG_PERSONAL_API_KEY` in the
environment, plus explicit `--since` and `--until` UTC bounds. The CLI renders
only those validated date placeholders and requires every query to use the
`LIMIT 50001` sentinel. It refuses redirects, non-HTTPS origins, embedded
credentials, nonnumeric project IDs, partial responses, `hasMore=true`, an
ambiguous missing completeness marker, or a response at the safety cap. Narrow
the time window or provide a complete local export when a response is rejected;
it never silently scores the first page. The adapters are in
[`contracts/product-telemetry/posthog/`](../../contracts/product-telemetry/posthog/).

Paid churn requires an owner-authorized start-of-window billing export. Convert
a local JSON/JSONL/CSV export with the read-only importer:

```bash
python3 scripts/product-telemetry/billing_snapshot.py \
  --input paid-users.csv --snapshot-id start-2026-09-01 \
  --snapshot-at 2026-09-01T00:00:00Z --output billing-snapshot.jsonl
```

The resulting `Billing Paid Population Snapshot` rows provide the churn
denominator. A snapshot has an independent billing scope by default. To join
it to a mobile export, the operator must declare the verified client cohort
values explicitly:

```bash
python3 scripts/product-telemetry/billing_snapshot.py \
  --input paid-users.csv --snapshot-id start-2026-09-01 \
  --snapshot-at 2026-09-01T00:00:00Z \
  --namespace com.friend.ios --environment production --app-build 1.0.0 \
  --output billing-snapshot.jsonl
cat posthog-billing.jsonl billing-snapshot.jsonl > billing-scorecard.jsonl
python3 scripts/product-telemetry/scorecard.py scorecard \
  --input billing-scorecard.jsonl --as-of 2026-09-30T00:00:00Z
```

For a separate billing run, use the bounded
[`billing-churn.hogql`](../../contracts/product-telemetry/posthog/billing-churn.hogql)
adapter and combine its export with the snapshot locally. Do not add an
unscoped snapshot to a mobile journey export: the scorecard returns
`mixed_cohort_scope` rather than inferring mobile affiliation from activity
during the churn window. `Billing Subscription Started` and `Billing
Subscription Churned` are emitted only after the signed Stripe webhook
resolves an existing Omi owner; a scheduled cancellation lifecycle event is
not churn, while an ended subscription remains churn even if Stripe's ended
reason is `cancellation_requested`. The lifecycle measurement is paid-plan **entitlement**, including trials under
the existing product authority, rather than cash/revenue. A payment-status update
that removes that entitlement is churn at that transition; a later deletion does
not count it again. Replacement-subscription reconciliation is excluded. No live
billing call is made by the importer or scorecard.

The scorecard also reports explicit telemetry-health, first-frame render, and
recording audio/transcript observation metrics. These describe observation
coverage only; no battery, native-hang, network-readiness, or usefulness claim
is inferred from them.

The workflow emits `product-evidence-packet.v1` with baseline/candidate
metrics, completeness, app builds, prompt versions, trace pointers, a proposed
investigation action, and a rollback condition. It never rolls out a change.
The seeded fixture demonstrates a candidate journey reliability regression and
the experiment fixture demonstrates an allocation imbalance while retaining
the exposure denominator. `experiment-corrected.jsonl` demonstrates a
corrected candidate compared with a holdout; pass `--experiment-id` to
`workflow` to attach that comparison to the evidence packet.

Billing lifecycle events are a best-effort projection, not a durable billing ledger.
They run immediately after the entitlement write and before cache followups, but
a crash between that write and emission can still omit a transition. Reconcile
against authorized billing snapshots/exports before using churn for automated
rollout decisions; missing events never prove retained payment.
