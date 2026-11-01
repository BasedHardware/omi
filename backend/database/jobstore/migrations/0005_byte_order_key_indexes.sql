-- Key tie-breaks follow Firestore's byte order (COLLATE "C"), whatever the database collation, so the
-- ordering indexes get C-collated twins. Expand-only: the default-collation originals from 0001/0004 drop
-- one train later as a contract.
CREATE INDEX jobs_merge_head_c    ON jobs (namespace, owner_key, capture_at, key COLLATE "C") WHERE merge_pending;
CREATE INDEX jobs_due_leased_c    ON jobs (namespace, lease_until, key COLLATE "C")  WHERE state = 'leased';
CREATE INDEX jobs_due_retry_c     ON jobs (namespace, available_at, key COLLATE "C") WHERE state IN ('retry', 'record_pending');
CREATE INDEX jobs_due_result_c    ON jobs (namespace, enqueued_at, key COLLATE "C")  WHERE state = 'result_ready';
CREATE INDEX jobs_pending_age_c   ON jobs (namespace, priority, enqueued_at, key COLLATE "C") WHERE merge_pending;
CREATE INDEX results_obligation_c ON results (namespace, projection_state, committed_at, key COLLATE "C");
