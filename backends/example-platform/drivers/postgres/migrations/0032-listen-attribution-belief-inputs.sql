-- P6 text-free Listen attribution inputs for the isolated shadow experiment
-- plane. Original transcript bytes remain only in the accepted formation
-- input; this table stores strict directional evidence and opaque coordinates.

CREATE TABLE omi_memory.memory_listen_attribution_belief_inputs (
  account_id text NOT NULL,
  input_ref text NOT NULL CHECK (input_ref ~ '^labinput1_[0-9a-f]{64}$'),
  input_version text NOT NULL
    CHECK (input_version = 'stored-listen-attribution-belief-input-v1'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  formation_work_id text NOT NULL CHECK (length(formation_work_id) BETWEEN 1 AND 256),
  source_snapshot_digest text NOT NULL CHECK (source_snapshot_digest ~ '^[0-9a-f]{64}$'),
  set_digest text NOT NULL CHECK (set_digest ~ '^[0-9a-f]{64}$'),
  input_count integer NOT NULL CHECK (input_count BETWEEN 1 AND 2),
  input_ordinal integer NOT NULL CHECK (input_ordinal >= 0 AND input_ordinal < input_count),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  graph_frontier text NOT NULL CHECK (graph_frontier ~ '^[0-9a-f]{64}$'),
  stage_request_digest text NOT NULL CHECK (stage_request_digest ~ '^[0-9a-f]{64}$'),
  input_json jsonb NOT NULL CHECK (
    jsonb_typeof(input_json) = 'object'
    AND octet_length(input_json::text) <= 131072
  ),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, input_ref),
  UNIQUE (account_id, formation_work_id, input_ordinal),
  UNIQUE (account_id, formation_work_id, input_ref),
  FOREIGN KEY (account_id, formation_work_id)
    REFERENCES omi_memory.memory_formation_work_inputs (account_id, job_id)
);

CREATE FUNCTION omi_memory.require_complete_listen_attribution_belief_input_set()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
DECLARE
  v_count bigint;
  v_distinct bigint;
BEGIN
  SELECT count(*), count(DISTINCT ROW(
    i.account_epoch, i.source_snapshot_digest, i.set_digest, i.input_count,
    i.stage_request_digest
  ))
  INTO v_count, v_distinct
  FROM omi_memory.memory_listen_attribution_belief_inputs AS i
  WHERE i.account_id = NEW.account_id
    AND i.formation_work_id = NEW.formation_work_id;

  IF v_count IS DISTINCT FROM NEW.input_count::bigint OR v_distinct IS DISTINCT FROM 1::bigint
     OR EXISTS (
       SELECT 1
       FROM generate_series(0, NEW.input_count - 1) AS expected(ordinal)
       WHERE NOT EXISTS (
         SELECT 1
         FROM omi_memory.memory_listen_attribution_belief_inputs AS actual
         WHERE actual.account_id = NEW.account_id
           AND actual.formation_work_id = NEW.formation_work_id
           AND actual.input_ordinal = expected.ordinal
       )
     )
  THEN
    RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'incomplete belief input set';
  END IF;
  RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER memory_listen_attribution_belief_input_set_complete
AFTER INSERT ON omi_memory.memory_listen_attribution_belief_inputs
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION omi_memory.require_complete_listen_attribution_belief_input_set();

