-- Expand only; old readers ignore the new state and the generic owner docs.
CREATE INDEX jobs_allowance_owner_capture ON jobs (namespace, owner_key, capture_at, key COLLATE "C")
    WHERE state = 'allowance_held';
CREATE INDEX docs_allowance_due ON docs (namespace, ((doc->>'check_at')::float8), key COLLATE "C")
    WHERE tbl = 'allowance_holds' AND doc->'active' = 'true'::jsonb;
