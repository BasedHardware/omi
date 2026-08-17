-- P2.1 expand-only PostgreSQL authority: append-only memory ledger.

CREATE TABLE omi_memory.memory_derivation_attempts (
  account_id text NOT NULL,
  attempt_id text NOT NULL CHECK (attempt_id <> ''),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  input_version_digest text NOT NULL CHECK (input_version_digest ~ '^[0-9a-f]{64}$'),
  output_digest text NOT NULL CHECK (output_digest ~ '^[0-9a-f]{64}$'),
  success_kind text NOT NULL CHECK (success_kind IN ('success', 'successful_empty')),
  versions jsonb NOT NULL CHECK (jsonb_typeof(versions) = 'object'),
  record_json jsonb NOT NULL CHECK (jsonb_typeof(record_json) = 'object'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, attempt_id),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_derivation_commits (
  account_id text NOT NULL,
  commit_id text NOT NULL CHECK (commit_id <> ''),
  attempt_id text NOT NULL,
  parent_commit_id text,
  sequence bigint NOT NULL CHECK (sequence > 0),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  input_version_digest text NOT NULL CHECK (input_version_digest ~ '^[0-9a-f]{64}$'),
  output_digest text NOT NULL CHECK (output_digest ~ '^[0-9a-f]{64}$'),
  success_kind text NOT NULL CHECK (success_kind IN ('success', 'successful_empty')),
  origin_kind text NOT NULL CHECK (origin_kind IN ('formation', 'non_formation')),
  formation_work_id text,
  non_formation_reason text CHECK (
    non_formation_reason IS NULL
    OR non_formation_reason IN ('repair', 'manual_liveness', 'historical_replay')
  ),
  record_json jsonb NOT NULL CHECK (jsonb_typeof(record_json) = 'object'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, commit_id),
  UNIQUE (account_id, sequence),
  UNIQUE (account_id, commit_id, sequence),
  UNIQUE (account_id, commit_id, formation_work_id),
  FOREIGN KEY (account_id, attempt_id)
    REFERENCES omi_memory.memory_derivation_attempts (account_id, attempt_id),
  FOREIGN KEY (account_id, parent_commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id),
  CHECK (
    (origin_kind = 'formation'
      AND formation_work_id IS NOT NULL
      AND non_formation_reason IS NULL)
    OR (origin_kind = 'non_formation'
      AND formation_work_id IS NULL
      AND non_formation_reason IS NOT NULL)
  )
);

CREATE TABLE omi_memory.memory_graph_heads (
  account_id text PRIMARY KEY,
  commit_id text,
  sequence bigint NOT NULL DEFAULT 0 CHECK (sequence >= 0),
  updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id),
  FOREIGN KEY (account_id, commit_id, sequence)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id, sequence),
  CHECK ((commit_id IS NULL AND sequence = 0) OR (commit_id IS NOT NULL AND sequence > 0))
);

INSERT INTO omi_memory.memory_graph_heads (account_id)
SELECT account_id FROM omi_memory.platform_accounts
ON CONFLICT (account_id) DO NOTHING;

CREATE FUNCTION omi_memory.seed_memory_graph_head()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, omi_memory
AS $function$
BEGIN
  INSERT INTO omi_memory.memory_graph_heads (account_id)
  VALUES (NEW.account_id);
  RETURN NEW;
END;
$function$;

CREATE TRIGGER platform_account_seeds_memory_graph_head
AFTER INSERT ON omi_memory.platform_accounts
FOR EACH ROW EXECUTE FUNCTION omi_memory.seed_memory_graph_head();

CREATE TABLE omi_memory.memory_idempotency_receipts (
  account_id text NOT NULL,
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  idempotency_key text NOT NULL CHECK (idempotency_key <> ''),
  request_digest text NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN ('reserved', 'finalized')),
  commit_id text,
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  finalized_at timestamptz,
  PRIMARY KEY (account_id, account_epoch, idempotency_key),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id),
  FOREIGN KEY (account_id, commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id),
  CHECK (
    (state = 'reserved' AND commit_id IS NULL AND finalized_at IS NULL)
    OR (state = 'finalized' AND commit_id IS NOT NULL AND finalized_at IS NOT NULL)
  )
);

CREATE TABLE omi_memory.memory_derivation_inputs (
  account_id text NOT NULL,
  commit_id text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  input_ref text NOT NULL CHECK (input_ref <> ''),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, commit_id, ordinal),
  UNIQUE (account_id, commit_id, input_ref),
  FOREIGN KEY (account_id, commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id)
);

