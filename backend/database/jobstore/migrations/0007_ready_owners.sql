-- Owner-grain discovery skips a whole ready backlog block on each cursor step.
CREATE INDEX jobs_ready_owners_c ON jobs (namespace, owner_key COLLATE "C")
    WHERE state = 'result_ready' AND merge_pending;
-- The same btree supports the pass ceiling: ORDER BY owner_key COLLATE "C" DESC LIMIT 1
-- via a backward scan, with the same ready/merge_pending predicate and namespace equality.
