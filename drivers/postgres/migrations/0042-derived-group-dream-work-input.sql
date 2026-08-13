-- P3 exact derived-group-dream input persistence. The bounded dream snapshot is
-- staged before work acceptance so a later worker can reconstruct the exact
-- grouping input after process loss without re-planning against a changed graph.

ALTER TABLE omi_memory.memory_work_acceptances
  DROP CONSTRAINT memory_work_acceptances_work_kind_check,
  ADD CONSTRAINT memory_work_acceptances_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_work_staged_results
  DROP CONSTRAINT memory_work_staged_results_work_kind_check,
  ADD CONSTRAINT memory_work_staged_results_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_work_success_results
  DROP CONSTRAINT memory_work_success_results_work_kind_check,
  ADD CONSTRAINT memory_work_success_results_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_work_execution_policies
  DROP CONSTRAINT memory_work_execution_policies_work_kind_check,
  ADD CONSTRAINT memory_work_execution_policies_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_strategy_definitions
  DROP CONSTRAINT memory_strategy_definitions_work_kind_check,
  ADD CONSTRAINT memory_strategy_definitions_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_strategy_assignment_policies
  DROP CONSTRAINT memory_strategy_assignment_policies_work_kind_check,
  ADD CONSTRAINT memory_strategy_assignment_policies_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_strategy_policy_shadows
  DROP CONSTRAINT memory_strategy_policy_shadows_work_kind_check,
  ADD CONSTRAINT memory_strategy_policy_shadows_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_strategy_assignment_bundles
  DROP CONSTRAINT memory_strategy_assignment_bundles_work_kind_check,
  ADD CONSTRAINT memory_strategy_assignment_bundles_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_strategy_shadow_assignments
  DROP CONSTRAINT memory_strategy_shadow_assignments_work_kind_check,
  ADD CONSTRAINT memory_strategy_shadow_assignments_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_strategy_evaluation_baselines
  DROP CONSTRAINT memory_strategy_evaluation_baselines_work_kind_check,
  ADD CONSTRAINT memory_strategy_evaluation_baselines_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_strategy_shadow_results
  DROP CONSTRAINT memory_strategy_shadow_results_work_kind_check,
  ADD CONSTRAINT memory_strategy_shadow_results_work_kind_check CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch',
    'retrieval', 'composition', 'derived_group_dream'
  ));

