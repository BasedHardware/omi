-- P5 exact restart-safe query input. Query text and timezone remain sensitive
-- isolated experiment inputs; they are not graph, product, recall, or answer
-- authority. The snapshot itself remains in the authoritative graph tables.

CREATE TABLE omi_memory.memory_query_evaluation_inputs (
  account_id text NOT NULL,
  source_ref text NOT NULL CHECK (source_ref ~ '^mqes1_[0-9a-f]{64}$'),
  input_version text NOT NULL CHECK (input_version = 'memory-query-evaluation-input-v1'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  input_ref text NOT NULL CHECK (input_ref ~ '^mqir1_[0-9a-f]{64}$'),
  input_frontier text NOT NULL CHECK (input_frontier ~ '^mqef1_[0-9a-f]{64}$'),
  query_text text NOT NULL CHECK (
    length(query_text) BETWEEN 1 AND 4096
    AND query_text = btrim(query_text)
  ),
  account_timezone text NOT NULL CHECK (
    length(account_timezone) BETWEEN 1 AND 128
    AND account_timezone !~ '[[:space:][:cntrl:]]'
  ),
  graph_generation bigint NOT NULL CHECK (graph_generation >= 0),
  graph_snapshot_digest text NOT NULL CHECK (graph_snapshot_digest ~ '^[0-9a-f]{64}$'),
  stage_request_digest text NOT NULL CHECK (stage_request_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, source_ref),
  UNIQUE (account_id, input_ref),
  UNIQUE (account_id, input_frontier, source_ref),
  FOREIGN KEY (account_id) REFERENCES omi_memory.platform_accounts (account_id)
);

REVOKE ALL ON omi_memory.memory_query_evaluation_inputs FROM PUBLIC;
GRANT SELECT, INSERT ON omi_memory.memory_query_evaluation_inputs
  TO omi_platform_application;

-- Intentionally no UPDATE, DELETE, TRUNCATE, graph/product/work/recall/answer
-- mutation, model execution, route, grading, statistics, or promotion grant.
