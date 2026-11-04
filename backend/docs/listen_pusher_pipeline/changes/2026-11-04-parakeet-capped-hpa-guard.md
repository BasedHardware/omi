# Parakeet rollback under an operator cap

The in-cluster guard accepts integer HPA caps from 1 through 12 while keeping
the existing metric and scaling-policy drift assertions. A safety rollback
atomically restores maxReplicas=12 alongside minReplicas=12 and the latency
metric. The ordinary floor schedule still preserves the operator's cap and
refuses targets above it.

The v2 duration histogram can remain fresh with no completed requests while
traffic uses v1. Its NaN p95 remains blind under the existing policy; three
consecutive blind readings still trigger rollback once armed. Zero completions
cannot distinguish idle v2 from stuck requests, and errors can precede duration
observations. A safe idle exception needs endpoint-specific in-flight evidence;
no metric-policy change or v1-for-v2 latency substitution ships in this repair.

Deployment uses the independent `gcp_incluster_guards.yml` workflow on main,
pinned to the merged SHA, with environment=prod, enabled=true, dry_run=false.
The lead owns deployment. No flag or serving image change is required.
See [guard contract and local verification](../../../charts/incluster-guards/README.md).
