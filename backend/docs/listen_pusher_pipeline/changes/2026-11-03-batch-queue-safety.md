# Batch queue age and two-hour alert

Queue age excludes dispositioned queue states while preserving custody and
the ordered commit owed by result_ready rows. An exhausted scan of holds is
BLIND instead of a fabricated late commitment. Grafana page-tier rules cover
two-hour queue debt and sustained scan/freshness blindness; the lead must import
them after deploying the worker and guard. No production data is changed.

See `backend/docs/runbooks/batch-queue-safety.md` for recovery paths and rollback.
