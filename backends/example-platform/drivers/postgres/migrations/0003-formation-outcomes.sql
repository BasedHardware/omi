-- P2.1 expand-only PostgreSQL authority: total formation outcomes and the
-- ADR-014 terminal-deletion export contract. No worker/outbox is introduced.

CREATE TABLE omi_memory.memory_formation_outcomes (
  account_id text NOT NULL,
  formation_work_id text NOT NULL CHECK (formation_work_id <> ''),
  input_frontier text NOT NULL CHECK (input_frontier <> ''),
  response_digest text NOT NULL CHECK (response_digest ~ '^[0-9a-f]{64}$'),
  contract_version text NOT NULL CHECK (contract_version <> ''),
  candidate_count integer NOT NULL CHECK (candidate_count >= 0),
  strategy_coordinates jsonb NOT NULL CHECK (jsonb_typeof(strategy_coordinates) = 'object'),
  candidate_manifest_digest text NOT NULL CHECK (candidate_manifest_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  commit_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, formation_work_id),
  UNIQUE (account_id, commit_id),
  UNIQUE (account_id, commit_id, formation_work_id),
  FOREIGN KEY (account_id, commit_id, formation_work_id)
    REFERENCES omi_memory.memory_derivation_commits
      (account_id, commit_id, formation_work_id)
);

