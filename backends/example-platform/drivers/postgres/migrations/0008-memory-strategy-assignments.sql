-- P5 inert strategy registry and deterministic assignment persistence.
-- Authority work references exactly one authority assignment. Selected shadow
-- assignments are separately normalized and have no path to the work queue,
-- ledger, product projection, or answer authority. No runtime or grant is added.

CREATE TABLE omi_memory.memory_strategy_definitions (
  account_id text NOT NULL,
  strategy_id text NOT NULL CHECK (length(strategy_id) BETWEEN 1 AND 256),
  strategy_version text NOT NULL CHECK (strategy_version = 'memory-strategy-v1'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  execution_contract_digest text NOT NULL
    CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  algorithm_strategy_version text NOT NULL CHECK (length(algorithm_strategy_version) BETWEEN 1 AND 256),
  model_version text NOT NULL CHECK (length(model_version) BETWEEN 1 AND 256),
  prompt_version text NOT NULL CHECK (length(prompt_version) BETWEEN 1 AND 256),
  policy_version text NOT NULL CHECK (length(policy_version) BETWEEN 1 AND 256),
  code_version text NOT NULL CHECK (length(code_version) BETWEEN 1 AND 256),
  schema_version text NOT NULL CHECK (length(schema_version) BETWEEN 1 AND 256),
  tokenizer_version text NOT NULL CHECK (length(tokenizer_version) BETWEEN 1 AND 256),
  tool_version text NOT NULL CHECK (length(tool_version) BETWEEN 1 AND 256),
  result_contract_version text NOT NULL CHECK (length(result_contract_version) BETWEEN 1 AND 256),
  speaker_strategy_version text NOT NULL CHECK (length(speaker_strategy_version) BETWEEN 1 AND 256),
  boundary_strategy_version text NOT NULL CHECK (length(boundary_strategy_version) BETWEEN 1 AND 256),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, strategy_id),
  UNIQUE (account_id, strategy_id, execution_contract_digest, work_kind),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_strategy_assignment_policies (
  account_id text NOT NULL,
  policy_id text NOT NULL CHECK (length(policy_id) BETWEEN 1 AND 256),
  policy_version text NOT NULL
    CHECK (policy_version = 'memory-strategy-assignment-policy-v1'),
  policy_digest text NOT NULL CHECK (policy_digest ~ '^[0-9a-f]{64}$'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  unit_kind text NOT NULL CHECK (unit_kind IN ('account', 'session', 'work')),
  key_version text NOT NULL CHECK (length(key_version) BETWEEN 1 AND 256),
  authority_strategy_id text NOT NULL,
  authority_execution_contract_digest text NOT NULL
    CHECK (authority_execution_contract_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, policy_id),
  UNIQUE (account_id, policy_id, policy_digest, work_kind, unit_kind, key_version),
  UNIQUE (account_id, policy_id, work_kind),
  FOREIGN KEY (
    account_id, authority_strategy_id, authority_execution_contract_digest, work_kind
  ) REFERENCES omi_memory.memory_strategy_definitions (
    account_id, strategy_id, execution_contract_digest, work_kind
  )
);

CREATE TABLE omi_memory.memory_strategy_policy_shadows (
  account_id text NOT NULL,
  policy_id text NOT NULL,
  shadow_ordinal integer NOT NULL CHECK (shadow_ordinal >= 0),
  strategy_id text NOT NULL,
  execution_contract_digest text NOT NULL
    CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  basis_points integer NOT NULL CHECK (basis_points BETWEEN 0 AND 10000),
  PRIMARY KEY (account_id, policy_id, shadow_ordinal),
  UNIQUE (account_id, policy_id, strategy_id),
  UNIQUE (
    account_id, policy_id, strategy_id, execution_contract_digest, work_kind, basis_points
  ),
  FOREIGN KEY (account_id, policy_id, work_kind)
    REFERENCES omi_memory.memory_strategy_assignment_policies
      (account_id, policy_id, work_kind),
  FOREIGN KEY (account_id, strategy_id, execution_contract_digest, work_kind)
    REFERENCES omi_memory.memory_strategy_definitions
      (account_id, strategy_id, execution_contract_digest, work_kind)
);

CREATE TABLE omi_memory.memory_strategy_assignment_bundles (
  account_id text NOT NULL,
  assignment_bundle_id text NOT NULL
    CHECK (assignment_bundle_id ~ '^msb1_[0-9a-f]{64}$'),
  assignment_bundle_digest text NOT NULL
    CHECK (assignment_bundle_digest ~ '^[0-9a-f]{64}$'),
  assignment_version text NOT NULL
    CHECK (assignment_version = 'memory-strategy-assignment-v1'),
  policy_id text NOT NULL,
  policy_digest text NOT NULL CHECK (policy_digest ~ '^[0-9a-f]{64}$'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  unit_kind text NOT NULL CHECK (unit_kind IN ('account', 'session', 'work')),
  unit_digest text NOT NULL CHECK (unit_digest ~ '^[0-9a-f]{64}$'),
  key_version text NOT NULL CHECK (length(key_version) BETWEEN 1 AND 256),
  authority_assignment_id text NOT NULL
    CHECK (authority_assignment_id ~ '^msa1_[0-9a-f]{64}$'),
  authority_strategy_id text NOT NULL,
  authority_execution_contract_digest text NOT NULL
    CHECK (authority_execution_contract_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, assignment_bundle_id),
  UNIQUE (
    account_id, assignment_bundle_id, assignment_bundle_digest, work_kind,
    authority_assignment_id, authority_strategy_id, authority_execution_contract_digest
  ),
  UNIQUE (account_id, policy_id, unit_digest),
  FOREIGN KEY (account_id, policy_id, policy_digest, work_kind, unit_kind, key_version)
    REFERENCES omi_memory.memory_strategy_assignment_policies
      (account_id, policy_id, policy_digest, work_kind, unit_kind, key_version),
  FOREIGN KEY (
    account_id, authority_strategy_id, authority_execution_contract_digest, work_kind
  ) REFERENCES omi_memory.memory_strategy_definitions (
    account_id, strategy_id, execution_contract_digest, work_kind
  )
);

CREATE TABLE omi_memory.memory_strategy_shadow_assignments (
  account_id text NOT NULL,
  assignment_bundle_id text NOT NULL,
  shadow_ordinal integer NOT NULL CHECK (shadow_ordinal >= 0),
  assignment_id text NOT NULL CHECK (assignment_id ~ '^msa1_[0-9a-f]{64}$'),
  policy_id text NOT NULL,
  strategy_id text NOT NULL,
  execution_contract_digest text NOT NULL
    CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  bucket integer NOT NULL CHECK (bucket BETWEEN 0 AND 9999),
  basis_points integer NOT NULL CHECK (basis_points BETWEEN 0 AND 10000),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, assignment_bundle_id, shadow_ordinal),
  UNIQUE (account_id, assignment_id),
  FOREIGN KEY (account_id, assignment_bundle_id)
    REFERENCES omi_memory.memory_strategy_assignment_bundles
      (account_id, assignment_bundle_id),
  FOREIGN KEY (
    account_id, policy_id, strategy_id, execution_contract_digest, work_kind, basis_points
  )
    REFERENCES omi_memory.memory_strategy_policy_shadows
      (account_id, policy_id, strategy_id, execution_contract_digest, work_kind, basis_points),
  FOREIGN KEY (account_id, strategy_id, execution_contract_digest, work_kind)
    REFERENCES omi_memory.memory_strategy_definitions
      (account_id, strategy_id, execution_contract_digest, work_kind),
  CHECK (bucket < basis_points)
);

ALTER TABLE omi_memory.memory_work_acceptances
  ADD COLUMN assignment_bundle_id text NOT NULL,
  ADD COLUMN assignment_bundle_digest text NOT NULL
    CHECK (assignment_bundle_digest ~ '^[0-9a-f]{64}$'),
  ADD COLUMN authority_assignment_id text NOT NULL,
  ADD COLUMN authority_strategy_id text NOT NULL;

ALTER TABLE omi_memory.memory_work_acceptances
  ADD CONSTRAINT memory_work_acceptances_authority_assignment_fk
  FOREIGN KEY (
    account_id, assignment_bundle_id, assignment_bundle_digest, work_kind,
    authority_assignment_id, authority_strategy_id, execution_contract_digest
  ) REFERENCES omi_memory.memory_strategy_assignment_bundles (
    account_id, assignment_bundle_id, assignment_bundle_digest, work_kind,
    authority_assignment_id, authority_strategy_id, authority_execution_contract_digest
  );

REVOKE ALL ON ALL TABLES IN SCHEMA omi_memory FROM PUBLIC;

-- Deliberately no application, worker, experiment, or migration-runner grant.
-- Shadow assignments are inert metadata and cannot authorize durable work.
