# Critical pipeline failures

These page-tier rules notify the existing Telegram receiver, with no always-on
agent mute. Telegram delivery is not a DND wake service. No receiver, phone,
credential or Cloud Monitoring notification-channel change is part of this fix.

`live-alert-gate.json` is both the import list and the fail-closed read-back list.
The existing metrics-egress workflow triggers on that file, calls
`verify_pusher_live_alert_route.py --mode import`, then verifies the `live-stt`
import set with `--fail-on gated`. This includes rules from every active split
file, not only `live-stt.json`. The combined export must equal the split exports.
No workflow change is needed to promote the former pending batch rules.

## Conditions and actions

Queries in `alerts/batch-timeliness.json` and `alerts/critical-failures.json` are
the executable definitions. Every rule contains the action, scope and threshold.

| Rule | Condition and pending duration | First action |
| --- | --- | --- |
| `omi-batch-unit-unpublished-2h` | New unpublished unit >7200 seconds, sample <1200 seconds old; 5m | Inspect the overdue leg and use the custody/recovery runbook; retain staged audio. |
| `omi-batch-held-backlog-growing` | Pre-epoch assignment-held stock >1000 with 1h growth >50, OR stock >=10,000; sample <1200 seconds old; 15m | Inspect assignment/projection recovery; at the count cap, drain held debt below the cap rather than infer a rate. |
| `omi-enrichment-queue-depth-page` | Native Cloud Tasks enrichment depth, 5m maximum >6000; 15m | Check dispatch, worker responses and drain rate before adding capacity. |
| `omi-stt-vendor-benched-page` | Soniox or Modulate minimum stage <=25; 15m | Inspect provider errors and GateState; get recovery approval before clearing a bench. |
| `omi-modulate-credit-page` | Any Modulate `provider_budget_exhausted` close in 15m; 1m | Billing owner verifies and restores credits before an account-circuit reset. |
| `omi-soniox-budget-exhausted` (existing) | Any Soniox `provider_budget_exhausted` close in 5m; immediate | Verify Soniox balance and restore credits before resetting its circuit. |
| `omi-incluster-guard-unsafe-page` | Any unsafe guard signal in 15m; 1m | Read verdict/reason and whether rollback completed; coordinate recovery with the lead. |

Batch stocks are replicated global gauges: take `max`, never
`sum` across worker/listen pods. Summing multiplies the backlog by replica count.
With `batch_timeliness_leader` enabled, historical counts stop at 10,000 per leg: a saturated value means
**at least** 10,000, not exact stock or measured growth. The held-backlog page therefore also fires on
stock >=10,000 without requiring growth history or a positive delta. It stays actionable while capped
stock is flat, including when the true stock is falling but still above the cap. Below the cap, the
original >1000 stock and >50/hour growth condition applies. Lever 0 restores exact counts; the >=10,000
stock condition still applies. Each stock is joined to its matching observation with `and ignoring(leg)`
before the fleet maximum, retaining only the source with the newest numeric observation; all replica/resource labels must match and the <1200 comparison omits `bool`.
Both branches, including the growth subquery, use that fresh fleet stock and retain the zero fallback.
Both branches require a fresh sample for 15 minutes. The sampling interval is clamped to 60–600 seconds
(default 300), keeping successful recurring observations below the 1200-second freshness boundary
through the full pending window. Configured 3600 now clamps to 600. Inspect aggregate
recovery progress and repair the held leg without deleting audio or removing the Firestore read bound.
All sampler gauges expire at collection after the configured sampling interval plus 60 seconds even
with election disabled; failed refreshes and lever changes do not extend that deadline. Existing leases
from older hourly samplers expire at their original deadline; this change does not revoke them.

The low-stage selector names the two serving paid targets; retired Parakeet's
persistent low stage must not cause this page. A pristine NaN stage does not
satisfy `<=25`. The credit alert uses the emitted closed `provider` and `reason`
labels, rather than raw HTTP bodies or a guessed `status_code` label.
Soniox already has a page in the live-STT gate; the new credit rule covers
Modulate only, so the two rules cannot double-notify for one provider refusal.

## Evidence and coverage

Read-only observation on 2026-11-03 used `ro-prod` and aggregate queries only.
The requested window is seven days at 60s steps. The checked-in metric inventory
proves names for local Prometheus; exact selectors were also read live. Native
Cloud Tasks depth and its `queue_id="enrichment"` label were verified through
the GMP-compatible Cloud Monitoring API. No query reads account records.