CREATE TABLE omi_memory.memory_formation_extraction_outcomes (
  account_id text NOT NULL,
  formation_work_id text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  candidate_ref text NOT NULL,
  outcome_kind text NOT NULL CHECK (outcome_kind IN ('accepted', 'dropped')),
  claim_revision_id text,
  repair_codes jsonb,
  reason_code text,
  reason_detail text,
  PRIMARY KEY (account_id, formation_work_id, ordinal),
  UNIQUE (account_id, formation_work_id, candidate_ref),
  FOREIGN KEY (account_id, formation_work_id)
    REFERENCES omi_memory.memory_formation_outcomes (account_id, formation_work_id),
  FOREIGN KEY (account_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  CHECK (
    (outcome_kind = 'accepted'
      AND claim_revision_id IS NOT NULL
      AND repair_codes IS NOT NULL
      AND jsonb_typeof(repair_codes) = 'array'
      AND reason_code IS NULL
      AND reason_detail IS NULL)
    OR (outcome_kind = 'dropped'
      AND claim_revision_id IS NULL
      AND repair_codes IS NULL
      AND reason_code IS NOT NULL)
  )
);

CREATE TABLE omi_memory.memory_formation_extraction_evidence (
  account_id text NOT NULL,
  formation_work_id text NOT NULL,
  extraction_ordinal integer NOT NULL CHECK (extraction_ordinal >= 0),
  evidence_id text NOT NULL,
  PRIMARY KEY (account_id, formation_work_id, extraction_ordinal, evidence_id),
  FOREIGN KEY (account_id, formation_work_id, extraction_ordinal)
    REFERENCES omi_memory.memory_formation_extraction_outcomes
      (account_id, formation_work_id, ordinal),
  FOREIGN KEY (account_id, evidence_id)
    REFERENCES omi_memory.memory_evidence_identities (account_id, evidence_id)
);

CREATE TABLE omi_memory.memory_formation_placement_outcomes (
  account_id text NOT NULL,
  formation_work_id text NOT NULL,
  input_provisional_revision_id text NOT NULL,
  outcome_kind text NOT NULL CHECK (outcome_kind IN (
    'admitted', 'abstained', 'retryable_error', 'dead_letter'
  )),
  canonical_claim_revision_id text,
  boundary_decision text CHECK (boundary_decision IS NULL OR boundary_decision IN ('accept_ltm', 'abstain')),
  scope_locality text CHECK (scope_locality IS NULL OR scope_locality IN ('durable', 'source_local')),
  reason_code text,
  reconsideration_trigger text,
  attempt integer CHECK (attempt IS NULL OR attempt > 0),
  attempts integer CHECK (attempts IS NULL OR attempts > 0),
  max_attempts integer CHECK (max_attempts IS NULL OR max_attempts > 0),
  error_code text,
  next_eligible_at text,
  PRIMARY KEY (account_id, formation_work_id, input_provisional_revision_id),
  FOREIGN KEY (account_id, formation_work_id)
    REFERENCES omi_memory.memory_formation_outcomes (account_id, formation_work_id),
  FOREIGN KEY (account_id, input_provisional_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, canonical_claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  CHECK (
    (outcome_kind = 'admitted'
      AND canonical_claim_revision_id IS NOT NULL
      AND boundary_decision = 'accept_ltm'
      AND scope_locality IS NOT NULL
      AND reason_code IS NULL AND reconsideration_trigger IS NULL
      AND attempt IS NULL AND attempts IS NULL AND max_attempts IS NULL
      AND error_code IS NULL AND next_eligible_at IS NULL)
    OR (outcome_kind = 'abstained'
      AND canonical_claim_revision_id IS NULL
      AND boundary_decision = 'abstain'
      AND scope_locality IS NULL
      AND reason_code IS NOT NULL
      AND attempt IS NULL AND attempts IS NULL AND max_attempts IS NULL
      AND error_code IS NULL AND next_eligible_at IS NULL)
    OR (outcome_kind = 'retryable_error'
      AND canonical_claim_revision_id IS NULL
      AND boundary_decision IS NULL AND scope_locality IS NULL
      AND reason_code IS NULL AND reconsideration_trigger IS NULL
      AND attempt IS NOT NULL AND max_attempts IS NOT NULL AND attempt < max_attempts
      AND attempts IS NULL AND error_code IS NOT NULL)
    OR (outcome_kind = 'dead_letter'
      AND canonical_claim_revision_id IS NULL
      AND boundary_decision IS NULL AND scope_locality IS NULL
      AND reason_code IS NULL AND reconsideration_trigger IS NULL
      AND attempt IS NULL AND attempts IS NOT NULL AND max_attempts IS NOT NULL
      AND attempts >= max_attempts AND error_code IS NOT NULL
      AND next_eligible_at IS NULL)
  )
);

CREATE TABLE omi_memory.account_terminal_deletion_exports (
  account_id text NOT NULL,
  deletion_epoch bigint NOT NULL CHECK (deletion_epoch >= 0),
  export_contract_version text NOT NULL CHECK (export_contract_version <> ''),
  transitioned_at timestamptz NOT NULL,
  account_generation text NOT NULL CHECK (account_generation IN (
    'legacy', 'migrating', 'new', 'rolled_back_stranded'
  )),
  terminal_lifecycle_state text NOT NULL CHECK (terminal_lifecycle_state = 'deleted'),
  stranded_data_present boolean NOT NULL,
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, deletion_epoch),
  FOREIGN KEY (
    account_id, control_revision, deletion_epoch, account_generation,
    terminal_lifecycle_state
  ) REFERENCES omi_memory.account_control_revisions (
    account_id, control_revision, deletion_epoch, account_generation,
    lifecycle_state
  )
);

ALTER TABLE omi_memory.memory_derivation_commits
  ADD CONSTRAINT memory_derivation_commits_formation_outcome_fk
  FOREIGN KEY (account_id, commit_id, formation_work_id)
  REFERENCES omi_memory.memory_formation_outcomes
    (account_id, commit_id, formation_work_id)
  DEFERRABLE INITIALLY DEFERRED;

REVOKE ALL ON ALL TABLES IN SCHEMA omi_memory FROM PUBLIC;

GRANT SELECT, INSERT ON omi_memory.memory_formation_outcomes TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_formation_extraction_outcomes TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_formation_extraction_evidence TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_formation_placement_outcomes TO omi_platform_application;
GRANT SELECT ON omi_memory.account_terminal_deletion_exports TO omi_platform_application;
