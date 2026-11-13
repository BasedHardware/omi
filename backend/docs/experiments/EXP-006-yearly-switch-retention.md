# EXP-006 — mobile yearly-switch retention

Status: source proposal, dark pending David's exact render/copy approval and an
authorized rollout. Neither merging nor an event establishes live lift. This
implements SCA-1808's corrected UID-first scope; no payer ledger is authorized.

## Assignment and admission

Use `utils.experiments.enroll`, experiment id
`EXP-006-yearly-switch-retention`, its existing deterministic UID assignment and
50/50 treatment/control split. Do not introduce another identity key or salt.
Both arms are enrolled through the same first-eligible-request path. The
existing assignment document's atomic `create` is also the admission claim.
Only `newly_enrolled && is_treatment` permits a placement. An existing UID,
including an unexposed treatment or control UID, can never claim again.

The first eligible placement wins; its `source` and frozen eligibility snapshot
identify cancel versus engaged. A lost HTTP response consumes the opportunity;
retrying must not redeliver. This is at-most-once admission, not guaranteed
exactly-once rendering. Intent-to-treat includes those unobserved exposures.
The two placements do not overlap for the same UID. The settings switch remains
available to both arms, so the contrast is the incremental placements, not all
yearly switching versus no yearly switching.

Existing yearly-switch eligibility is authoritative: paid, renewing, supported
monthly plan/currency, without trial, discount, scheduled change/cancellation,
or other existing refusals. No prices, plans, ceilings or billing mutation are
added. The original invoice preview and price/amount/proration-pinned
`upgrade-subscription(switch_now=true)` apply the switch.

Engagement predicate v1: **at least eight completed, non-discarded, visible saved
conversations created in the preceding 14 days**, counted with the existing
`get_conversations_count(statuses=['completed'], start_date=now-14d, end_date=now)`.
Its existing visibility exclusions apply. This is eight captures, **not eight
distinct active days**. No empty in-progress session is counted. The count,
window, predicate version and placement are frozen at enrollment. Cancellation
does not require engagement. Engagement is checked on each new Home presentation;
a UID that qualifies after its first presentation can qualify on its next visit.

## Flags and privacy

`YEARLY_SWITCH_RETENTION_ENABLED` defaults on; only the literal `false`
(case/whitespace normalized) disables it. Admission additionally requires a
nonempty `YEARLY_SWITCH_RETENTION_APPROVAL_REF` and
`YEARLY_SWITCH_RETENTION_ROLLOUT_AUTHORIZED=true`. Both are absent by default.
An authorized operator must first record David's exact approval on SCA-1808.
Do not activate from this PR. Setting the kill switch false stops new admissions;
mounted clients refresh on resume/every 30 seconds and before opening/confirming
the new switch sheet. Config failures hide the optional placement. Existing
cancellation and settings switch continue. Stored controls survive toggles.

The existing experiment assignment is the only new persisted per-UID record.
`purge_user_subtree` explicitly deletes this experiment's assignment, including
root-missing wipe retries; failures propagate. Admission checks the durable
deletion status before and after enrollment, erasing an in-flight assignment
if deletion started. No other experiment's erasure policy changes. No content,
audio, customer ID, device ID or raw UID is added to metric properties. Existing
analytics consent/identity/erasure transport remains authoritative.

The two legacy retention-offer wire names are registered without renaming:
Shown means offer loaded into the cancellation step; Accepted means discount
accept intent, not billing success. The new `Yearly Retention Observation`
contains only closed placement/action/variant and numeric experiment version.
Shown is a post-frame observation, not attention or guaranteed ingestion.
Succeeded uses the existing switch confirmation/readback semantics; final
take-up still requires authorized billing association. Presence SQL is an
executable registry consumer, not an outcome estimator or deployed dashboard.

## Measurement and limits

Analyze the enrolled UID roster by randomized arm, including controls without
events; do not build the denominator from Shown/Accepted/Succeeded. Stratify
first placement from the frozen snapshot; aggregate both arms consistently.
Estimate yearly take-up, effective paid ends by day 30 and day 60, and revenue
per enrolled subscriber, with uncertainty and cohort maturity. Cancellation
scheduled is not a paid end. Annual renewal retention is not observed in a
60-day window. Annual upfront cash is not recurring-revenue lift.

UID randomization permits linked-account/duplicate-customer contamination.
Do not call this payer-clustered. Existing billing associations may be missing
or ambiguous: mark those unknown/excluded and report protected coverage.
Overall Stripe totals and list-price MRR cannot establish arm-specific effect.
Do not infer identity from email/device, add an exporter/store, or access
production credentials to fill a gap. The bounded next measurement step is an
authorized verifier assessing which existing associations actually cover the
enrolled arms and returning the missing metric/coverage if insufficient.

The read-only acceptance gate is:

```sh
python3 backend/scripts/verify_yearly_switch_retention.py --read-only --require-live --require-mature-holdout
```

Live mode always exits 2/WAITING: **authenticated receipt provenance is not
available in this implementation**. `YEARLY_SWITCH_RETENTION_RECEIPT` (a local
protected receipt file) or `--receipt PATH` supplies untrusted assertions only.
The literal authority name, evidence URLs, an approval name, synthetic/live
labels or a caller-supplied signature cannot establish trust. Even a complete,
fresh, mature schema-valid receipt remains WAITING with all metrics withheld.
The command never queries a service or writes a file.

