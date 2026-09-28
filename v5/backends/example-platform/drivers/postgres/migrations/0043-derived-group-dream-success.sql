-- P3 derived-group dream atomic success: graph witness commit plus append-only
-- product group projections and attribution belief revisions. No scheduler,
-- route, or worker activation is granted here.

ALTER TABLE omi_memory.memory_derivation_commits
  DROP CONSTRAINT memory_derivation_commits_non_formation_reason_check;

ALTER TABLE omi_memory.memory_derivation_commits
  ADD CONSTRAINT memory_derivation_commits_non_formation_reason_check
  CHECK (
    non_formation_reason IS NULL
    OR non_formation_reason IN (
      'repair', 'manual_liveness', 'historical_replay',
      'promotion', 'identity_consolidation', 'predicate_alignment', 'derived_group_dream'
    )
  );

ALTER TABLE omi_memory.memory_derivation_commits
  DROP CONSTRAINT memory_derivation_commits_origin_code_check;

ALTER TABLE omi_memory.memory_derivation_commits
  ADD CONSTRAINT memory_derivation_commits_origin_code_check
  CHECK (origin_code IN (
    'formation', 'repair', 'manual_liveness', 'historical_replay',
    'promotion', 'identity_consolidation', 'predicate_alignment', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_work_success_results
  DROP CONSTRAINT memory_work_success_results_origin_code_check;

ALTER TABLE omi_memory.memory_work_success_results
  ADD CONSTRAINT memory_work_success_results_origin_code_check
  CHECK (origin_code IS NULL OR origin_code IN (
    'formation', 'promotion', 'identity_consolidation', 'predicate_alignment', 'derived_group_dream'
  ));

ALTER TABLE omi_memory.memory_work_success_results
  DROP CONSTRAINT memory_work_success_results_check;

ALTER TABLE omi_memory.memory_work_success_results
  ADD CONSTRAINT memory_work_success_results_check
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
        OR (work_kind = 'derived_group_dream'
          AND origin_code = 'derived_group_dream')
      ))
  );

CREATE TABLE omi_memory.memory_attribution_belief_revisions (
  account_id text NOT NULL,
  belief_revision_id text NOT NULL CHECK (belief_revision_id ~ '^atbr1_[0-9a-f]{64}$'),
  belief_lineage_id text NOT NULL CHECK (belief_lineage_id ~ '^atbl1_[0-9a-f]{64}$'),
  belief_kind text NOT NULL CHECK (belief_kind IN (
    'source_identity', 'claim_subject', 'claim_truth'
  )),
  graph_frontier text NOT NULL CHECK (length(graph_frontier) BETWEEN 1 AND 256),
  graph_commit_id text NOT NULL,
  graph_commit_sequence bigint NOT NULL CHECK (graph_commit_sequence > 0),
  revision_contract_version text NOT NULL
    CHECK (revision_contract_version = 'attribution-belief-v1'),
  revision_json jsonb NOT NULL CHECK (
    jsonb_typeof(revision_json) = 'object'
    AND octet_length(revision_json::text) <= 524288
  ),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, belief_revision_id),
  UNIQUE (account_id, belief_lineage_id, belief_revision_id),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id),
  FOREIGN KEY (account_id, graph_commit_id, graph_commit_sequence)
    REFERENCES omi_memory.memory_derivation_commits (account_id, commit_id, sequence)
);

REVOKE ALL ON omi_memory.memory_attribution_belief_revisions FROM PUBLIC;

CREATE FUNCTION omi_memory.persist_derived_group_dream_materialization(
  requested_account_id text,
  requested_job_id text,
  requested_graph_frontier text,
  requested_graph_commit_id text,
  requested_graph_commit_sequence bigint,
  requested_outcome_json jsonb
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
DECLARE
  group_row jsonb;
  member_index integer;
  belief_row jsonb;
  group_id text;
  group_request_digest text;
  operation_identity text;
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.work.execute'
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'derived group dream materialization denied';
  END IF;

  IF jsonb_typeof(requested_outcome_json) <> 'object' THEN
    RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid derived group dream outcome';
  END IF;

  FOR group_row IN
    SELECT value FROM jsonb_array_elements(
      COALESCE(requested_outcome_json->'group_projections', '[]'::jsonb)
    )
  LOOP
    group_id := group_row->>'group_projection_id';
    IF group_id IS NULL THEN
      RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'invalid group projection';
    END IF;
  INSERT INTO omi_memory.memory_product_group_projections
    (account_id, group_projection_id, input_frontier, graph_commit_id,
     graph_commit_sequence, projection_contract_digest, result_digest,
     created_at_event_time, content_hash)
  VALUES (
    requested_account_id,
    group_id,
    group_row->>'input_frontier',
    requested_graph_commit_id,
    requested_graph_commit_sequence,
    group_row->>'projection_contract_digest',
    group_row->>'result_digest',
    (group_row->>'created_at_event_time')::bigint,
    group_row->>'result_digest'
  )
  ON CONFLICT (account_id, group_projection_id) DO NOTHING;

    member_index := 0;
    WHILE member_index < jsonb_array_length(group_row->'proposition_ids') LOOP
      INSERT INTO omi_memory.memory_product_group_members
        (account_id, group_projection_id, member_ordinal, proposition_id)
      VALUES (
        requested_account_id,
        group_id,
        member_index,
        group_row->'proposition_ids'->>member_index
      )
      ON CONFLICT (account_id, group_projection_id, member_ordinal) DO NOTHING;
      member_index := member_index + 1;
    END LOOP;

    operation_identity := group_id;
    group_request_digest := group_row->>'result_digest';
    INSERT INTO omi_memory.memory_product_operation_receipts
      (account_id, request_digest, operation, operation_identity, graph_frontier,
       graph_commit_id, graph_commit_sequence, receipt_contract_version)
    VALUES (
      requested_account_id, group_request_digest, 'group', operation_identity,
      requested_graph_frontier, requested_graph_commit_id,
      requested_graph_commit_sequence, 'product-operation-receipt-v1'
    )
    ON CONFLICT (account_id, request_digest) DO NOTHING;
  END LOOP;

  FOR belief_row IN
    SELECT value FROM jsonb_array_elements(
      COALESCE(requested_outcome_json->'people_cluster_beliefs', '[]'::jsonb)
    )
  LOOP
    INSERT INTO omi_memory.memory_attribution_belief_revisions
      (account_id, belief_revision_id, belief_lineage_id, belief_kind,
       graph_frontier, graph_commit_id, graph_commit_sequence,
       revision_contract_version, revision_json, content_hash)
    VALUES (
      requested_account_id,
      belief_row->>'belief_revision_id',
      belief_row->>'belief_lineage_id',
      belief_row->>'belief_kind',
      belief_row->>'graph_frontier',
      requested_graph_commit_id,
      requested_graph_commit_sequence,
      'attribution-belief-v1',
      belief_row,
      belief_row->>'observation_content_digest'
    )
    ON CONFLICT (account_id, belief_revision_id) DO NOTHING;
  END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION omi_memory.persist_derived_group_dream_materialization(
  text, text, text, text, bigint, jsonb
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.persist_derived_group_dream_materialization(
  text, text, text, text, bigint, jsonb
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
    ('authoritative_memory', 'memory_attribution_belief_revisions'),
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
