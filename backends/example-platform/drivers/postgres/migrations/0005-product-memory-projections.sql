-- P4 inert product-memory identity and projection persistence. This migration
-- adds no role grants, repository, worker, route, search index, or runtime.

CREATE TABLE omi_memory.memory_legacy_proposition_mappings (
  account_id text NOT NULL,
  legacy_source_id text NOT NULL CHECK (length(legacy_source_id) BETWEEN 1 AND 256),
  proposition_id text NOT NULL CHECK (
    length(proposition_id) BETWEEN 1 AND 256
    AND proposition_id !~ '^grp1_[0-9a-f]{64}$'
  ),
  allocation_contract text NOT NULL CHECK (allocation_contract = 'random_opaque_v1'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, legacy_source_id),
  UNIQUE (account_id, proposition_id),
  UNIQUE (account_id, legacy_source_id, proposition_id),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_migration_item_tombstones (
  account_id text NOT NULL,
  legacy_source_id text NOT NULL CHECK (length(legacy_source_id) BETWEEN 1 AND 256),
  tombstone_sequence bigint NOT NULL CHECK (tombstone_sequence > 0),
  tombstone_operation_id text NOT NULL CHECK (length(tombstone_operation_id) BETWEEN 1 AND 256),
  tombstoned_at_event_time bigint NOT NULL CHECK (tombstoned_at_event_time >= 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, legacy_source_id),
  UNIQUE (account_id, tombstone_operation_id),
  UNIQUE (account_id, legacy_source_id, tombstone_sequence),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.memory_product_propositions (
  account_id text NOT NULL,
  proposition_id text NOT NULL CHECK (
    length(proposition_id) BETWEEN 1 AND 256
    AND proposition_id !~ '^grp1_[0-9a-f]{64}$'
  ),
  product_contract_version text NOT NULL CHECK (product_contract_version = 'product-projection-v1'),
  birth_claim_lineage_id text NOT NULL,
  birth_commit_id text NOT NULL,
  birth_commit_sequence bigint NOT NULL CHECK (birth_commit_sequence > 0),
  origin text NOT NULL CHECK (origin IN ('native', 'legacy_mapping')),
  legacy_source_id text,
  created_at_event_time bigint NOT NULL CHECK (created_at_event_time >= 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, proposition_id),
  UNIQUE (account_id, legacy_source_id, proposition_id),
  FOREIGN KEY (account_id, birth_claim_lineage_id)
    REFERENCES omi_memory.memory_claim_lineages (account_id, claim_lineage_id),
  FOREIGN KEY (account_id, birth_commit_id, birth_commit_sequence)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id, sequence),
  FOREIGN KEY (account_id, legacy_source_id, proposition_id)
    REFERENCES omi_memory.memory_legacy_proposition_mappings
      (account_id, legacy_source_id, proposition_id),
  CHECK (
    (origin = 'native' AND legacy_source_id IS NULL)
    OR (origin = 'legacy_mapping' AND legacy_source_id IS NOT NULL)
  )
);

CREATE TABLE omi_memory.memory_product_membership_revisions (
  account_id text NOT NULL,
  proposition_id text NOT NULL,
  membership_revision_id text NOT NULL CHECK (membership_revision_id ~ '^pmr1_[0-9a-f]{64}$'),
  revision_sequence bigint NOT NULL CHECK (revision_sequence > 0),
  parent_membership_revision_id text,
  cause text NOT NULL CHECK (cause IN (
    'birth', 'ledger_consolidation', 'correction', 'product_successor'
  )),
  graph_frontier text NOT NULL CHECK (length(graph_frontier) BETWEEN 1 AND 256),
  graph_commit_id text NOT NULL,
  graph_commit_sequence bigint NOT NULL CHECK (graph_commit_sequence > 0),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  result_digest text NOT NULL CHECK (result_digest ~ '^[0-9a-f]{64}$'),
  created_at_event_time bigint NOT NULL CHECK (created_at_event_time >= 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, membership_revision_id),
  UNIQUE (account_id, proposition_id, revision_sequence),
  UNIQUE (account_id, proposition_id, membership_revision_id),
  UNIQUE (
    account_id, proposition_id, membership_revision_id, graph_frontier,
    graph_commit_id, graph_commit_sequence
  ),
  FOREIGN KEY (account_id, proposition_id)
    REFERENCES omi_memory.memory_product_propositions (account_id, proposition_id),
  FOREIGN KEY (account_id, proposition_id, parent_membership_revision_id)
    REFERENCES omi_memory.memory_product_membership_revisions
      (account_id, proposition_id, membership_revision_id),
  FOREIGN KEY (account_id, graph_commit_id, graph_commit_sequence)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id, sequence),
  CHECK (
    (cause = 'birth' AND revision_sequence = 1 AND parent_membership_revision_id IS NULL)
    OR (cause <> 'birth' AND revision_sequence > 1 AND parent_membership_revision_id IS NOT NULL)
  )
);

