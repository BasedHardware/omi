# Bound fleet queue metric reads

Serving queue-age/count sampling uses the existing advisory lease implementation
with an independent metrics role. GPU samplers retain their per-pod freshness
contract and bound only fleet queue queries to a 60-second interval. The default-on
`batch_metrics_oldest_leader` Firestore read lever restores previous per-instance
behavior at 0. Timeliness, projection and local event metrics keep their schedules.
Queue samples expire after 60 seconds even if refresh stops. See the
[queue safety runbook](../../runbooks/batch-queue-safety.md#fleet-queue-sample-ownership)
for cadence, fail-open semantics and rollback.