Bounded measurement gap: an authorized m5 verifier/owner must identify an existing
trusted mechanism to authenticate the receipt producer and independently resolve
its exact serving release, David approval, operational checks and protected
aggregate evidence. An owner-authorized adapter and regression tests at that
boundary are required before this entry point can ever return LIVE/exit 0. No
such adapter, new signing key, payer ledger, exporter, credential access or
production read is authorized by this PR. Source/render review may proceed;
this gap cannot be counted as live acceptance or retention lift.

Fixtures can separately exercise the schema, chronology, coverage and suppression
rules with:

```sh
python3 backend/scripts/verify_yearly_switch_retention.py --read-only --schema-only --receipt PATH
```

Only schema mode may exit 0/SCHEMA_VALID, and it emits `live_acceptance: false`
with no metric table. It cannot be combined with either live/maturity flag.
SCHEMA_VALID means only that the supplied assertions satisfy the rules; it is
never evidence of deployment, approval, authorization or observed outcomes.

The receipt vocabulary and positive/negative examples are executable in
`backend/tests/unit/test_verify_yearly_switch_retention.py`. Required fields:

- `experiment`, `unit=uid`, `authority=authorized_aggregate_verifier`,
  `evidence_ref`, `generated_at` (within 24h).
- `release`: exact current `backend_commit`, `client_commit`, `client_build`,
  `deployed_at`, and `serving_evidence_ref`. This conservative gate requires both
  release commits to equal the checked-out implementation commit.
- `approval`: `approved_by=David Zhang`, matching `source_commit`,
  `issue_comment_ref`, and exact SHA256 of the checked-in `render-manifest.json`
  and `copy.json` in `.agent-artifacts/ui-evidence/yearly-retention`.
- `gates`: `enabled`, `rollout_authorized`, `stable_uid_holdout`, `once_only`,
  `non_overlap`, plus `evidence_ref` for the operational checks.
- `cohort_start`, `cohort_end`, `observed_through`: timezone-aware, after release,
  no future observation, at least 60 days after the final enrollment.
- `measurement`: `revenue_basis=realized_net_revenue_per_enrolled_uid`,
  `refunds=included`, `currency=USD`, `fx_policy=exclude_non_usd`,
  `billing_linkage_evidence_ref`, `uncertainty_method`.
- `arms.control`/`arms.treatment`: `enrolled`, mutually exclusive coverage
  categories `linked`, `missing_linkage`, `ambiguous_linkage`, `non_usd`,
  `censored`; `take_up`/`effective_ends_30`/`effective_ends_60` with `count` and
  `ci95`; `revenue_per_uid` with `mean_usd` and `ci95`.
- `comparison_ci95`: intervals for `take_up_difference`,
  `effective_ends_30_difference`, `effective_ends_60_difference`,
  `revenue_per_uid_difference`, supplied by the authorized aggregate analysis.

The gate is deliberately conservative about an enrolled-UID denominator:
incomplete linkage produces WAITING rather than dividing partial revenue by all
enrollees or presenting a covered-only estimate as intention-to-treat. It
suppresses the entire metric table when any count or recoverable complement is
below ten, coverage is incomplete, or live/maturity evidence is missing. This
may withhold an underpowered reading; it is not a requirement for a new ledger
or a prerequisite for preparing this PR and approval packet. Revenue intervals
and missingness/FX sensitivity must come from authorized analysis; no attribution
is invented here. Direct churn credit remains 0pp until measured.

## Review and reproduction

The approval packet uses production widgets and synthetic prices. Cancellation
before is rendered from historical source `ac02feb05f0d6389f473e08a25980397b1348b0f`;
Home evidence shows the production placement in a minimal synthetic host, not a
full Home feed/device capture. The existing yearly-switch row and sheet are
reused. No David approval or workflow Kimi SECOND-LOOK is implied by local tests.

PR #25095 (inspected `c5c7557dd063251304cc16b6ee1d696a33af4d00`) overlaps the
yearly-switch widget and analytics registry. Its payment changes are untouched.
PR #25106 (inspected `4ccd6536f86f2f1920d2b0d2ec6484f170dbb360`) overlaps Home,
flags and generated API assets. Neither head was integrated or approved by this
PR. Reconcile those files at integration; do not overwrite either owner's work.
SCA-1753 plan-picker defaults and SCA-1809 web/macOS parity are untouched except
mechanically regenerated client transport methods.

```sh
backend/.venv/bin/python -m pytest backend/tests/unit/test_yearly_switch_retention.py backend/tests/unit/test_verify_yearly_switch_retention.py backend/tests/unit/test_yearly_switch.py backend/tests/unit/test_batch_pipeline_privacy.py backend/tests/unit/test_experiments.py -q
cd app
flutter test --no-pub --dart-define=YEARLY_RETENTION_RENDER_OUTPUT=../.agent-artifacts/ui-evidence/yearly-retention test/widgets/yearly_retention_test.dart test/widgets/yearly_switch_test.dart
bash test/widgets/render_yearly_retention_baseline.sh
```
