# Batch worker HPA retune

The dedicated batch worker raises its ready-unit target from 32 to 40 and
flight-wall target from 0.5 to 0.6. The proposed 64/0.8 pair failed the existing
measured-load headroom and step-response checks; the corrected pair preserves
them. The production floor/ceiling remain 4/16, and worker processes remain 1.

The targets ship on when the authorized lead applies chart values. Restore
32/0.5 to roll back. There are no new env, wire or payload contracts and no
admission-cohort change. Full-volume capacity remains unqualified: the
synthetic 3.7x fixture cannot satisfy the proposed eight-worker/no-hot bound.
The planscost lead accepts a staged apply at today's volume, with timeliness
and T3/hard-3 observation for one shed cycle plus 24h and rollback to 32/0.5
on regression. Before streaming retirement doubles batch volume, the lead
decides whether to raise maxReplicas above 16 (the replay needs 18 for zero
hot minutes). This PR leaves the ceiling unchanged.

[Worker sizing evidence and apply prerequisites](../../batch-pipeline-worker.md#retune-apply-and-rollback-lead)
include replay results, profiling/freshness requirements, alarm/index readiness
and the distinction between T3 policy and the custody-only automatic guard.
