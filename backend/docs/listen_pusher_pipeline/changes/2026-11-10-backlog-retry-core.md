# Batch backlog retry state (PR #24936)

The [backlog state-machine runbook](../../runbooks/backlog-state-machine.md)
defines the batch lease-expiry and held re-drive transitions. Class 1's
`CAPTURE_RETRY_CAP_ENFORCED` defaults off: enabling it quarantines exhausted
batch units for every owner, retaining audio and custody. With it off, the
existing capture-coverage cohort decides. Sync recovery remains main's behavior;
class 2 and terminal held re-drive stops belong to the #24893 follow-up.

Class 3's `BATCH_HELD_REDRIVE_BUDGET_ENABLED` defaults off. With the class 6
counter on and the owner's retry cap enforcing, a held re-drive resets `attempt`
for the first three re-drives and retains prior attempt history. Turning it off
stops new resets; already granted attempts remain bounded by `MAX_ATTEMPTS`.
`BATCH_HELD_REDRIVE_COUNTER_ENABLED` defaults on and counts held re-drives without
changing custody. Nightly, operator and poll paths emit a spent-budget signal
only after a committed re-drive, excluding failed, skipped and replayed rows.
The alert families pass through the Cloud Run sidecar and exporter allowlists.

Rollout follows the PR's deployment cohorts: dev, backend-integration, one prod
service, then all prod. The backlog-refactor owner and lead2 must assign dates
before enabling either default-off behavior switch. Check quarantine decisions
against prior would-quarantine observations, and compare committed held units
with re-quarantines before expanding. Keep the single-unit loop page active.

Unit verification covers switches unset/on/off, retained custody, bounded grants
and on-to-off rollback, committed-only counter emission with replay and failure
cases, and alert ingestion through both sidecars and all dev/prod exporters.
See `tests/unit/test_backlog_state_machine.py`,
`tests/unit/test_backlog_redrive_metrics.py`, and
`tests/unit/test_monitoring_telemetry_contract.py`. This is unit evidence; no
deployment, live recording or production ramp is performed by this PR.
