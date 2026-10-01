-- P5 sensitive finalized query grounding. These rows are physically isolated
-- from graph/product authority and must be inserted in the same transaction as
-- their exact evaluation result by the future named repository adapter.

ALTER TABLE omi_memory.memory_strategy_evaluation_baselines
  ADD CONSTRAINT memory_strategy_evaluation_baselines_grounding_fk_unique
  UNIQUE (
    account_id, evaluation_result_id, account_epoch, input_digest, strategy_id,
    execution_contract_digest, result_contract_version,
    normalized_result_digest, response_digest
  );

ALTER TABLE omi_memory.memory_strategy_shadow_results
  ADD CONSTRAINT memory_strategy_shadow_results_grounding_fk_unique
  UNIQUE (
    account_id, evaluation_result_id, account_epoch, input_digest, strategy_id,
    execution_contract_digest, result_contract_version,
    normalized_result_digest, response_digest
  );

CREATE TABLE omi_memory.memory_strategy_baseline_read_groundings (
  account_id text NOT NULL,
  grounding_artifact_id text NOT NULL CHECK (grounding_artifact_id ~ '^mgr1_[0-9a-f]{64}$'),
  evaluation_result_id text NOT NULL CHECK (evaluation_result_id ~ '^msr1_[0-9a-f]{64}$'),
  artifact_version text NOT NULL CHECK (artifact_version = 'finalized-query-grounding-v1'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  copied_input_digest text NOT NULL CHECK (copied_input_digest ~ '^[0-9a-f]{64}$'),
  input_frontier_digest text NOT NULL CHECK (input_frontier_digest ~ '^[0-9a-f]{64}$'),
  strategy_id text NOT NULL CHECK (length(strategy_id) BETWEEN 1 AND 256),
  execution_contract_digest text NOT NULL CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  result_contract_version text NOT NULL CHECK (result_contract_version = 'memory-read-evaluation-result-v1'),
  normalized_result_digest text NOT NULL CHECK (normalized_result_digest ~ '^[0-9a-f]{64}$'),
  response_digest text NOT NULL CHECK (response_digest ~ '^[0-9a-f]{64}$'),
  projection_authorization_digest text NOT NULL CHECK (projection_authorization_digest ~ '^[0-9a-f]{64}$'),
  reader_projection_digest text NOT NULL CHECK (reader_projection_digest ~ '^[0-9a-f]{64}$'),
  projected_content_digest text NOT NULL CHECK (projected_content_digest ~ '^[0-9a-f]{64}$'),
  grounded_reference_count integer NOT NULL CHECK (grounded_reference_count BETWEEN 0 AND 10000),
  rows_json jsonb NOT NULL
    CHECK (jsonb_typeof(rows_json) = 'array')
    CHECK (jsonb_array_length(rows_json) = grounded_reference_count)
    CHECK (octet_length(rows_json::text) <= 1048576),
  artifact_digest text NOT NULL CHECK (artifact_digest ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, grounding_artifact_id),
  UNIQUE (account_id, evaluation_result_id),
  UNIQUE (account_id, grounding_artifact_id, artifact_digest),
  FOREIGN KEY (
    account_id, evaluation_result_id, account_epoch, copied_input_digest,
    strategy_id, execution_contract_digest, result_contract_version,
    normalized_result_digest, response_digest
  ) REFERENCES omi_memory.memory_strategy_evaluation_baselines (
    account_id, evaluation_result_id, account_epoch, input_digest,
    strategy_id, execution_contract_digest, result_contract_version,
    normalized_result_digest, response_digest
  )
);

CREATE TABLE omi_memory.memory_strategy_candidate_read_groundings (
  account_id text NOT NULL,
  grounding_artifact_id text NOT NULL CHECK (grounding_artifact_id ~ '^mgr1_[0-9a-f]{64}$'),
  evaluation_result_id text NOT NULL CHECK (evaluation_result_id ~ '^msr1_[0-9a-f]{64}$'),
  artifact_version text NOT NULL CHECK (artifact_version = 'finalized-query-grounding-v1'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  copied_input_digest text NOT NULL CHECK (copied_input_digest ~ '^[0-9a-f]{64}$'),
  input_frontier_digest text NOT NULL CHECK (input_frontier_digest ~ '^[0-9a-f]{64}$'),
  strategy_id text NOT NULL CHECK (length(strategy_id) BETWEEN 1 AND 256),
  execution_contract_digest text NOT NULL CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  result_contract_version text NOT NULL CHECK (result_contract_version = 'memory-read-evaluation-result-v1'),
  normalized_result_digest text NOT NULL CHECK (normalized_result_digest ~ '^[0-9a-f]{64}$'),
  response_digest text NOT NULL CHECK (response_digest ~ '^[0-9a-f]{64}$'),
  projection_authorization_digest text NOT NULL CHECK (projection_authorization_digest ~ '^[0-9a-f]{64}$'),
  reader_projection_digest text NOT NULL CHECK (reader_projection_digest ~ '^[0-9a-f]{64}$'),
  projected_content_digest text NOT NULL CHECK (projected_content_digest ~ '^[0-9a-f]{64}$'),
  grounded_reference_count integer NOT NULL CHECK (grounded_reference_count BETWEEN 0 AND 10000),
  rows_json jsonb NOT NULL
    CHECK (jsonb_typeof(rows_json) = 'array')
    CHECK (jsonb_array_length(rows_json) = grounded_reference_count)
    CHECK (octet_length(rows_json::text) <= 1048576),
  artifact_digest text NOT NULL CHECK (artifact_digest ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, grounding_artifact_id),
  UNIQUE (account_id, evaluation_result_id),
  UNIQUE (account_id, grounding_artifact_id, artifact_digest),
  FOREIGN KEY (
    account_id, evaluation_result_id, account_epoch, copied_input_digest,
    strategy_id, execution_contract_digest, result_contract_version,
    normalized_result_digest, response_digest
  ) REFERENCES omi_memory.memory_strategy_shadow_results (
    account_id, evaluation_result_id, account_epoch, input_digest,
    strategy_id, execution_contract_digest, result_contract_version,
    normalized_result_digest, response_digest
  )
);

REVOKE ALL ON ALL TABLES IN SCHEMA omi_memory FROM PUBLIC;

-- Deliberately no application, worker, evaluator, or migration-runner grant.
-- A grounding artifact cannot authorize a graph/product/read result or memory work.