CREATE TABLE omi_memory.memory_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL CHECK (revision_id <> ''),
  revision_kind text NOT NULL CHECK (revision_kind IN (
    'claim', 'entity', 'predicate', 'predicate_assertion', 'identity',
    'event', 'evidence', 'mention', 'identity_authorization',
    'coreference_support'
  )),
  commit_id text NOT NULL,
  schema_version text NOT NULL CHECK (schema_version <> ''),
  content_json jsonb NOT NULL CHECK (jsonb_typeof(content_json) = 'object'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, revision_id),
  FOREIGN KEY (account_id, commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id)
);

CREATE TABLE omi_memory.memory_event_identities (
  account_id text NOT NULL,
  event_id text NOT NULL,
  PRIMARY KEY (account_id, event_id),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_event_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  event_id text NOT NULL,
  event_revision_id text NOT NULL,
  PRIMARY KEY (account_id, revision_id),
  UNIQUE (account_id, event_revision_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, event_id)
    REFERENCES omi_memory.memory_event_identities (account_id, event_id)
);

CREATE TABLE omi_memory.memory_evidence_identities (
  account_id text NOT NULL,
  evidence_id text NOT NULL,
  PRIMARY KEY (account_id, evidence_id),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_evidence_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  evidence_id text NOT NULL,
  event_revision_id text NOT NULL,
  PRIMARY KEY (account_id, revision_id),
  UNIQUE (account_id, revision_id, event_revision_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, evidence_id)
    REFERENCES omi_memory.memory_evidence_identities (account_id, evidence_id),
  FOREIGN KEY (account_id, event_revision_id)
    REFERENCES omi_memory.memory_event_revisions (account_id, event_revision_id)
);

CREATE TABLE omi_memory.memory_claim_lineages (
  account_id text NOT NULL,
  claim_lineage_id text NOT NULL,
  PRIMARY KEY (account_id, claim_lineage_id),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_claim_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  claim_lineage_id text NOT NULL,
  claim_revision_id text NOT NULL,
  canonical_claim_id text,
  lifecycle text NOT NULL CHECK (lifecycle IN ('provisional', 'canonical')),
  placement_status text NOT NULL CHECK (placement_status IN (
    'canonical', 'consumed', 'provisional_unresolved_subject', 'provisional_abstained'
  )),
  PRIMARY KEY (account_id, revision_id),
  UNIQUE (account_id, claim_revision_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, claim_lineage_id)
    REFERENCES omi_memory.memory_claim_lineages (account_id, claim_lineage_id),
  CHECK ((lifecycle = 'canonical') = (canonical_claim_id IS NOT NULL)),
  CHECK ((placement_status = 'canonical') = (lifecycle = 'canonical'))
);

CREATE TABLE omi_memory.memory_claim_evidence_refs (
  account_id text NOT NULL,
  claim_revision_id text NOT NULL,
  evidence_ordinal integer NOT NULL CHECK (evidence_ordinal >= 0),
  evidence_id text NOT NULL,
  PRIMARY KEY (account_id, claim_revision_id, evidence_ordinal),
  UNIQUE (account_id, claim_revision_id, evidence_id),
  FOREIGN KEY (account_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, evidence_id)
    REFERENCES omi_memory.memory_evidence_identities (account_id, evidence_id)
);

CREATE TABLE omi_memory.memory_claim_source_provisionals (
  account_id text NOT NULL,
  canonical_claim_revision_id text NOT NULL,
  source_ordinal integer NOT NULL CHECK (source_ordinal >= 0),
  source_provisional_revision_id text NOT NULL,
  PRIMARY KEY (account_id, canonical_claim_revision_id, source_ordinal),
  UNIQUE (
    account_id, canonical_claim_revision_id, source_provisional_revision_id
  ),
  FOREIGN KEY (account_id, canonical_claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, source_provisional_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id)
);