CREATE TABLE omi_memory.memory_product_membership_claim_lineages (
  account_id text NOT NULL,
  membership_revision_id text NOT NULL,
  member_ordinal integer NOT NULL CHECK (member_ordinal >= 0),
  claim_lineage_id text NOT NULL,
  PRIMARY KEY (account_id, membership_revision_id, member_ordinal),
  UNIQUE (account_id, membership_revision_id, claim_lineage_id),
  FOREIGN KEY (account_id, membership_revision_id)
    REFERENCES omi_memory.memory_product_membership_revisions
      (account_id, membership_revision_id),
  FOREIGN KEY (account_id, claim_lineage_id)
    REFERENCES omi_memory.memory_claim_lineages (account_id, claim_lineage_id)
);

ALTER TABLE omi_memory.memory_claim_revisions
  ADD CONSTRAINT memory_claim_revisions_lineage_revision_unique
  UNIQUE (account_id, claim_lineage_id, claim_revision_id);

CREATE TABLE omi_memory.memory_product_projection_revisions (
  account_id text NOT NULL,
  proposition_id text NOT NULL,
  projection_revision_id text NOT NULL CHECK (projection_revision_id ~ '^pvr1_[0-9a-f]{64}$'),
  projection_sequence bigint NOT NULL CHECK (projection_sequence > 0),
  membership_revision_id text NOT NULL,
  graph_frontier text NOT NULL CHECK (length(graph_frontier) BETWEEN 1 AND 256),
  graph_commit_id text NOT NULL,
  graph_commit_sequence bigint NOT NULL CHECK (graph_commit_sequence > 0),
  renderer_contract_digest text NOT NULL CHECK (renderer_contract_digest ~ '^[0-9a-f]{64}$'),
  rendered_content_digest text NOT NULL CHECK (rendered_content_digest ~ '^[0-9a-f]{64}$'),
  created_at_event_time bigint NOT NULL CHECK (created_at_event_time >= 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, projection_revision_id),
  UNIQUE (account_id, proposition_id, projection_sequence),
  UNIQUE (account_id, proposition_id, projection_revision_id),
  UNIQUE (account_id, projection_revision_id, membership_revision_id),
  UNIQUE (account_id, projection_revision_id, rendered_content_digest),
  FOREIGN KEY (account_id, proposition_id)
    REFERENCES omi_memory.memory_product_propositions (account_id, proposition_id),
  FOREIGN KEY (
    account_id, proposition_id, membership_revision_id, graph_frontier,
    graph_commit_id, graph_commit_sequence
  )
    REFERENCES omi_memory.memory_product_membership_revisions
      (
        account_id, proposition_id, membership_revision_id, graph_frontier,
        graph_commit_id, graph_commit_sequence
      )
);

CREATE TABLE omi_memory.memory_product_projection_payloads (
  account_id text NOT NULL,
  projection_revision_id text NOT NULL,
  rendered_content_digest text NOT NULL CHECK (rendered_content_digest ~ '^[0-9a-f]{64}$'),
  payload_contract_version text NOT NULL CHECK (length(payload_contract_version) BETWEEN 1 AND 256),
  rendered_content_json jsonb NOT NULL CHECK (jsonb_typeof(rendered_content_json) = 'object'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, projection_revision_id),
  UNIQUE (account_id, projection_revision_id, rendered_content_digest),
  FOREIGN KEY (account_id, projection_revision_id, rendered_content_digest)
    REFERENCES omi_memory.memory_product_projection_revisions
      (account_id, projection_revision_id, rendered_content_digest)
);

ALTER TABLE omi_memory.memory_product_projection_revisions
  ADD CONSTRAINT memory_product_projection_revisions_payload_fk
  FOREIGN KEY (account_id, projection_revision_id, rendered_content_digest)
  REFERENCES omi_memory.memory_product_projection_payloads
    (account_id, projection_revision_id, rendered_content_digest)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE omi_memory.memory_product_projection_citations (
  account_id text NOT NULL,
  projection_revision_id text NOT NULL,
  membership_revision_id text NOT NULL,
  citation_ordinal integer NOT NULL CHECK (citation_ordinal >= 0),
  claim_lineage_id text NOT NULL,
  claim_revision_id text NOT NULL,
  PRIMARY KEY (account_id, projection_revision_id, citation_ordinal),
  UNIQUE (account_id, projection_revision_id, claim_lineage_id, claim_revision_id),
  UNIQUE (account_id, projection_revision_id, citation_ordinal, claim_revision_id),
  FOREIGN KEY (account_id, projection_revision_id, membership_revision_id)
    REFERENCES omi_memory.memory_product_projection_revisions
      (account_id, projection_revision_id, membership_revision_id),
  FOREIGN KEY (account_id, membership_revision_id, claim_lineage_id)
    REFERENCES omi_memory.memory_product_membership_claim_lineages
      (account_id, membership_revision_id, claim_lineage_id),
  FOREIGN KEY (account_id, claim_lineage_id, claim_revision_id)
    REFERENCES omi_memory.memory_claim_revisions
      (account_id, claim_lineage_id, claim_revision_id)
);

