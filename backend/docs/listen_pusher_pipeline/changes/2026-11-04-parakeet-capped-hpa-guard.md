# Parakeet rollback under an operator cap

The in-cluster guard accepts integer HPA caps from 1 through 12 while keeping
the existing metric and scaling-policy drift assertions. A safety rollback
atomically restores maxReplicas=12 alongside minReplicas=12 and the latency
metric. The ordinary floor schedule still preserves the operator's cap and
refuses targets above it.

The v2 duration histogram (`parakeet_request_duration_seconds{exported_endpoint="v2_transcribe"}`)
can remain fresh with no completed requests while traffic uses v1. Under the
existing low-sample exception (`first_count < 20` or `admission_count < 20`
with all five staleness checks `<= 120s`), a `NaN` `v2_p95` is already accepted
as `LOW_SAMPLE` (`blind == []`) so quiet hours do not accumulate blind strikes.
When v1 is busy (`first_count >= 20` and `admission_count >= 20`), a `NaN`
`v2_p95` remains `BLIND` (`missing_or_nonfinite_v2_p95`) and three consecutive
blind readings still trigger rollback once armed: zero duration completions
alone cannot distinguish an idle v2 endpoint from requests hung in flight, and
early caller or readiness errors (`422` speaker-bound validation or `503` model
loading) increment `parakeet_requests_total{endpoint="v2_transcribe",status="error"}`
and return before `parakeet_request_duration_seconds` is observed or
`parakeet_active_batch_requests` is incremented. Distinguishing busy-v1 /
idle-v2 from a stalled or failing v2 endpoint requires endpoint-specific v2
arrival/in-flight and error telemetry; no busy-v1 idle exception, shared v1/v2
batch gauge, or v1-for-v2 latency substitution ships in this repair.

Deployment uses the independent `gcp_incluster_guards.yml` workflow on main,
pinned to the merged SHA, with environment=prod, enabled=true, dry_run=false.
The lead owns deployment. No flag or serving image change is required.
See [guard contract and local verification](../../../charts/incluster-guards/README.md).
