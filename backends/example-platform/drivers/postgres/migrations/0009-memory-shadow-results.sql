-- P5 inert evaluation results. Baseline and candidate payloads are physically
-- separate from durable work, graph, projection, recall, and answer authority.
-- Pair rows contain only opaque coordinates/digests. No runtime or grant exists.

ALTER TABLE omi_memory.memory_strategy_shadow_assignments
  ADD CONSTRAINT memory_strategy_shadow_assignments_exact_entry_unique
  UNIQUE (
    account_id, assignment_bundle_id, assignment_id, strategy_id,
    execution_contract_digest, work_kind
  );

ALTER TABLE omi_memory.memory_strategy_assignment_bundles
  ADD CONSTRAINT memory_strategy_assignment_bundles_digest_unique
  UNIQUE (account_id, assignment_bundle_id, assignment_bundle_digest);

CREATE TABLE omi_memory.memory_strategy_evaluation_baselines (
  account_id text NOT NULL,
  evaluation_result_id text NOT NULL CHECK (evaluation_result_id ~ '^msr1_[0-9a-f]{64}$'),
  result_version text NOT NULL CHECK (result_version = 'memory-evaluation-result-v1'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  assignment_bundle_id text NOT NULL,
  assignment_bundle_digest text NOT NULL CHECK (assignment_bundle_digest ~ '^[0-9a-f]{64}$'),
  assignment_id text NOT NULL,
  strategy_id text NOT NULL,
  execution_contract_digest text NOT NULL CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  evaluation_mode text NOT NULL CHECK (evaluation_mode IN ('live_shadow', 'offline_replay')),
  evaluation_run_id text NOT NULL CHECK (evaluation_run_id ~ '^mer1_[0-9a-f]{64}$'),
  input_frontier text NOT NULL CHECK (length(input_frontier) BETWEEN 1 AND 256),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  repeat_ordinal integer NOT NULL CHECK (repeat_ordinal BETWEEN 0 AND 999),
  result_contract_version text NOT NULL CHECK (length(result_contract_version) BETWEEN 1 AND 256),
  response_digest text NOT NULL CHECK (response_digest ~ '^[0-9a-f]{64}$'),
  normalized_result_digest text NOT NULL CHECK (normalized_result_digest ~ '^[0-9a-f]{64}$'),
  normalized_result_json jsonb NOT NULL
    CHECK (jsonb_typeof(normalized_result_json) = 'object')
    CHECK (octet_length(normalized_result_json::text) <= 524288),
  stage_request_digest text NOT NULL CHECK (stage_request_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, evaluation_result_id),
  UNIQUE (
    account_id, assignment_bundle_id, evaluation_mode, evaluation_run_id,
    input_frontier, input_digest, repeat_ordinal
  ),
  UNIQUE (
    account_id, evaluation_result_id, assignment_bundle_id, account_epoch,
    evaluation_mode, evaluation_run_id, input_digest,
    repeat_ordinal, strategy_id, normalized_result_digest
  ),
  FOREIGN KEY (
    account_id, assignment_bundle_id, assignment_bundle_digest, work_kind,
    assignment_id, strategy_id, execution_contract_digest
  ) REFERENCES omi_memory.memory_strategy_assignment_bundles (
    account_id, assignment_bundle_id, assignment_bundle_digest, work_kind,
    authority_assignment_id, authority_strategy_id, authority_execution_contract_digest
  )
);

CREATE TABLE omi_memory.memory_strategy_shadow_results (
  account_id text NOT NULL,
  evaluation_result_id text NOT NULL CHECK (evaluation_result_id ~ '^msr1_[0-9a-f]{64}$'),
  result_version text NOT NULL CHECK (result_version = 'memory-evaluation-result-v1'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  assignment_bundle_id text NOT NULL,
  assignment_bundle_digest text NOT NULL CHECK (assignment_bundle_digest ~ '^[0-9a-f]{64}$'),
  assignment_id text NOT NULL,
  strategy_id text NOT NULL,
  execution_contract_digest text NOT NULL CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  evaluation_mode text NOT NULL CHECK (evaluation_mode IN ('live_shadow', 'offline_replay')),
  evaluation_run_id text NOT NULL CHECK (evaluation_run_id ~ '^mer1_[0-9a-f]{64}$'),
  input_frontier text NOT NULL CHECK (length(input_frontier) BETWEEN 1 AND 256),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  repeat_ordinal integer NOT NULL CHECK (repeat_ordinal BETWEEN 0 AND 999),
  result_contract_version text NOT NULL CHECK (length(result_contract_version) BETWEEN 1 AND 256),
  response_digest text NOT NULL CHECK (response_digest ~ '^[0-9a-f]{64}$'),
  normalized_result_digest text NOT NULL CHECK (normalized_result_digest ~ '^[0-9a-f]{64}$'),
  normalized_result_json jsonb NOT NULL
    CHECK (jsonb_typeof(normalized_result_json) = 'object')
    CHECK (octet_length(normalized_result_json::text) <= 524288),
  stage_request_digest text NOT NULL CHECK (stage_request_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, evaluation_result_id),
  UNIQUE (
    account_id, assignment_bundle_id, assignment_id, evaluation_mode,
    evaluation_run_id, input_frontier, input_digest, repeat_ordinal
  ),
  UNIQUE (
    account_id, evaluation_result_id, assignment_bundle_id, account_epoch,
    evaluation_mode, evaluation_run_id, input_digest,
    repeat_ordinal, strategy_id, normalized_result_digest
  ),
  FOREIGN KEY (
    account_id, assignment_bundle_id, assignment_id, strategy_id,
    execution_contract_digest, work_kind
  ) REFERENCES omi_memory.memory_strategy_shadow_assignments (
    account_id, assignment_bundle_id, assignment_id, strategy_id,
    execution_contract_digest, work_kind
  ),
  FOREIGN KEY (account_id, assignment_bundle_id)
    REFERENCES omi_memory.memory_strategy_assignment_bundles
      (account_id, assignment_bundle_id),
  FOREIGN KEY (account_id, assignment_bundle_id, assignment_bundle_digest)
    REFERENCES omi_memory.memory_strategy_assignment_bundles
      (account_id, assignment_bundle_id, assignment_bundle_digest)
);

CREATE TABLE omi_memory.memory_strategy_evaluation_pairs (
  account_id text NOT NULL,
  pair_id text NOT NULL CHECK (pair_id ~ '^mep1_[0-9a-f]{64}$'),
  pair_version text NOT NULL CHECK (pair_version = 'memory-evaluation-pair-v1'),
  pair_digest text NOT NULL CHECK (pair_digest ~ '^[0-9a-f]{64}$'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  assignment_bundle_id text NOT NULL,
  evaluation_mode text NOT NULL CHECK (evaluation_mode IN ('live_shadow', 'offline_replay')),
  evaluation_run_id text NOT NULL CHECK (evaluation_run_id ~ '^mer1_[0-9a-f]{64}$'),
  input_frontier_digest text NOT NULL CHECK (input_frontier_digest ~ '^[0-9a-f]{64}$'),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  repeat_ordinal integer NOT NULL CHECK (repeat_ordinal BETWEEN 0 AND 999),
  baseline_result_id text NOT NULL,
  baseline_strategy_id text NOT NULL,
  baseline_result_digest text NOT NULL CHECK (baseline_result_digest ~ '^[0-9a-f]{64}$'),
  candidate_result_id text NOT NULL,
  candidate_strategy_id text NOT NULL,
  candidate_result_digest text NOT NULL CHECK (candidate_result_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, pair_id),
  UNIQUE (account_id, pair_id, pair_digest),
  UNIQUE (account_id, baseline_result_id, candidate_result_id),
  FOREIGN KEY (
    account_id, baseline_result_id, assignment_bundle_id, account_epoch,
    evaluation_mode, evaluation_run_id, input_digest,
    repeat_ordinal, baseline_strategy_id, baseline_result_digest
  ) REFERENCES omi_memory.memory_strategy_evaluation_baselines (
    account_id, evaluation_result_id, assignment_bundle_id, account_epoch,
    evaluation_mode, evaluation_run_id, input_digest,
    repeat_ordinal, strategy_id, normalized_result_digest
  ),
  FOREIGN KEY (
    account_id, candidate_result_id, assignment_bundle_id, account_epoch,
    evaluation_mode, evaluation_run_id, input_digest,
    repeat_ordinal, candidate_strategy_id, candidate_result_digest
  ) REFERENCES omi_memory.memory_strategy_shadow_results (
    account_id, evaluation_result_id, assignment_bundle_id, account_epoch,
    evaluation_mode, evaluation_run_id, input_digest,
    repeat_ordinal, strategy_id, normalized_result_digest
  ),
  CHECK (baseline_strategy_id <> candidate_strategy_id)
);

REVOKE ALL ON ALL TABLES IN SCHEMA omi_memory FROM PUBLIC;

-- Deliberately no application, worker, evaluator, or migration-runner grant.
-- Evaluation rows cannot authorize memory work, graph writes, projections, or reads.
