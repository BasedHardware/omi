# Firestore spend guard

Production maintenance coordination defaults on independently of the
`singleton_loops` percentage in `FIRESTORE_READ_LEVERS`. Rolling back cache
levers must not restore a full queue-age and finalization scan on every replica.
Non-production, including staging (`OMI_ENV_STAGE=prod` with
`OMI_DEPLOYMENT=staging`), retains the existing cohort unless explicitly
overridden. Production means stage prod with an absent/prod/production
deployment identity; other explicit deployment identities retain qualification.

The existing Redis owner/generation/tick protocol is unchanged, including
interval cadence, stale-owner takeover, max-hold bounds, cooperative fencing,
SIGTERM release and Redis-outage local recovery. Queue publishing still requires
`FSR_QUEUE_AGE_PUBLISHER=1`; verify at least one healthy designated publisher
and fresh queue-age gauges before the lead deploys this source. Transactional
job claims, scan predicates, limits, user quotas, speaker processing and retained
audio are unchanged. This prevents a config-induced amplification; it does not
cap real workload or impose a per-user budget.

Rollback (lead only): set `FSR_MAINTENANCE_COORDINATION_ENABLED=false` on the
affected runtime through its regular deployment process. This intentionally
restores per-replica scans and can raise spend. Prefer leaving coordination on
when the guard breach is unrelated to maintenance; measure origin/caller
absolute reads and recovery age before assigning causality. Clear the override
or set true to restore coordination. No runtime config is changed by this PR.

Readback: observe `omi_fsr_leader_lease_total` by fixed loop/outcome, queue age
freshness, stale/in-progress recovery, existing error rate and live p95. Compare
`omi_firestore_billed_reads_by_caller_total` for queue sampling and three finjob
sweeps against the same Monitoring `document/read_ops_count` window; include
Cloud Run GMP and in-cluster GKE without double-counting. PromQL observations
are not invoice savings. Reconcile net read and write cost at D+1 against the
10-24/25 billing average, keeping incident recovery separate from new savings.