CREATE TABLE omi_memory.memory_claim_supersessions (
  account_id text NOT NULL,
  claim_revision_id text NOT NULL,
  supersession_ordinal integer NOT NULL CHECK (supersession_ordinal >= 0),
  superseded_claim_revision_id text NOT NULL,
  PRIMARY KEY (account_id, claim_revision_id, supersession_ordinal),
  UNIQUE (account_id, claim_revision_id, superseded_claim_revision_id),
  FOREIGN KEY (account_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, superseded_claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  CHECK (claim_revision_id <> superseded_claim_revision_id)
);

CREATE TABLE omi_memory.memory_entity_identities (
  account_id text NOT NULL,
  entity_id text NOT NULL,
  PRIMARY KEY (account_id, entity_id),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_entity_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  entity_id text NOT NULL,
  entity_revision_id text NOT NULL,
  PRIMARY KEY (account_id, revision_id),
  UNIQUE (account_id, entity_revision_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, entity_id)
    REFERENCES omi_memory.memory_entity_identities (account_id, entity_id)
);

CREATE TABLE omi_memory.memory_predicate_identities (
  account_id text NOT NULL,
  predicate_id text NOT NULL,
  identity_version text NOT NULL CHECK (identity_version IN ('name-slots-v1', 'name-v2')),
  PRIMARY KEY (account_id, predicate_id),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_predicate_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  predicate_id text NOT NULL,
  predicate_revision_id text NOT NULL,
  PRIMARY KEY (account_id, revision_id),
  UNIQUE (account_id, predicate_revision_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, predicate_id)
    REFERENCES omi_memory.memory_predicate_identities (account_id, predicate_id)
);

CREATE TABLE omi_memory.memory_predicate_assertion_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  assertion_id text NOT NULL,
  predicate_id text NOT NULL,
  target_predicate_id text NOT NULL,
  supersedes_assertion_id text,
  PRIMARY KEY (account_id, revision_id),
  UNIQUE (account_id, assertion_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, predicate_id)
    REFERENCES omi_memory.memory_predicate_identities (account_id, predicate_id),
  FOREIGN KEY (account_id, target_predicate_id)
    REFERENCES omi_memory.memory_predicate_identities (account_id, predicate_id),
  FOREIGN KEY (account_id, supersedes_assertion_id)
    REFERENCES omi_memory.memory_predicate_assertion_revisions
      (account_id, assertion_id),
  CHECK (supersedes_assertion_id IS NULL OR supersedes_assertion_id <> assertion_id)
);

CREATE TABLE omi_memory.memory_claim_predicate_refs (
  account_id text NOT NULL,
  claim_revision_id text NOT NULL,
  predicate_id text NOT NULL,
  PRIMARY KEY (account_id, claim_revision_id),
  FOREIGN KEY (account_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, predicate_id)
    REFERENCES omi_memory.memory_predicate_identities (account_id, predicate_id)
);

CREATE TABLE omi_memory.memory_identity_authorization_identities (
  account_id text NOT NULL,
  authorization_id text NOT NULL,
  PRIMARY KEY (account_id, authorization_id),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_identity_authorization_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  authorization_id text NOT NULL,
  lifecycle text NOT NULL CHECK (lifecycle IN ('active', 'superseded', 'revoked')),
  superseded_by_authorization_id text,
  PRIMARY KEY (account_id, revision_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, authorization_id)
    REFERENCES omi_memory.memory_identity_authorization_identities
      (account_id, authorization_id),
  FOREIGN KEY (account_id, superseded_by_authorization_id)
    REFERENCES omi_memory.memory_identity_authorization_identities
      (account_id, authorization_id),
  CHECK (
    superseded_by_authorization_id IS NULL
    OR superseded_by_authorization_id <> authorization_id
  )
);

CREATE TABLE omi_memory.memory_identity_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  constraint_id text NOT NULL,
  authorization_revision_id text NOT NULL,
  PRIMARY KEY (account_id, revision_id),
  UNIQUE (account_id, constraint_id, revision_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, authorization_revision_id)
    REFERENCES omi_memory.memory_identity_authorization_revisions
      (account_id, revision_id)
);

-- Only entity endpoints have a P2.1 authority table. Source-identity endpoints
-- remain in strict revision JSON and are validated by the repository boundary.
CREATE TABLE omi_memory.memory_identity_authorization_entity_endpoints (
  account_id text NOT NULL,
  authorization_revision_id text NOT NULL,
  endpoint_ordinal integer NOT NULL CHECK (endpoint_ordinal IN (0, 1)),
  entity_id text NOT NULL,
  PRIMARY KEY (account_id, authorization_revision_id, endpoint_ordinal),
  FOREIGN KEY (account_id, authorization_revision_id)
    REFERENCES omi_memory.memory_identity_authorization_revisions
      (account_id, revision_id),
  FOREIGN KEY (account_id, entity_id)
    REFERENCES omi_memory.memory_entity_identities (account_id, entity_id)
);

CREATE TABLE omi_memory.memory_identity_constraint_entity_endpoints (
  account_id text NOT NULL,
  identity_revision_id text NOT NULL,
  endpoint_ordinal integer NOT NULL CHECK (endpoint_ordinal IN (0, 1)),
  entity_id text NOT NULL,
  PRIMARY KEY (account_id, identity_revision_id, endpoint_ordinal),
  FOREIGN KEY (account_id, identity_revision_id)
    REFERENCES omi_memory.memory_identity_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, entity_id)
    REFERENCES omi_memory.memory_entity_identities (account_id, entity_id)
);

