# Parakeet rollback under an operator cap

The in-cluster guard accepts integer HPA caps from 1 through 12 while keeping
the existing metric and scaling-policy drift assertions. A safety rollback
atomically restores maxReplicas=12 alongside minReplicas=12 and the latency
metric. The ordinary floor schedule still preserves the operator's cap and
refuses targets above it.

The v2 duration histogram can remain fresh with zero requests while traffic
uses v1. The guard now measures v2's own 15-minute request counter (including
early errors not recorded by the duration histogram) and tolerates NaN p95
only with a fresh zero count. Missing/stale telemetry and nonfinite
p95 with v2 traffic remain blind; three consecutive blind readings still
trigger rollback once armed. V1 and v2 latency thresholds are not substituted.

Deployment uses the independent `gcp_incluster_guards.yml` workflow on main,
pinned to the merged SHA, with environment=prod, enabled=true, dry_run=false.
The lead owns deployment. No flag or serving image change is required.
See [guard contract and local verification](../../../charts/incluster-guards/README.md).