* Batch age/sample/held series are retained only on Nov3, starting around 09:20Z.
  The available age minimum is 97211s, sample-age maximum 312s, held stock
  4300..4461 and hourly growth p95 74 / max 83. The 2h threshold is the stated
  contract, not a percentile fitted to an already unhealthy day. No historical
  normal day exists for these new series; normal controls are synthetic.
* Native enrichment history starts Nov1. Nov1 max 1216 and Nov2 max 5261 sit
  below 6000; Nov3 reaches 22552. Nov2 is a quiet reference for this alert,
  not proof that all product paths were healthy that day.
* Finalization blocked-BYOK dwell and dead-letter stock/age coverage belong to
  [PR #24533](https://github.com/BasedHardware/omi/pull/24533). This change adds
  no duplicate finalization rule; the lead must include that PR in the release.
* Paid-vendor stages are present for the full local window, including extended
  Modulate stage 5..25 and Nov3 benches. A 15m pending duration excludes short
  stage dips; stage 100 is the normal control. The bench itself is actionable
  even when the other provider keeps overall transcription successful.
* Local credit-close replay catches two Soniox episodes on Nov2 (maximum
  15m count about 54). Oct28 and Nov3 remain quiet. A single synthetic
  402-classified close must fire after 1m. GMP-only credit reads had missed
  these local listen events, so the rule deliberately uses local Prometheus.
* The unsafe guard counter is new and has no backfilled series. Replay of the
  older structured guard logs is a counterfactual mapping, not historical
  evaluation of a deployed counter. Synthetic TRIP/BLIND/error and clean/dry-run
  controls verify the emitted signal. Never claim a new counter's history exists.

Replay evidence belongs in the lane handoff, including exact query parameters,
retained coverage, daily episodes, pending durations and control results. Replay
proves evaluation, not notification delivery; Grafana read-back after deployment
and a receiver delivery check remain separate production checks.

## Lead-owned deployment

This lane makes no live alert, Grafana, GKE or Cloud Monitoring changes.

1. Before importing the guard page, create/update the bounded log counter from
   `guard-unsafe.log-metric.json` in `based-hardware`, using the existing
   operator-approved monitoring path. For a missing metric the CLI command is
   `gcloud logging metrics create omi_incluster_guard_unsafe --project=based-hardware --config-from-file=backend/charts/monitoring/guard-unsafe.log-metric.json`.
   For an existing metric use `gcloud logging metrics update` with the same
   arguments. This is a deploy step for the lead; no IAM grant is part of the PR.
2. Dispatch the existing in-cluster guards workflow at the merged SHA. Verify
   the script ConfigMap contains `page_signal`, and the next scheduled run
   emits it. Dry-run readings emit `false`; do not induce a production trip.
3. Dispatch the existing metrics-egress workflow for production at the merged
   SHA. Its independent import job installs all gate UIDs and verifies active,
   definition-equal rules and their Telegram routing. A main push alone targets
   development and does not prove a production import.
   The importer omits the two native production-project rules (enrichment and
   guard counter) from development, which has no verified equivalent datasource.
4. Check the new counter is queryable after a naturally unsafe verdict, and
   verify a notification through the receiver's approved delivery test. An
   import gate proves definitions/routes, not phone delivery or a working log
   metric. Missing signal or permissions keeps this deploy unqualified.

The counter has no extracted labels: only fixed production namespace and guard
container selectors plus `page_signal=true`. It reads no payloads in Grafana,
creates no raw-log query load and does not notify on dry runs. This signal adds
no rollback authority and does not change guard verdicts, mutations or exits.

Rollback is a forward revert of these alert definitions and gate entries,
followed by the same import; reverting the guard source removes the signal.
Keep the log metric rather than deleting history. Existing debt and real trips
must remain tracked by the rollout lead while an alert is reverted.

`vendor_runway.py` lives in the workspace rollout tooling, not this repository.
Its separately tested companion patch returns 2 for a missing key/API, missing
burn history or failed history write, while preserving the atomic export and
the existing nonzero low-runway result. A measured zero burn is healthy. The
lead must install that companion patch into the supervised coord snapshot;
merging this public PR alone does not repair the installed watcher.