CREATE TABLE omi_memory.memory_product_projection_citation_evidence_refs (
  account_id text NOT NULL,
  projection_revision_id text NOT NULL,
  citation_ordinal integer NOT NULL CHECK (citation_ordinal >= 0),
  evidence_ordinal integer NOT NULL CHECK (evidence_ordinal >= 0),
  claim_revision_id text NOT NULL,
  evidence_id text NOT NULL,
  PRIMARY KEY (
    account_id, projection_revision_id, citation_ordinal, evidence_ordinal
  ),
  UNIQUE (account_id, projection_revision_id, citation_ordinal, evidence_id),
  FOREIGN KEY (
    account_id, projection_revision_id, citation_ordinal, claim_revision_id
  )
    REFERENCES omi_memory.memory_product_projection_citations
      (account_id, projection_revision_id, citation_ordinal, claim_revision_id),
  FOREIGN KEY (account_id, claim_revision_id, evidence_id)
    REFERENCES omi_memory.memory_claim_evidence_refs
      (account_id, claim_revision_id, evidence_id)
);

CREATE TABLE omi_memory.memory_product_redirects (
  account_id text NOT NULL,
  redirect_id text NOT NULL CHECK (redirect_id ~ '^prd1_[0-9a-f]{64}$'),
  source_proposition_id text NOT NULL,
  operation text NOT NULL CHECK (operation IN ('merge', 'split')),
  operation_ref text NOT NULL CHECK (length(operation_ref) BETWEEN 1 AND 256),
  created_at_event_time bigint NOT NULL CHECK (created_at_event_time >= 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, redirect_id),
  UNIQUE (account_id, source_proposition_id),
  UNIQUE (account_id, redirect_id, source_proposition_id),
  FOREIGN KEY (account_id, source_proposition_id)
    REFERENCES omi_memory.memory_product_propositions (account_id, proposition_id)
);

CREATE TABLE omi_memory.memory_product_redirect_successors (
  account_id text NOT NULL,
  redirect_id text NOT NULL,
  successor_ordinal integer NOT NULL CHECK (successor_ordinal >= 0),
  source_proposition_id text NOT NULL,
  successor_proposition_id text NOT NULL,
  PRIMARY KEY (account_id, redirect_id, successor_ordinal),
  UNIQUE (account_id, redirect_id, successor_proposition_id),
  FOREIGN KEY (account_id, redirect_id, source_proposition_id)
    REFERENCES omi_memory.memory_product_redirects
      (account_id, redirect_id, source_proposition_id),
  FOREIGN KEY (account_id, successor_proposition_id)
    REFERENCES omi_memory.memory_product_propositions (account_id, proposition_id),
  CHECK (source_proposition_id <> successor_proposition_id)
);

CREATE TABLE omi_memory.memory_product_group_projections (
  account_id text NOT NULL,
  group_projection_id text NOT NULL CHECK (group_projection_id ~ '^grp1_[0-9a-f]{64}$'),
  input_frontier text NOT NULL CHECK (length(input_frontier) BETWEEN 1 AND 256),
  graph_commit_id text NOT NULL,
  graph_commit_sequence bigint NOT NULL CHECK (graph_commit_sequence > 0),
  projection_contract_digest text NOT NULL CHECK (projection_contract_digest ~ '^[0-9a-f]{64}$'),
  result_digest text NOT NULL CHECK (result_digest ~ '^[0-9a-f]{64}$'),
  created_at_event_time bigint NOT NULL CHECK (created_at_event_time >= 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, group_projection_id),
  FOREIGN KEY (account_id, graph_commit_id, graph_commit_sequence)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id, sequence)
);

CREATE TABLE omi_memory.memory_product_group_members (
  account_id text NOT NULL,
  group_projection_id text NOT NULL,
  member_ordinal integer NOT NULL CHECK (member_ordinal >= 0),
  proposition_id text NOT NULL,
  PRIMARY KEY (account_id, group_projection_id, member_ordinal),
  UNIQUE (account_id, group_projection_id, proposition_id),
  FOREIGN KEY (account_id, group_projection_id)
    REFERENCES omi_memory.memory_product_group_projections
      (account_id, group_projection_id),
  FOREIGN KEY (account_id, proposition_id)
    REFERENCES omi_memory.memory_product_propositions (account_id, proposition_id)
);

REVOKE ALL ON ALL TABLES IN SCHEMA omi_memory FROM PUBLIC;

-- Deliberately no application, migration-copier, projector, or worker grant.
-- The real PostgreSQL adapter must first prove insert-if-absent mapping,
-- tombstone-at-resume, atomic projection+payload+citation writes, reader-relative
-- authorization-before-latest selection, and crash/replay behavior.
