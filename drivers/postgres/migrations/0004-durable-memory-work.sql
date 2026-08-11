-- P3 inert durable-work persistence: accepted work, exact input manifests,
-- append-only fenced state revisions, one current head, and content-safe
-- terminal outbox coordinates. No worker role, function, or runtime is wired.

CREATE TABLE omi_memory.memory_work_acceptances (
  account_id text NOT NULL,
  job_id text NOT NULL CHECK (length(job_id) BETWEEN 1 AND 256),
  work_version text NOT NULL CHECK (work_version = 'durable-memory-work-v1'),
  accepted_work_digest text NOT NULL CHECK (accepted_work_digest ~ '^[0-9a-f]{64}$'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  accepted_control_revision bigint NOT NULL CHECK (accepted_control_revision >= 0),
  lifecycle_state text NOT NULL CHECK (lifecycle_state = 'active'),
  deletion_epoch bigint CHECK (deletion_epoch IS NULL),
  account_generation text NOT NULL CHECK (account_generation = 'new'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  input_frontier text NOT NULL CHECK (length(input_frontier) BETWEEN 1 AND 256),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  execution_contract_digest text NOT NULL
    CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  accepted_at_event_time bigint NOT NULL CHECK (accepted_at_event_time >= 0),
  max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 100),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, job_id),
  UNIQUE (account_id, job_id, accepted_work_digest),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id),
  FOREIGN KEY (account_id, accepted_control_revision, account_epoch)
    REFERENCES omi_memory.account_control_revisions
      (account_id, control_revision, account_epoch)
);

CREATE TABLE omi_memory.memory_work_input_manifest (
  account_id text NOT NULL,
  job_id text NOT NULL,
  input_ordinal integer NOT NULL CHECK (input_ordinal >= 0),
  input_kind text NOT NULL CHECK (input_kind IN (
    'event_revision', 'evidence_revision', 'claim_revision', 'mention_revision',
    'entity_revision', 'predicate_revision', 'identity_revision',
    'identity_authorization_revision', 'graph_frontier'
  )),
  input_ref text NOT NULL CHECK (length(input_ref) BETWEEN 1 AND 256),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, job_id, input_ordinal),
  UNIQUE (account_id, job_id, input_kind, input_ref),
  FOREIGN KEY (account_id, job_id)
    REFERENCES omi_memory.memory_work_acceptances (account_id, job_id)
);

