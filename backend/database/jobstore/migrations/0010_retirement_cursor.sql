-- Expand only. Sensitive cursor text stays in PG, never telemetry.
CREATE TABLE jobstore_retirement_cursor (
    namespace text NOT NULL,
    source text NOT NULL CHECK (source IN ('primary', 'copy')),
    tbl text NOT NULL CHECK (tbl IN ('jobs', 'queues', 'owners', 'control', 'results', 'gpus',
                                    'intakes', 'artifacts', 'allowance_holds', 'pull_claims', 'merge_holds')),
    mode text NOT NULL CHECK (mode IN ('apply', 'dry_run')),
    target_identity text NOT NULL CHECK (target_identity ~ '^[0-9a-f]{64}$'),
    cursor text CHECK (octet_length(cursor) <= 16384),
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    passes bigint NOT NULL DEFAULT 0 CHECK (passes >= 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    rotation_completed_at timestamptz,
    PRIMARY KEY (namespace, source, tbl, mode, target_identity)
);
