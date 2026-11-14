-- Owner-grain discovery skips a whole ready backlog block on each cursor step.
CREATE INDEX jobs_ready_owners_c ON jobs (namespace, owner_key COLLATE "C")
    WHERE state = 'result_ready' AND merge_pending;