CREATE TABLE omi_memory.memory_mention_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  mention_id text NOT NULL,
  claim_revision_id text NOT NULL,
  evidence_id text NOT NULL,
  entity_id text,
  PRIMARY KEY (account_id, revision_id),
  UNIQUE (account_id, mention_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, evidence_id)
    REFERENCES omi_memory.memory_evidence_identities (account_id, evidence_id),
  FOREIGN KEY (account_id, entity_id)
    REFERENCES omi_memory.memory_entity_identities (account_id, entity_id)
);

CREATE TABLE omi_memory.memory_coreference_support_revisions (
  account_id text NOT NULL,
  revision_id text NOT NULL,
  coreference_support_id text NOT NULL,
  antecedent_mention_id text NOT NULL,
  anaphor_mention_id text NOT NULL,
  PRIMARY KEY (account_id, revision_id),
  UNIQUE (account_id, coreference_support_id),
  FOREIGN KEY (account_id, revision_id)
    REFERENCES omi_memory.memory_revisions (account_id, revision_id),
  FOREIGN KEY (account_id, antecedent_mention_id)
    REFERENCES omi_memory.memory_mention_revisions (account_id, mention_id),
  FOREIGN KEY (account_id, anaphor_mention_id)
    REFERENCES omi_memory.memory_mention_revisions (account_id, mention_id)
);

CREATE TABLE omi_memory.memory_coreference_support_evidence_refs (
  account_id text NOT NULL,
  coreference_support_revision_id text NOT NULL,
  evidence_ordinal integer NOT NULL CHECK (evidence_ordinal >= 0),
  evidence_id text NOT NULL,
  PRIMARY KEY (
    account_id, coreference_support_revision_id, evidence_ordinal
  ),
  UNIQUE (account_id, coreference_support_revision_id, evidence_id),
  FOREIGN KEY (account_id, coreference_support_revision_id)
    REFERENCES omi_memory.memory_coreference_support_revisions
      (account_id, revision_id),
  FOREIGN KEY (account_id, evidence_id)
    REFERENCES omi_memory.memory_evidence_identities (account_id, evidence_id)
);

-- Coreference lineage_refs, candidate input_refs, and other external source
-- coordinates have no P2.1 relational authority target. They remain in strict,
-- checksummed payloads and cannot mint tenant or identity authority.

CREATE TABLE omi_memory.memory_identity_support (
  account_id text NOT NULL,
  support_ref text NOT NULL,
  claim_revision_id text NOT NULL,
  evidence_revision_id text NOT NULL,
  event_revision_id text NOT NULL,
  source_independence_key text NOT NULL CHECK (source_independence_key <> ''),
  support_origin text NOT NULL CHECK (support_origin IN ('suggested', 'independent')),
  commit_id text NOT NULL,
  schema_version text NOT NULL CHECK (schema_version <> ''),
  content_json jsonb NOT NULL CHECK (jsonb_typeof(content_json) = 'object'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, support_ref),
  FOREIGN KEY (account_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, evidence_revision_id, event_revision_id)
    REFERENCES omi_memory.memory_evidence_revisions
      (account_id, revision_id, event_revision_id),
  FOREIGN KEY (account_id, commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id)
);

CREATE TABLE omi_memory.memory_identity_authorization_support (
  account_id text NOT NULL,
  authorization_revision_id text NOT NULL,
  support_ordinal integer NOT NULL CHECK (support_ordinal >= 0),
  support_ref text NOT NULL,
  PRIMARY KEY (account_id, authorization_revision_id, support_ordinal),
  UNIQUE (account_id, authorization_revision_id, support_ref),
  FOREIGN KEY (account_id, authorization_revision_id)
    REFERENCES omi_memory.memory_identity_authorization_revisions
      (account_id, revision_id),
  FOREIGN KEY (account_id, support_ref)
    REFERENCES omi_memory.memory_identity_support (account_id, support_ref)
);

CREATE TABLE omi_memory.memory_generated_adjacency (
  account_id text NOT NULL,
  claim_revision_id text NOT NULL,
  entity_id text NOT NULL,
  role_slot_id text NOT NULL,
  commit_id text NOT NULL,
  PRIMARY KEY (account_id, claim_revision_id, entity_id, role_slot_id),
  FOREIGN KEY (account_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, entity_id)
    REFERENCES omi_memory.memory_entity_identities (account_id, entity_id),
  FOREIGN KEY (account_id, commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id)
);

