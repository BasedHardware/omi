CREATE TABLE omi_memory.task_records (
  account_id text NOT NULL REFERENCES omi_memory.platform_accounts(account_id),
  record_id text NOT NULL CHECK(record_id ~ '^[!-~]+$' AND length(record_id)<=256),
  revision text NOT NULL CHECK (revision ~ '^[a-f0-9]{64}$'),
  content_json text,
  first_seen_seq bigint NOT NULL CHECK (first_seen_seq BETWEEN 1 AND 9007199254740991),
  last_applied_seq bigint NOT NULL CHECK (last_applied_seq BETWEEN 1 AND 9007199254740991),
  PRIMARY KEY (account_id,record_id),
  CHECK (content_json IS NULL OR json_typeof(content_json::json)='object')
);
CREATE TABLE omi_memory.task_sequences (
  account_id text PRIMARY KEY REFERENCES omi_memory.platform_accounts(account_id),
  sequence bigint NOT NULL CHECK (sequence BETWEEN 0 AND 9007199254740991)
);
CREATE TABLE omi_memory.task_write_receipts (
  account_id text NOT NULL REFERENCES omi_memory.platform_accounts(account_id),
  write_id text NOT NULL CHECK(write_id ~ '^[0-9a-f]{64}$'),
  account_epoch bigint NOT NULL CHECK(account_epoch>=0),
  fingerprint text NOT NULL,
  outcome_json text NOT NULL CHECK(json_typeof(outcome_json::json)='object'),
  PRIMARY KEY(account_id,write_id)
);
CREATE TABLE omi_memory.task_stragglers (
  account_id text NOT NULL REFERENCES omi_memory.platform_accounts(account_id),
  write_id text NOT NULL CHECK(write_id ~ '^[0-9a-f]{64}$'),
  envelope_digest text NOT NULL CHECK(envelope_digest ~ '^[a-f0-9]{64}$'),
  envelope_json text NOT NULL,
  account_epoch bigint NOT NULL CHECK(account_epoch>=0),
  retained_at_epoch_seconds bigint NOT NULL CHECK(retained_at_epoch_seconds>=0),
  PRIMARY KEY(account_id,write_id,envelope_digest)
);
DO $policies$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['task_records','task_sequences','task_write_receipts','task_stragglers'] LOOP
    EXECUTE format('ALTER TABLE omi_memory.%I ENABLE ROW LEVEL SECURITY',target);
    EXECUTE format('CREATE POLICY task_read ON omi_memory.%I FOR SELECT TO omi_platform_application USING (account_id=current_setting(''omi.account_id'',true) AND current_setting(''omi.capability'',true) IN (''tasks.read'',''tasks.write''))',target);
    EXECUTE format('CREATE POLICY task_insert ON omi_memory.%I FOR INSERT TO omi_platform_application WITH CHECK (account_id=current_setting(''omi.account_id'',true) AND current_setting(''omi.capability'',true)=''tasks.write'')',target);
    EXECUTE format('CREATE POLICY task_update ON omi_memory.%I FOR UPDATE TO omi_platform_application USING (account_id=current_setting(''omi.account_id'',true) AND current_setting(''omi.capability'',true)=''tasks.write'') WITH CHECK (account_id=current_setting(''omi.account_id'',true) AND current_setting(''omi.capability'',true)=''tasks.write'')',target);
    EXECUTE format('GRANT SELECT,INSERT,UPDATE ON omi_memory.%I TO omi_platform_application',target);
  END LOOP;
END $policies$;

CREATE OR REPLACE FUNCTION omi_memory.cleanup_surface_tables(p_surface text)
RETURNS TABLE(table_name text)
LANGUAGE sql
IMMUTABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT mapping.table_name
  FROM (VALUES
    ('product_projections', 'task_records'),
    ('product_projections', 'task_sequences'),
    ('product_projections', 'task_write_receipts'),
    ('product_projections', 'task_stragglers'),
    ('product_projections', 'memory_render_responses'),
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