CREATE FUNCTION omi_memory.read_accepted_formation_work_input_for_shadow(
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
  v_account_id text := current_setting('omi.account_id', true);
BEGIN
  IF v_account_id IS NULL
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.experiments.shadow'
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'belief input source access denied';
  END IF;

  RETURN QUERY
  SELECT
    i.input_version, i.staged_input_id, i.account_id, i.job_id, i.account_epoch,
    i.accepted_work_digest, i.input_frontier, i.input_digest,
    i.execution_contract_digest, i.snapshot_digest, i.snapshot_json,
    i.stage_request_digest, i.content_hash
  FROM omi_memory.memory_formation_work_inputs AS i
  JOIN omi_memory.memory_work_acceptances AS a
    ON a.account_id = i.account_id AND a.job_id = i.job_id
   AND a.account_epoch = i.account_epoch
   AND a.accepted_work_digest = i.accepted_work_digest
   AND a.input_frontier = i.input_frontier
   AND a.input_digest = i.input_digest
   AND a.execution_contract_digest = i.execution_contract_digest
  WHERE i.account_id = v_account_id AND i.job_id = requested_job_id;
END;
$$;

CREATE FUNCTION omi_memory.insert_listen_attribution_belief_input(
  requested_input_ref text,
  requested_input_version text,
  requested_account_epoch bigint,
  requested_formation_work_id text,
  requested_source_snapshot_digest text,
  requested_set_digest text,
  requested_input_count integer,
  requested_input_ordinal integer,
  requested_input_digest text,
  requested_graph_frontier text,
  requested_stage_request_digest text,
  requested_input_json jsonb,
  requested_content_hash text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
DECLARE
  v_account_id text := current_setting('omi.account_id', true);
BEGIN
  IF v_account_id IS NULL
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.experiments.shadow'
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
     OR NOT EXISTS (
       SELECT 1
       FROM omi_memory.memory_formation_work_inputs AS i
       JOIN omi_memory.memory_work_acceptances AS a
         ON a.account_id = i.account_id AND a.job_id = i.job_id
        AND a.account_epoch = i.account_epoch
        AND a.accepted_work_digest = i.accepted_work_digest
        AND a.input_frontier = i.input_frontier
        AND a.input_digest = i.input_digest
        AND a.execution_contract_digest = i.execution_contract_digest
       WHERE i.account_id = v_account_id
         AND i.job_id = requested_formation_work_id
         AND i.account_epoch = requested_account_epoch
         AND i.snapshot_digest = requested_source_snapshot_digest
     )
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'belief input source access denied';
  END IF;

  INSERT INTO omi_memory.memory_listen_attribution_belief_inputs (
    account_id, input_ref, input_version, account_epoch, formation_work_id,
    source_snapshot_digest, set_digest, input_count, input_ordinal, input_digest,
    graph_frontier, stage_request_digest, input_json, content_hash
  ) VALUES (
    v_account_id, requested_input_ref, requested_input_version,
    requested_account_epoch, requested_formation_work_id,
    requested_source_snapshot_digest, requested_set_digest, requested_input_count,
    requested_input_ordinal, requested_input_digest, requested_graph_frontier,
    requested_stage_request_digest, requested_input_json, requested_content_hash
  );
  RETURN true;
END;
$$;

CREATE FUNCTION omi_memory.read_listen_attribution_belief_input_set(
  requested_input_ref text
)
RETURNS TABLE (
  input_version text,
  account_id text,
  account_epoch bigint,
  formation_work_id text,
  source_snapshot_digest text,
  set_digest text,
  input_count integer,
  input_ordinal integer,
  input_ref text,
  input_digest text,
  graph_frontier text,
  stage_request_digest text,
  input_json jsonb,
  content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
DECLARE
  v_account_id text := current_setting('omi.account_id', true);
  v_work_id text;
BEGIN
  IF v_account_id IS NULL
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.experiments.shadow'
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'belief input source access denied';
  END IF;

  SELECT i.formation_work_id INTO v_work_id
  FROM omi_memory.memory_listen_attribution_belief_inputs AS i
  WHERE i.account_id = v_account_id AND i.input_ref = requested_input_ref;

  RETURN QUERY
  SELECT
    i.input_version, i.account_id, i.account_epoch, i.formation_work_id,
    i.source_snapshot_digest, i.set_digest, i.input_count, i.input_ordinal,
    i.input_ref, i.input_digest, i.graph_frontier, i.stage_request_digest,
    i.input_json, i.content_hash
  FROM omi_memory.memory_listen_attribution_belief_inputs AS i
  WHERE i.account_id = v_account_id AND i.formation_work_id = v_work_id
  ORDER BY i.input_ordinal;
END;
$$;

REVOKE ALL ON omi_memory.memory_listen_attribution_belief_inputs FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.require_complete_listen_attribution_belief_input_set() FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_accepted_formation_work_input_for_shadow(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.insert_listen_attribution_belief_input(
  text, text, bigint, text, text, text, integer, integer, text, text, text, jsonb, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_listen_attribution_belief_input_set(text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.read_accepted_formation_work_input_for_shadow(text)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.insert_listen_attribution_belief_input(
  text, text, bigint, text, text, text, integer, integer, text, text, text, jsonb, text
) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_attribution_belief_input_set(text)
  TO omi_platform_application;

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

REVOKE ALL ON FUNCTION omi_memory.cleanup_surface_tables(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.cleanup_surface_tables(text)
  TO omi_platform_cleanup;