CREATE TABLE omi_memory.memory_source_local_claim_roles (
  account_id text NOT NULL,
  claim_revision_id text NOT NULL,
  source_local_ref text NOT NULL,
  role_slot_id text NOT NULL,
  commit_id text NOT NULL,
  PRIMARY KEY (account_id, claim_revision_id, source_local_ref, role_slot_id),
  FOREIGN KEY (account_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id)
);

CREATE TABLE omi_memory.memory_consumed_markers (
  account_id text NOT NULL,
  provisional_revision_id text NOT NULL,
  commit_id text NOT NULL,
  disposition text NOT NULL,
  PRIMARY KEY (account_id, provisional_revision_id),
  FOREIGN KEY (account_id, provisional_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id)
);

CREATE TABLE omi_memory.memory_placement_artifacts (
  account_id text NOT NULL,
  artifact_id text NOT NULL,
  artifact_kind text NOT NULL CHECK (artifact_kind IN (
    'confirmation_queue', 'abstention_set', 'auto_placement_log'
  )),
  provisional_revision_id text NOT NULL,
  canonical_claim_revision_id text,
  margin text CHECK (margin IS NULL OR margin IN ('low', 'medium', 'high')),
  risk_markers jsonb NOT NULL CHECK (jsonb_typeof(risk_markers) = 'array'),
  unit_boundary_decision text NOT NULL CHECK (unit_boundary_decision IN ('accept_ltm', 'abstain')),
  scope_locality text CHECK (scope_locality IS NULL OR scope_locality IN ('durable', 'source_local')),
  commit_id text NOT NULL,
  PRIMARY KEY (account_id, artifact_id),
  FOREIGN KEY (account_id, provisional_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, canonical_claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id),
  FOREIGN KEY (account_id, commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id),
  CHECK (
    (artifact_kind = 'auto_placement_log' AND canonical_claim_revision_id IS NOT NULL)
    OR (artifact_kind <> 'auto_placement_log' AND canonical_claim_revision_id IS NULL)
  )
);

CREATE TABLE omi_memory.memory_candidate_derivation_artifacts (
  account_id text NOT NULL,
  artifact_id text NOT NULL,
  source_ref text NOT NULL,
  candidate_entity_id text NOT NULL,
  strategy_ref text NOT NULL,
  input_refs jsonb NOT NULL CHECK (jsonb_typeof(input_refs) = 'array'),
  commit_id text NOT NULL,
  PRIMARY KEY (account_id, artifact_id),
  FOREIGN KEY (account_id, candidate_entity_id)
    REFERENCES omi_memory.memory_entity_identities (account_id, entity_id),
  FOREIGN KEY (account_id, commit_id)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id)
);

CREATE TABLE omi_memory.memory_claim_liveness_fences (
  account_id text NOT NULL,
  claim_revision_id text NOT NULL,
  cause text NOT NULL CHECK (cause IN ('purged', 'forgotten')),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, claim_revision_id, cause),
  FOREIGN KEY (account_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions (account_id, claim_revision_id)
);

REVOKE ALL ON ALL TABLES IN SCHEMA omi_memory FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.seed_memory_graph_head() FROM PUBLIC;

GRANT SELECT, INSERT ON omi_memory.memory_derivation_attempts TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_derivation_commits TO omi_platform_application;
GRANT SELECT, UPDATE (commit_id, sequence, updated_at)
  ON omi_memory.memory_graph_heads TO omi_platform_application;
GRANT SELECT, INSERT, UPDATE (state, commit_id, finalized_at)
  ON omi_memory.memory_idempotency_receipts TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_derivation_inputs TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_event_identities TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_event_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_evidence_identities TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_evidence_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_claim_lineages TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_claim_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_claim_evidence_refs TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_claim_source_provisionals TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_claim_supersessions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_entity_identities TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_entity_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_predicate_identities TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_predicate_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_predicate_assertion_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_claim_predicate_refs TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_identity_authorization_identities TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_identity_authorization_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_identity_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_identity_authorization_entity_endpoints TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_identity_constraint_entity_endpoints TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_mention_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_coreference_support_revisions TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_coreference_support_evidence_refs TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_identity_support TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_identity_authorization_support TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_generated_adjacency TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_source_local_claim_roles TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_consumed_markers TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_placement_artifacts TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_candidate_derivation_artifacts TO omi_platform_application;
GRANT SELECT, INSERT ON omi_memory.memory_claim_liveness_fences TO omi_platform_application;