CREATE TABLE omi_memory.memory_work_state_revisions (
  account_id text NOT NULL,
  job_id text NOT NULL,
  state_revision bigint NOT NULL CHECK (state_revision >= 0),
  state_digest text NOT NULL CHECK (state_digest ~ '^[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN (
    'pending', 'leased', 'retryable_failed', 'succeeded', 'dead_letter'
  )),
  attempt integer NOT NULL CHECK (attempt >= 0),
  lease_fence bigint NOT NULL CHECK (lease_fence >= 0),
  worker_id text CHECK (worker_id IS NULL OR length(worker_id) BETWEEN 1 AND 256),
  leased_at_event_time bigint CHECK (leased_at_event_time IS NULL OR leased_at_event_time >= 0),
  lease_expires_at_event_time bigint
    CHECK (lease_expires_at_event_time IS NULL OR lease_expires_at_event_time > 0),
  error_code text CHECK (error_code IS NULL OR error_code IN (
    'model_timeout', 'model_rate_limited', 'model_response_invalid',
    'prompt_budget_exceeded', 'dependency_unavailable',
    'serialization_retryable', 'worker_lost'
  )),
  failed_at_event_time bigint CHECK (failed_at_event_time IS NULL OR failed_at_event_time >= 0),
  next_eligible_event_time bigint
    CHECK (next_eligible_event_time IS NULL OR next_eligible_event_time >= 0),
  result_kind text CHECK (result_kind IS NULL OR result_kind IN (
    'successful', 'successful_empty'
  )),
  response_digest text CHECK (response_digest IS NULL OR response_digest ~ '^[0-9a-f]{64}$'),
  result_digest text CHECK (result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'),
  succeeded_at_event_time bigint
    CHECK (succeeded_at_event_time IS NULL OR succeeded_at_event_time >= 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, job_id, state_revision),
  UNIQUE (account_id, job_id, state_revision, state_digest),
  UNIQUE (account_id, job_id, state_revision, state_digest, state),
  FOREIGN KEY (account_id, job_id)
    REFERENCES omi_memory.memory_work_acceptances (account_id, job_id),
  CHECK (lease_fence = attempt),
  CHECK (
    (state = 'pending'
      AND attempt = 0 AND lease_fence = 0
      AND worker_id IS NULL
      AND leased_at_event_time IS NULL AND lease_expires_at_event_time IS NULL
      AND error_code IS NULL AND failed_at_event_time IS NULL
      AND next_eligible_event_time IS NULL
      AND result_kind IS NULL AND response_digest IS NULL AND result_digest IS NULL
      AND succeeded_at_event_time IS NULL)
    OR (state = 'leased'
      AND attempt > 0
      AND worker_id IS NOT NULL
      AND leased_at_event_time IS NOT NULL AND lease_expires_at_event_time IS NOT NULL
      AND lease_expires_at_event_time > leased_at_event_time
      AND error_code IS NULL AND failed_at_event_time IS NULL
      AND next_eligible_event_time IS NULL
      AND result_kind IS NULL AND response_digest IS NULL AND result_digest IS NULL
      AND succeeded_at_event_time IS NULL)
    OR (state = 'retryable_failed'
      AND attempt > 0
      AND worker_id IS NULL
      AND leased_at_event_time IS NULL AND lease_expires_at_event_time IS NULL
      AND error_code IS NOT NULL AND failed_at_event_time IS NOT NULL
      AND next_eligible_event_time IS NOT NULL
      AND next_eligible_event_time > failed_at_event_time
      AND result_kind IS NULL AND response_digest IS NULL AND result_digest IS NULL
      AND succeeded_at_event_time IS NULL)
    OR (state = 'succeeded'
      AND attempt > 0
      AND worker_id IS NULL
      AND leased_at_event_time IS NULL AND lease_expires_at_event_time IS NULL
      AND error_code IS NULL AND failed_at_event_time IS NULL
      AND next_eligible_event_time IS NULL
      AND result_kind IS NOT NULL AND response_digest IS NOT NULL AND result_digest IS NOT NULL
      AND succeeded_at_event_time IS NOT NULL)
    OR (state = 'dead_letter'
      AND attempt > 0
      AND worker_id IS NULL
      AND leased_at_event_time IS NULL AND lease_expires_at_event_time IS NULL
      AND error_code IS NOT NULL AND failed_at_event_time IS NOT NULL
      AND next_eligible_event_time IS NULL
      AND result_kind IS NULL AND response_digest IS NULL AND result_digest IS NULL
      AND succeeded_at_event_time IS NULL)
  )
);

CREATE TABLE omi_memory.memory_work_heads (
  account_id text NOT NULL,
  job_id text NOT NULL,
  state_revision bigint NOT NULL CHECK (state_revision >= 0),
  state_digest text NOT NULL CHECK (state_digest ~ '^[0-9a-f]{64}$'),
  updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, job_id),
  FOREIGN KEY (account_id, job_id, state_revision, state_digest)
    REFERENCES omi_memory.memory_work_state_revisions
      (account_id, job_id, state_revision, state_digest)
);

CREATE TABLE omi_memory.memory_work_outbox_events (
  account_id text NOT NULL,
  outbox_id text NOT NULL,
  job_id text NOT NULL,
  terminal_state_revision bigint NOT NULL CHECK (terminal_state_revision > 0),
  terminal_state_digest text NOT NULL CHECK (terminal_state_digest ~ '^[0-9a-f]{64}$'),
  terminal_state text NOT NULL CHECK (terminal_state IN ('succeeded', 'dead_letter')),
  event_kind text NOT NULL CHECK (event_kind IN (
    'memory_work_succeeded', 'memory_work_dead_letter'
  )),
  result_digest text CHECK (result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'),
  created_at_event_time bigint NOT NULL CHECK (created_at_event_time >= 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, outbox_id),
  UNIQUE (account_id, job_id, terminal_state_revision, event_kind),
  FOREIGN KEY (
    account_id, job_id, terminal_state_revision, terminal_state_digest, terminal_state
  )
    REFERENCES omi_memory.memory_work_state_revisions
      (account_id, job_id, state_revision, state_digest, state),
  CHECK (
    (event_kind = 'memory_work_succeeded'
      AND terminal_state = 'succeeded' AND result_digest IS NOT NULL)
    OR (event_kind = 'memory_work_dead_letter'
      AND terminal_state = 'dead_letter' AND result_digest IS NULL)
  )
);

REVOKE ALL ON ALL TABLES IN SCHEMA omi_memory FROM PUBLIC;

-- Deliberately no application grant. A later P3 migration may grant narrowly
-- named operations only after the worker identity and real PostgreSQL adapter
-- are ratified and the atomic lease/result/outbox gate passes.
