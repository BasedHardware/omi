-- P3 inert sensitive normalized-result staging. A committed stage is immutable
-- and reusable across later leases; every success must reference it exactly.
-- Raw provider output is never stored and no runtime authority is granted.

ALTER TABLE omi_memory.memory_work_acceptances
  ADD CONSTRAINT memory_work_acceptances_result_stage_coordinate_key
  UNIQUE (
    account_id, job_id, accepted_work_digest, work_kind, input_frontier,
    execution_contract_digest
  );

ALTER TABLE omi_memory.memory_work_state_revisions
  ADD CONSTRAINT memory_work_state_revisions_result_producer_coordinate_key
  UNIQUE (
    account_id, job_id, state_digest, state, attempt, lease_fence, worker_id
  );

CREATE TABLE omi_memory.memory_work_staged_results (
  account_id text NOT NULL,
  staged_result_id text NOT NULL
    CHECK (staged_result_id ~ '^mwr1_[0-9a-f]{64}$'),
  job_id text NOT NULL,
  result_version text NOT NULL CHECK (
    result_version = 'durable-memory-work-result-v1'
  ),
  accepted_work_digest text NOT NULL
    CHECK (accepted_work_digest ~ '^[0-9a-f]{64}$'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  input_frontier text NOT NULL CHECK (length(input_frontier) BETWEEN 1 AND 256),
  execution_contract_digest text NOT NULL
    CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  produced_attempt integer NOT NULL CHECK (produced_attempt > 0),
  produced_lease_fence bigint NOT NULL CHECK (produced_lease_fence > 0),
  produced_state_digest text NOT NULL
    CHECK (produced_state_digest ~ '^[0-9a-f]{64}$'),
  produced_state text NOT NULL CHECK (produced_state = 'leased'),
  producer_worker_id text NOT NULL
    CHECK (length(producer_worker_id) BETWEEN 1 AND 256),
  result_contract_version text NOT NULL
    CHECK (length(result_contract_version) BETWEEN 1 AND 256),
  response_digest text NOT NULL CHECK (response_digest ~ '^[0-9a-f]{64}$'),
  normalized_result_digest text NOT NULL
    CHECK (normalized_result_digest ~ '^[0-9a-f]{64}$'),
  normalized_result_json jsonb NOT NULL CHECK (
    jsonb_typeof(normalized_result_json) = 'object'
    AND octet_length(normalized_result_json::text) <= 524288
  ),
  stage_request_digest text NOT NULL
    CHECK (stage_request_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, job_id),
  UNIQUE (account_id, staged_result_id),
  UNIQUE (account_id, job_id, stage_request_digest),
  UNIQUE (
    account_id, job_id, staged_result_id, normalized_result_digest,
    response_digest, work_kind, input_frontier
  ),
  FOREIGN KEY (
    account_id, job_id, accepted_work_digest, work_kind, input_frontier,
    execution_contract_digest
  )
    REFERENCES omi_memory.memory_work_acceptances (
      account_id, job_id, accepted_work_digest, work_kind, input_frontier,
      execution_contract_digest
    ),
  FOREIGN KEY (
    account_id, job_id, produced_state_digest, produced_state,
    produced_attempt, produced_lease_fence, producer_worker_id
  )
    REFERENCES omi_memory.memory_work_state_revisions (
      account_id, job_id, state_digest, state,
      attempt, lease_fence, worker_id
    ),
  CHECK (produced_attempt = produced_lease_fence)
);

ALTER TABLE omi_memory.memory_work_success_results
  ADD COLUMN staged_result_id text,
  ADD COLUMN staged_result_digest text;

ALTER TABLE omi_memory.memory_work_success_results
  ALTER COLUMN staged_result_id SET NOT NULL,
  ALTER COLUMN staged_result_digest SET NOT NULL,
  ADD CONSTRAINT memory_work_success_results_staged_result_digest_check
    CHECK (staged_result_digest ~ '^[0-9a-f]{64}$'),
  ADD CONSTRAINT memory_work_success_results_empty_stage_check
    CHECK (
      result_kind <> 'successful_empty'
      OR result_digest = staged_result_digest
    ),
  ADD CONSTRAINT memory_work_success_results_staged_result_fk
    FOREIGN KEY (
      account_id, job_id, staged_result_id, staged_result_digest,
      response_digest, work_kind, input_frontier
    )
      REFERENCES omi_memory.memory_work_staged_results (
        account_id, job_id, staged_result_id, normalized_result_digest,
        response_digest, work_kind, input_frontier
      );

REVOKE ALL ON omi_memory.memory_work_staged_results FROM PUBLIC;

-- Deliberately no application or worker grant. The normalized JSON is
-- sensitive memory content and is unavailable to product routes and telemetry.