CREATE TABLE omi_memory.memory_derived_group_dream_work_inputs (
  account_id text NOT NULL,
  staged_input_id text NOT NULL CHECK (staged_input_id ~ '^dgwi1_[0-9a-f]{64}$'),
  job_id text NOT NULL CHECK (length(job_id) BETWEEN 1 AND 256),
  input_version text NOT NULL CHECK (input_version = 'derived-group-dream-work-staged-input-v1'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  accepted_work_digest text NOT NULL CHECK (accepted_work_digest ~ '^[0-9a-f]{64}$'),
  input_frontier text NOT NULL CHECK (length(input_frontier) BETWEEN 1 AND 256),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  execution_contract_digest text NOT NULL
    CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  snapshot_digest text NOT NULL CHECK (snapshot_digest ~ '^[0-9a-f]{64}$'),
  snapshot_version text NOT NULL CHECK (snapshot_version = 'derived-group-dream-input-snapshot-v1'),
  snapshot_json jsonb NOT NULL CHECK (
    jsonb_typeof(snapshot_json) = 'object'
    AND octet_length(snapshot_json::text) <= 524288
  ),
  stage_request_digest text NOT NULL CHECK (stage_request_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, job_id),
  UNIQUE (account_id, staged_input_id),
  FOREIGN KEY (account_id) REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE FUNCTION omi_memory.require_derived_group_dream_work_input()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
BEGIN
  IF NEW.work_kind = 'derived_group_dream' AND NOT EXISTS (
    SELECT 1
    FROM omi_memory.memory_derived_group_dream_work_inputs AS i
    WHERE i.account_id = NEW.account_id
      AND i.job_id = NEW.job_id
      AND i.account_epoch = NEW.account_epoch
      AND i.accepted_work_digest = NEW.accepted_work_digest
      AND i.input_frontier = NEW.input_frontier
      AND i.input_digest = NEW.input_digest
      AND i.execution_contract_digest = NEW.execution_contract_digest
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '23503', MESSAGE = 'derived group dream work input missing';
  END IF;
  RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER memory_derived_group_dream_acceptance_requires_input
AFTER INSERT ON omi_memory.memory_work_acceptances
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION omi_memory.require_derived_group_dream_work_input();

CREATE FUNCTION omi_memory.read_derived_group_dream_work_input(
  requested_account_id text,
  requested_job_id text
)
RETURNS TABLE (
  input_version text,
  staged_input_id text,
  account_id text,
  job_id text,
  account_epoch bigint,
  accepted_work_digest text,
  input_frontier text,
  input_digest text,
  execution_contract_digest text,
  snapshot_digest text,
  snapshot_json jsonb,
  stage_request_digest text,
  content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
DECLARE
  capability text := current_setting('omi.capability', true);
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR capability NOT IN ('memories.work.accept', 'memories.work.execute')
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'derived group dream work input access denied';
  END IF;

  IF capability = 'memories.work.execute' AND NOT EXISTS (
    SELECT 1
    FROM omi_memory.memory_work_heads AS h
    JOIN omi_memory.memory_work_state_revisions AS s
      ON s.account_id = h.account_id AND s.job_id = h.job_id
     AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
    WHERE h.account_id = requested_account_id
      AND h.job_id = requested_job_id
      AND s.state = 'leased'
      AND s.worker_id = current_setting('omi.principal_id', true)
      AND s.lease_expires_at_event_time
        > floor(extract(epoch FROM transaction_timestamp()))::bigint
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'derived group dream work input lease denied';
  END IF;

  RETURN QUERY
  SELECT
    i.input_version, i.staged_input_id, i.account_id, i.job_id, i.account_epoch,
    i.accepted_work_digest, i.input_frontier, i.input_digest,
    i.execution_contract_digest, i.snapshot_digest, i.snapshot_json,
    i.stage_request_digest, i.content_hash
  FROM omi_memory.memory_derived_group_dream_work_inputs AS i
  WHERE i.account_id = requested_account_id AND i.job_id = requested_job_id;
END;
$$;

CREATE FUNCTION omi_memory.insert_derived_group_dream_work_input(
  requested_account_id text,
  requested_staged_input_id text,
  requested_job_id text,
  requested_input_version text,
  requested_account_epoch bigint,
  requested_accepted_work_digest text,
  requested_input_frontier text,
  requested_input_digest text,
  requested_execution_contract_digest text,
  requested_snapshot_digest text,
  requested_snapshot_version text,
  requested_snapshot_json jsonb,
  requested_stage_request_digest text,
  requested_content_hash text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.work.accept'
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'derived group dream work input access denied';
  END IF;

  INSERT INTO omi_memory.memory_derived_group_dream_work_inputs (
    account_id, staged_input_id, job_id, input_version, account_epoch,
    accepted_work_digest, input_frontier, input_digest, execution_contract_digest,
    snapshot_digest, snapshot_version, snapshot_json, stage_request_digest, content_hash
  ) VALUES (
    requested_account_id, requested_staged_input_id, requested_job_id,
    requested_input_version, requested_account_epoch, requested_accepted_work_digest,
    requested_input_frontier, requested_input_digest,
    requested_execution_contract_digest, requested_snapshot_digest,
    requested_snapshot_version, requested_snapshot_json,
    requested_stage_request_digest, requested_content_hash
  );
  RETURN true;
END;
$$;

REVOKE ALL ON omi_memory.memory_derived_group_dream_work_inputs FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.require_derived_group_dream_work_input() FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_derived_group_dream_work_input(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.insert_derived_group_dream_work_input(
  text, text, text, text, bigint, text, text, text, text, text, text, jsonb, text, text
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.read_derived_group_dream_work_input(text, text)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.insert_derived_group_dream_work_input(
  text, text, text, text, bigint, text, text, text, text, text, text, jsonb, text, text
) TO omi_platform_application;

-- Extend the closed account-deletion registry without changing prior bytes.
CREATE OR REPLACE FUNCTION omi_memory.cleanup_surface_tables(p_surface text)
RETURNS TABLE(table_name text)
LANGUAGE sql
IMMUTABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT mapping.table_name
  FROM (VALUES
    ('durable_work', 'memory_work_acceptances'),
    ('durable_work', 'memory_work_execution_policies'),
    ('durable_work', 'memory_work_heads'),
    ('durable_work', 'memory_work_input_manifest'),
    ('durable_work', 'memory_work_outbox_events'),
    ('durable_work', 'memory_work_state_revisions'),
    ('durable_work', 'memory_work_success_results'),
    ('staged_results', 'memory_work_staged_results'),
    ('staged_results', 'memory_formation_work_inputs'),
    ('staged_results', 'memory_predicate_batch_work_inputs'),
    ('staged_results', 'memory_derived_group_dream_work_inputs'),
    ('staged_results', 'memory_query_evaluation_inputs'),
    ('staged_results', 'memory_listen_attribution_belief_inputs'),
    ('staged_results', 'memory_candidate_derivation_artifacts'),
    ('staged_results', 'listen_capture_sessions'),
    ('staged_results', 'listen_capture_session_state_revisions'),
    ('staged_results', 'listen_capture_segments'),
    ('staged_results', 'listen_formation_finalizations'),
    ('staged_results', 'listen_conversation_finalization_intents'),
    ('staged_results', 'listen_formation_outbox'),
    ('staged_results', 'listen_formation_delivery_revisions'),
    ('staged_results', 'listen_formation_delivery_heads'),
    ('authoritative_memory', 'memory_claim_evidence_refs'),
    ('authoritative_memory', 'memory_claim_lineages'),
    ('authoritative_memory', 'memory_claim_liveness_fences'),
    ('authoritative_memory', 'memory_claim_predicate_refs'),
    ('authoritative_memory', 'memory_claim_revisions'),
    ('authoritative_memory', 'memory_claim_source_provisionals'),
    ('authoritative_memory', 'memory_claim_supersessions'),
    ('authoritative_memory', 'memory_consumed_markers'),
    ('authoritative_memory', 'memory_coreference_support_evidence_refs'),
    ('authoritative_memory', 'memory_coreference_support_revisions'),
    ('authoritative_memory', 'memory_derivation_attempts'),
    ('authoritative_memory', 'memory_derivation_commits'),
    ('authoritative_memory', 'memory_derivation_inputs'),
    ('authoritative_memory', 'memory_entity_identities'),
    ('authoritative_memory', 'memory_entity_revisions'),
    ('authoritative_memory', 'memory_event_identities'),
    ('authoritative_memory', 'memory_event_revisions'),
    ('authoritative_memory', 'memory_evidence_identities'),
    ('authoritative_memory', 'memory_evidence_revisions'),
    ('authoritative_memory', 'memory_formation_extraction_evidence'),
    ('authoritative_memory', 'memory_formation_extraction_outcomes'),
    ('authoritative_memory', 'memory_formation_placement_outcomes'),
    ('authoritative_memory', 'memory_formation_outcomes'),
    ('authoritative_memory', 'memory_generated_adjacency'),
    ('authoritative_memory', 'memory_graph_heads'),
    ('authoritative_memory', 'memory_idempotency_receipts'),
    ('authoritative_memory', 'memory_identity_authorization_identities'),
    ('authoritative_memory', 'memory_identity_authorization_entity_endpoints'),
    ('authoritative_memory', 'memory_identity_authorization_revisions'),
    ('authoritative_memory', 'memory_identity_authorization_support'),
    ('authoritative_memory', 'memory_identity_constraint_entity_endpoints'),
    ('authoritative_memory', 'memory_identity_revisions'),
    ('authoritative_memory', 'memory_identity_support'),
    ('authoritative_memory', 'memory_mention_revisions'),
    ('authoritative_memory', 'memory_placement_artifacts'),
    ('authoritative_memory', 'memory_predicate_assertion_revisions'),
    ('authoritative_memory', 'memory_predicate_identities'),
    ('authoritative_memory', 'memory_predicate_revisions'),
    ('authoritative_memory', 'memory_revisions'),
    ('authoritative_memory', 'memory_source_local_claim_roles'),
    ('account_access', 'application_credential_heads'),
    ('account_access', 'application_credential_revisions'),
    ('account_access', 'application_grant_heads'),
    ('account_access', 'application_grant_revisions'),
    ('account_access', 'firebase_application_credential_bindings'),
    ('account_access', 'firebase_identity_bindings'),
    ('experiment_results', 'memory_strategy_assignment_bundles'),
    ('experiment_results', 'memory_strategy_assignment_policies'),
    ('experiment_results', 'memory_strategy_baseline_read_groundings'),
    ('experiment_results', 'memory_strategy_candidate_read_groundings'),
    ('experiment_results', 'memory_strategy_definitions'),
    ('experiment_results', 'memory_strategy_evaluation_baselines'),
    ('experiment_results', 'memory_strategy_evaluation_pairs'),
    ('experiment_results', 'memory_strategy_policy_shadows'),
    ('experiment_results', 'memory_strategy_shadow_assignments'),
    ('experiment_results', 'memory_strategy_shadow_results'),
    ('product_projections', 'memory_product_membership_claim_lineages'),
    ('product_projections', 'memory_product_membership_revisions'),
    ('product_projections', 'memory_product_operation_receipts'),
    ('product_projections', 'memory_product_projection_citation_evidence_refs'),
    ('product_projections', 'memory_product_projection_citations'),
    ('product_projections', 'memory_product_projection_payloads'),
    ('product_projections', 'memory_product_projection_revisions'),
    ('product_projections', 'memory_product_propositions'),
    ('product_projections', 'memory_product_redirect_successors'),
    ('product_projections', 'memory_product_redirects'),
    ('rebuildable_groups_indexes', 'memory_product_group_members'),
    ('rebuildable_groups_indexes', 'memory_product_group_projections'),
    ('migration_state', 'memory_legacy_proposition_mappings'),
    ('migration_state', 'memory_migration_item_tombstones')
  ) AS mapping(surface, table_name)
  WHERE mapping.surface = p_surface
  ORDER BY mapping.table_name
$function$;

-- No direct table grant and no runtime composition. The trigger protects only
-- newly inserted derived-group-dream acceptances; earlier rows remain unchanged.
