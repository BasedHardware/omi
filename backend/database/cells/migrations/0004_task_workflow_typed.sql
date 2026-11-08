-- A2b, depends on B2 0002_write_fence.sql. Expand-only, before enrollment.
-- Adding STORED columns rewrites cell_docs under ACCESS EXCLUSIVE; no owner may
-- be enrolled until this migration and B2's wipe/admission gate are installed.
-- The shared codec stores datetimes as {"$datetime": "ISO8601+offset"}, not text.
-- Fixed timezone/DateStyle and an explicit offset make this parser immutable;
-- malformed legacy values yield NULL rather than aborting unrelated writes.
-- The exception handler opens a subtransaction, which parallel workers forbid.
CREATE FUNCTION cell_query_timestamp(value jsonb) RETURNS timestamptz
LANGUAGE plpgsql IMMUTABLE PARALLEL UNSAFE
SET timezone = 'UTC' SET datestyle = 'ISO, YMD'
AS $$
DECLARE encoded text;
BEGIN
    encoded := CASE WHEN jsonb_typeof(value) = 'object' THEN value->>'$datetime'
                    WHEN jsonb_typeof(value) = 'string' THEN value #>> '{}' END;
    IF encoded IS NULL OR encoded !~ '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$' THEN
        RETURN NULL;
    END IF;
    RETURN encoded::timestamptz;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow OR invalid_time_zone_displacement_value THEN
    RETURN NULL;
END;
$$;

-- The polymorphic jsonb_build_array is STABLE in PostgreSQL. These fixed
-- jsonb/numeric/text inputs are immutable; the timestamp decoder pins UTC.
-- Sharing this function keeps folder ordering, cursor keys and the index exact.
-- PostgreSQL 17 builds indexes under a restricted search_path, so pin the
-- creation path; otherwise the index build cannot resolve the decoder.
CREATE FUNCTION cell_folder_order_key(value jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE PARALLEL UNSAFE
SET search_path FROM CURRENT
AS $$
    SELECT CASE jsonb_typeof(value)
        WHEN 'null' THEN jsonb_build_array(0, 0)
        WHEN 'boolean' THEN jsonb_build_array(1, value)
        WHEN 'number' THEN jsonb_build_array(2, value)
        WHEN 'object' THEN CASE WHEN value ? '$datetime'
            THEN jsonb_build_array(3, extract(epoch FROM cell_query_timestamp(value) AT TIME ZONE 'UTC'))
            ELSE jsonb_build_array(5, value::text) END
        WHEN 'string' THEN jsonb_build_array(4, value)
        ELSE jsonb_build_array(5, value::text) END;
$$;

ALTER TABLE cell_docs ADD COLUMN q_completed boolean GENERATED ALWAYS AS
    (CASE WHEN entity = 'action_items' THEN doc->'completed' = 'true'::jsonb END) STORED,
    ADD COLUMN q_deleted boolean GENERATED ALWAYS AS
    (doc->'deleted' = 'true'::jsonb) STORED,
    ADD COLUMN q_due_at timestamptz GENERATED ALWAYS AS
    (cell_query_timestamp(doc->'due_at')) STORED,
    ADD COLUMN q_created_at timestamptz GENERATED ALWAYS AS
    (cell_query_timestamp(doc->'created_at')) STORED,
    ADD COLUMN q_updated_at timestamptz GENERATED ALWAYS AS
    (cell_query_timestamp(doc->'updated_at')) STORED,
    -- Key projections keep only JSON strings: a legacy numeric 123 must not
    -- match the string '123', matching the simulator's typed equality.
    ADD COLUMN q_conversation_id text GENERATED ALWAYS AS
    (CASE WHEN jsonb_typeof(doc->'conversation_id')='string' THEN doc->>'conversation_id' END) STORED,
    ADD COLUMN q_idempotency_key text GENERATED ALWAYS AS
    (CASE WHEN jsonb_typeof(doc->'idempotency_key')='string' THEN doc->>'idempotency_key' END) STORED,
    ADD COLUMN q_goal_id text GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc->'goal_id')='string' THEN doc->>'goal_id' END) STORED,
    ADD COLUMN q_status text GENERATED ALWAYS AS (doc->>'status') STORED,
    ADD COLUMN q_order jsonb GENERATED ALWAYS AS (doc->'order') STORED;

CREATE INDEX cell_docs_ai_list ON cell_docs
    (space_id, (coalesce(q_completed, false)), (q_due_at IS NULL),
     (coalesce(extract(epoch FROM q_due_at AT TIME ZONE 'UTC'), 'Infinity'::numeric)),
     (-coalesce(extract(epoch FROM q_created_at AT TIME ZONE 'UTC'), '-Infinity'::numeric)), entity_id COLLATE "C")
    WHERE entity = 'action_items' AND q_deleted IS DISTINCT FROM TRUE;
CREATE INDEX cell_docs_ai_due ON cell_docs (space_id, q_due_at) WHERE entity = 'action_items';
CREATE INDEX cell_docs_ai_conv ON cell_docs (space_id, q_conversation_id) WHERE entity = 'action_items';
CREATE INDEX cell_docs_ai_idem ON cell_docs (space_id, q_idempotency_key) WHERE entity = 'action_items';
CREATE INDEX cell_docs_sync_keyset ON cell_docs (space_id, q_updated_at, entity_id COLLATE "C")
    WHERE entity = 'action_items';
CREATE INDEX cell_docs_ws_goal ON cell_docs (space_id, q_goal_id) WHERE entity = 'workstreams';
CREATE INDEX cell_docs_goal_status ON cell_docs (space_id, q_status) WHERE entity = 'goals';
CREATE INDEX cell_docs_folder_order ON cell_docs
    (space_id, cell_folder_order_key(q_order), entity_id COLLATE "C") WHERE entity = 'folders';
CREATE INDEX cell_docs_people_name ON cell_docs (space_id, (doc->>'name'), entity_id COLLATE "C") WHERE entity = 'people';
