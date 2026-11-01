-- Store-protocol parity (A3 step 1). Expand-only.
--
-- Key tie-breaks follow Firestore's byte order (COLLATE "C"), whatever the database collation, so the
-- ordering indexes get C-collated twins; the 0001 originals are dropped one train later as a contract.
CREATE INDEX jobs_merge_head_c  ON jobs (namespace, owner_key, capture_at, key COLLATE "C") WHERE merge_pending;
CREATE INDEX jobs_due_leased_c  ON jobs (namespace, lease_until, key COLLATE "C")  WHERE state = 'leased';
CREATE INDEX jobs_due_retry_c   ON jobs (namespace, available_at, key COLLATE "C") WHERE state IN ('retry', 'record_pending');
CREATE INDEX jobs_due_result_c  ON jobs (namespace, enqueued_at, key COLLATE "C")  WHERE state = 'result_ready';
CREATE INDEX jobs_pending_age_c ON jobs (namespace, priority, enqueued_at, key COLLATE "C") WHERE merge_pending;
-- The result-log successor hint, and projection pages over any drain state (the 0001 partial index
-- does not cover quarantine_held).
CREATE INDEX results_successor  ON results (namespace, (doc->>'owner_key'), (doc->>'previous_segment_id'));
CREATE INDEX results_obligation ON results (namespace, projection_state, committed_at, key COLLATE "C");
