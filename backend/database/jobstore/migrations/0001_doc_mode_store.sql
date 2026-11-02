-- A1 doc mode: the batch `Store` protocol over Postgres.
--
-- Each logical table keeps its whole document in `doc jsonb` (byte-faithful round trip for the
-- goldens) and exposes the fields the Firestore queries index as STORED generated columns, so the
-- indexed columns can never drift from the document. Every row is scoped by `namespace`
-- (batch_pipeline_prod | _dev | _test_<id>), the same isolation the Firestore store uses.
-- Expand-only: later migrations add columns/tables/indexes; contracting ships one train later.

CREATE TABLE jobs (
    namespace        text   NOT NULL,
    key              text   NOT NULL,
    doc              jsonb  NOT NULL,
    state            text   GENERATED ALWAYS AS (doc->>'state') STORED,
    owner_key        text   GENERATED ALWAYS AS (doc->>'owner_key') STORED,
    priority         int    GENERATED ALWAYS AS ((doc->>'priority')::int) STORED,
    merge_pending    boolean GENERATED ALWAYS AS ((doc->>'merge_pending')::boolean) STORED,
    next_id          text   GENERATED ALWAYS AS (doc->>'next') STORED,
    capture_at       float8 GENERATED ALWAYS AS ((doc->>'capture_at')::float8) STORED,
    enqueued_at      float8 GENERATED ALWAYS AS ((doc->>'enqueued_at')::float8) STORED,
    available_at     float8 GENERATED ALWAYS AS ((doc->>'available_at')::float8) STORED,
    lease_until      float8 GENERATED ALWAYS AS ((doc->>'lease_until')::float8) STORED,
    retry_started_at float8 GENERATED ALWAYS AS ((doc->>'retry_started_at')::float8) STORED,
    PRIMARY KEY (namespace, key)
);
CREATE INDEX jobs_merge_head   ON jobs (namespace, owner_key, capture_at, key) WHERE merge_pending;
CREATE INDEX jobs_predecessor  ON jobs (namespace, owner_key, priority, next_id) WHERE state = 'ready';
CREATE INDEX jobs_due_leased   ON jobs (namespace, lease_until, key)  WHERE state = 'leased';
CREATE INDEX jobs_due_retry    ON jobs (namespace, available_at, key) WHERE state IN ('retry', 'record_pending');
CREATE INDEX jobs_due_result   ON jobs (namespace, enqueued_at, key)  WHERE state = 'result_ready';
CREATE INDEX jobs_age_ready    ON jobs (namespace, priority, enqueued_at) WHERE state = 'ready';
CREATE INDEX jobs_age_pending  ON jobs (namespace, priority, enqueued_at) WHERE merge_pending;
CREATE INDEX jobs_retry_age    ON jobs (namespace, priority, retry_started_at) WHERE retry_started_at IS NOT NULL;

CREATE TABLE results (
    namespace        text  NOT NULL,
    key              text  NOT NULL,
    doc              jsonb NOT NULL,
    projection_state text  GENERATED ALWAYS AS (doc->>'projection_state') STORED,
    committed_at     float8 GENERATED ALWAYS AS ((doc->>'committed_at')::float8) STORED,
    PRIMARY KEY (namespace, key)
);
CREATE INDEX results_projection ON results (namespace, committed_at, key)
    WHERE projection_state IN ('pending', 'persisted', 'ready');

CREATE TABLE control (
    namespace        text  NOT NULL,
    key              text  NOT NULL,
    doc              jsonb NOT NULL,
    p0_active        boolean GENERATED ALWAYS AS ((doc->>'p0_active')::boolean) STORED,
    p1_active        boolean GENERATED ALWAYS AS ((doc->>'p1_active')::boolean) STORED,
    p2_active        boolean GENERATED ALWAYS AS ((doc->>'p2_active')::boolean) STORED,
    p0_service       float8 GENERATED ALWAYS AS ((doc->>'p0_service')::float8) STORED,
    p1_service       float8 GENERATED ALWAYS AS ((doc->>'p1_service')::float8) STORED,
    p2_service       float8 GENERATED ALWAYS AS ((doc->>'p2_service')::float8) STORED,
    p0_batch_at      float8 GENERATED ALWAYS AS ((doc->>'p0_batch_available_at')::float8) STORED,
    p1_batch_at      float8 GENERATED ALWAYS AS ((doc->>'p1_batch_available_at')::float8) STORED,
    p2_batch_at      float8 GENERATED ALWAYS AS ((doc->>'p2_batch_available_at')::float8) STORED,
    p0_live_at       float8 GENERATED ALWAYS AS ((doc->>'p0_live_available_at')::float8) STORED,
    p1_live_at       float8 GENERATED ALWAYS AS ((doc->>'p1_live_available_at')::float8) STORED,
    p2_live_at       float8 GENERATED ALWAYS AS ((doc->>'p2_live_available_at')::float8) STORED,
    PRIMARY KEY (namespace, key)
);
CREATE INDEX control_p0_batch ON control (namespace, p0_service, p0_batch_at, key) WHERE p0_active;
CREATE INDEX control_p1_batch ON control (namespace, p1_service, p1_batch_at, key) WHERE p1_active;
CREATE INDEX control_p2_batch ON control (namespace, p2_service, p2_batch_at, key) WHERE p2_active;
CREATE INDEX control_p0_live  ON control (namespace, p0_service, p0_live_at, key)  WHERE p0_active;
CREATE INDEX control_p1_live  ON control (namespace, p1_service, p1_live_at, key)  WHERE p1_active;
CREATE INDEX control_p2_live  ON control (namespace, p2_service, p2_live_at, key)  WHERE p2_active;

-- queues, owners, gpus, intakes, artifacts (and the harness-only conversations/content tables):
-- point reads and writes only.
CREATE TABLE docs (
    namespace text  NOT NULL,
    tbl       text  NOT NULL,
    key       text  NOT NULL,
    doc       jsonb NOT NULL,
    PRIMARY KEY (namespace, tbl, key)
);
