-- Expand-only protocol parity; no row restamp. Apply before a PostgreSQL-primary worker roll.
CREATE INDEX jobs_protected_retry ON jobs (namespace, capture_at DESC, key COLLATE "C" DESC)
    WHERE state = 'retry' AND doc->'compute_decision'->>'outcome' IN ('unattempted', 'allowed');
CREATE INDEX jobs_protected_ready ON jobs (namespace, owner_key, priority, capture_at DESC, key COLLATE "C" DESC)
    WHERE state = 'ready' AND doc->'compute_decision'->>'outcome' IN ('unattempted', 'allowed');
