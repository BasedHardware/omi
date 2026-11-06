# Timeliness rollback freshness and bounded backlog alerts

Every successful timeliness sample now sets a collection deadline at attempt start plus the configured
interval and 60-second grace, including `batch_timeliness_leader=0`. Failed sampling and lever changes
cannot extend visibility. A scrapeable replica whose supervisor stops withdraws all sampler gauges
at expiry, so its old debt cannot borrow another replica's fresh observation timestamp. Lever 0 still
bypasses election and restores per-instance queries and exact, unbounded historical counts.

The existing held-backlog page now detects either its original growth condition (>1000 pre-epoch
assignment-held units and >50 growth over one hour) or stock >=10,000. Both require a sample younger
than 900 seconds for 15 minutes. With election enabled, the unchanged `limit(10000).count()` reports a
lower bound at saturation. That stock is actionable even without measured growth: a flat capped series
must keep paging. Lever 0 uses the same alert condition on exact stock. No new metric or label is added;
the split alert, combined export and migration inventory describe the same query.

The 2-hour delivery alarm remains limited to the new cohort. Scheduling and repair do not consume the
capped historical counts. See the [sampler runbook](../../../charts/monitoring/batch-projection/README.md)
and [held-backlog actions](../../../charts/monitoring/critical-failures.md).

Regression cases extend `test_batch_pipeline_timeliness.py` for stalled replicas and failed refreshes
in elected, lever-zero and rollback modes, plus bounded assignment-held counts. The existing
`test_critical_failure_alerts.py` pins the mirrored query and adds an offline `PROMTOOL_BIN` semantic
case matrix for saturation, freshness, growth, pending and resolution. These cases are authored only;
execution and publication belong to the parent validation turn.
