-- Both LIMIT 1 fresh queries preserve capture/key order without scanning the unready prefix.
CREATE INDEX jobs_merge_fresh_c ON jobs (namespace, owner_key, capture_at, key COLLATE "C")
    WHERE merge_pending AND doc->'fresh_capture' = 'true'::jsonb;
CREATE INDEX jobs_merge_fresh_ready_c ON jobs (namespace, owner_key, capture_at, key COLLATE "C")
    WHERE merge_pending AND doc->'fresh_capture' = 'true'::jsonb AND state = 'result_ready';
