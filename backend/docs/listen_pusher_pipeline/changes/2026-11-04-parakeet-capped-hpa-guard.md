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
When v1 is busy (`first_count >= 20` and `admission_count >= 20`) and no
endpoint-specific v2 idle evidence is present, a `NaN` `v2_p95` remains `BLIND`
(`missing_or_nonfinite_v2_p95`) and three consecutive blind readings still
trigger rollback once armed. Zero duration completions alone cannot distinguish
an idle v2 endpoint from requests hung in flight, and early caller or readiness
errors (`422` speaker-bound validation or `503` model loading) increment
`parakeet_requests_total{endpoint="v2_transcribe",status="error"}` and return
before `parakeet_request_duration_seconds` is observed or
`parakeet_active_batch_requests` is incremented. Qualifying a busy-v1 / idle-v2
reading (`v2_idle_qualified`) therefore requires both zero endpoint-specific v2
in-flight requests (`v2_inflight_max == 0`) and zero v2 errors (`v2_errors == 0`)
with fresh v2 telemetry; shared v1/v2 batch gauges and v1-for-v2 latency
substitutions are never used.

Deployment uses the independent `gcp_incluster_guards.yml` workflow on main,
pinned to the merged SHA, with environment=prod, enabled=true, dry_run=false.
The lead owns deployment. No flag or serving image change is required.
See [guard contract and local verification](../../../charts/incluster-guards/README.md).
