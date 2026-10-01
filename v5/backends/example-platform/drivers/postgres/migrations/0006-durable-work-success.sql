-- P3 atomic durable-work success linkage. This migration expands the closed
-- graph-origin vocabulary and makes a succeeded work state, its exact graph
-- append receipt (when non-empty), and its success outbox structurally one
-- account-scoped result. It grants no runtime authority.

ALTER TABLE omi_memory.memory_derivation_commits
  DROP CONSTRAINT memory_derivation_commits_non_formation_reason_check;

ALTER TABLE omi_memory.memory_derivation_commits
  ADD CONSTRAINT memory_derivation_commits_non_formation_reason_check
  CHECK (
    non_formation_reason IS NULL
    OR non_formation_reason IN (
      'repair', 'manual_liveness', 'historical_replay',
      'promotion', 'identity_consolidation', 'predicate_alignment'
    )
  );

ALTER TABLE omi_memory.memory_derivation_commits
  ADD COLUMN origin_code text GENERATED ALWAYS AS (
    CASE
      WHEN origin_kind = 'formation' THEN 'formation'
      ELSE non_formation_reason
    END
  ) STORED;

ALTER TABLE omi_memory.memory_derivation_commits
  ADD CONSTRAINT memory_derivation_commits_origin_code_check
  CHECK (origin_code IN (
    'formation', 'repair', 'manual_liveness', 'historical_replay',
    'promotion', 'identity_consolidation', 'predicate_alignment'
  )),
  ADD CONSTRAINT memory_derivation_commits_origin_coordinate_key
  UNIQUE (account_id, commit_id, sequence, origin_code, success_kind);

ALTER TABLE omi_memory.memory_idempotency_receipts
  ADD CONSTRAINT memory_idempotency_receipts_result_coordinate_key
  UNIQUE (account_id, commit_id, request_digest, state);

ALTER TABLE omi_memory.memory_work_acceptances
  ADD CONSTRAINT memory_work_acceptances_kind_coordinate_key
  UNIQUE (account_id, job_id, work_kind, input_frontier);

ALTER TABLE omi_memory.memory_work_state_revisions
  ADD CONSTRAINT memory_work_state_revisions_success_coordinate_key
  UNIQUE (
    account_id, job_id, state_revision, state_digest, state,
    result_kind, response_digest, result_digest
  );

ALTER TABLE omi_memory.memory_formation_outcomes
  ADD CONSTRAINT memory_formation_outcomes_success_coordinate_key
  UNIQUE (
    account_id, formation_work_id, commit_id, response_digest, input_frontier
  );

CREATE TABLE omi_memory.memory_work_success_results (
  account_id text NOT NULL,
  job_id text NOT NULL,
  terminal_state_revision bigint NOT NULL CHECK (terminal_state_revision > 0),
  terminal_state_digest text NOT NULL CHECK (terminal_state_digest ~ '^[0-9a-f]{64}$'),
  terminal_state text NOT NULL CHECK (terminal_state = 'succeeded'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  input_frontier text NOT NULL CHECK (length(input_frontier) BETWEEN 1 AND 256),
  result_kind text NOT NULL CHECK (result_kind IN (
    'successful', 'successful_empty'
  )),
  response_digest text NOT NULL CHECK (response_digest ~ '^[0-9a-f]{64}$'),
  result_digest text NOT NULL CHECK (result_digest ~ '^[0-9a-f]{64}$'),
  origin_code text CHECK (origin_code IS NULL OR origin_code IN (
    'formation', 'promotion', 'identity_consolidation', 'predicate_alignment'
  )),
  graph_commit_id text,
  graph_commit_sequence bigint CHECK (
    graph_commit_sequence IS NULL OR graph_commit_sequence > 0
  ),
  graph_success_kind text CHECK (
    graph_success_kind IS NULL OR graph_success_kind = 'success'
  ),
  formation_work_id text GENERATED ALWAYS AS (
    CASE WHEN work_kind = 'formation' THEN job_id ELSE NULL END
  ) STORED,
  append_receipt_state text CHECK (
    append_receipt_state IS NULL OR append_receipt_state = 'finalized'
  ),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, job_id),
  UNIQUE (account_id, job_id, terminal_state_revision, result_digest),
  FOREIGN KEY (account_id, job_id, work_kind, input_frontier)
    REFERENCES omi_memory.memory_work_acceptances
      (account_id, job_id, work_kind, input_frontier),
  FOREIGN KEY (
    account_id, job_id, terminal_state_revision, terminal_state_digest,
    terminal_state, result_kind, response_digest, result_digest
  )
    REFERENCES omi_memory.memory_work_state_revisions (
      account_id, job_id, state_revision, state_digest,
      state, result_kind, response_digest, result_digest
    ),
  FOREIGN KEY (
    account_id, graph_commit_id, graph_commit_sequence, origin_code,
    graph_success_kind
  )
    REFERENCES omi_memory.memory_derivation_commits
      (account_id, commit_id, sequence, origin_code, success_kind),
  FOREIGN KEY (account_id, graph_commit_id, formation_work_id)
    REFERENCES omi_memory.memory_derivation_commits
      (account_id, commit_id, formation_work_id),
  FOREIGN KEY (
    account_id, formation_work_id, graph_commit_id, response_digest,
    input_frontier
  )
    REFERENCES omi_memory.memory_formation_outcomes (
      account_id, formation_work_id, commit_id, response_digest,
      input_frontier
    ),
  FOREIGN KEY (
    account_id, graph_commit_id, result_digest, append_receipt_state
  )
    REFERENCES omi_memory.memory_idempotency_receipts
      (account_id, commit_id, request_digest, state),
  CHECK (
    (result_kind = 'successful_empty'
      AND origin_code IS NULL
      AND graph_commit_id IS NULL
      AND graph_commit_sequence IS NULL
      AND graph_success_kind IS NULL
      AND append_receipt_state IS NULL)
    OR (result_kind = 'successful'
      AND graph_commit_id IS NOT NULL
      AND graph_commit_sequence IS NOT NULL
      AND graph_success_kind = 'success'
      AND append_receipt_state = 'finalized'
      AND (
        (work_kind = 'formation' AND origin_code = 'formation')
        OR (work_kind = 'promotion' AND origin_code = 'promotion')
        OR (work_kind = 'identity_cluster'
          AND origin_code = 'identity_consolidation')
        OR (work_kind = 'predicate_batch'
          AND origin_code = 'predicate_alignment')
      ))
  )
);

ALTER TABLE omi_memory.memory_work_outbox_events
  ADD CONSTRAINT memory_work_outbox_events_success_result_fk
  FOREIGN KEY (
    account_id, job_id, terminal_state_revision, result_digest
  )
    REFERENCES omi_memory.memory_work_success_results
      (account_id, job_id, terminal_state_revision, result_digest);

REVOKE ALL ON omi_memory.memory_work_success_results FROM PUBLIC;

-- Deliberately no application or worker grant. Real PostgreSQL transaction,
-- crash-window, role, and replay qualification remains a separate gate.
