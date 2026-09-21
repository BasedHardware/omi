CREATE TABLE omi_memory.chat_attachments (
  account_id text NOT NULL REFERENCES omi_memory.platform_accounts(account_id),
  id text NOT NULL CHECK (id <> ''),
  content_reference text CHECK (content_reference IS NULL OR content_reference <> ''),
  attachment_scope text NOT NULL CHECK (attachment_scope <> ''),
  display_name text NOT NULL CHECK (display_name <> ''),
  mime_type text NOT NULL CHECK (mime_type IN (
    'image/jpeg','image/png','image/gif','image/webp','application/pdf','text/plain','text/markdown'
  )),
  size_bytes bigint NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 52428800),
  attachment_state text NOT NULL CHECK (attachment_state IN (
    'staged','scanning','clean','rejected','timed_out','error','bound'
  )),
  scanner_id text NOT NULL CHECK (scanner_id = 'dev-noop-scanner'),
  scanning_started_at bigint CHECK (scanning_started_at IS NULL OR scanning_started_at >= 0),
  staged_at bigint NOT NULL CHECK (staged_at >= 0),
  stage_expires_at bigint NOT NULL CHECK (stage_expires_at > staged_at),
  bound_message_id text CHECK (bound_message_id IS NULL OR bound_message_id <> ''),
  bound_at bigint CHECK (bound_at IS NULL OR bound_at >= 0),
  content_expires_at bigint CHECK (content_expires_at IS NULL OR content_expires_at >= 0),
  content_bytes bytea,
  PRIMARY KEY (account_id, id),
  UNIQUE (account_id, content_reference)
);
CREATE INDEX chat_attachments_owner_message ON omi_memory.chat_attachments (
  account_id, attachment_scope, bound_message_id, id
);
REVOKE ALL ON omi_memory.chat_attachments FROM PUBLIC, omi_platform_application;
ALTER TABLE omi_memory.chat_attachments ENABLE ROW LEVEL SECURITY;
CREATE POLICY chat_attachments_select ON omi_memory.chat_attachments FOR SELECT TO omi_platform_application
  USING (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write');
CREATE POLICY chat_attachments_insert ON omi_memory.chat_attachments FOR INSERT TO omi_platform_application
  WITH CHECK (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write');
CREATE POLICY chat_attachments_update ON omi_memory.chat_attachments FOR UPDATE TO omi_platform_application
  USING (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write')
  WITH CHECK (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write');
GRANT SELECT, INSERT, UPDATE ON omi_memory.chat_attachments TO omi_platform_application;

CREATE FUNCTION omi_memory.remove_unbound_chat_attachment(p_id text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_deleted integer;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'chat.write'
    OR p_id IS NULL OR p_id='' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='chat_authority_denied';
  END IF;
  DELETE FROM omi_memory.chat_attachments
  WHERE account_id=v_account AND id=p_id AND attachment_state IS DISTINCT FROM 'bound';
  GET DIAGNOSTICS v_deleted = ROW_COUNT;
  RETURN v_deleted = 1;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.remove_unbound_chat_attachment(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.remove_unbound_chat_attachment(text) TO omi_platform_application;

CREATE OR REPLACE FUNCTION omi_memory.cleanup_surface_tables(p_surface text)
RETURNS TABLE(table_name text)
LANGUAGE sql
IMMUTABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT mapping.table_name
  FROM (VALUES
    ('product_projections', 'listen_conversation_cursor_positions'),
    ('product_projections', 'listen_conversation_read_revisions'),
    ('product_projections', 'chat_admission_reservations'),
    ('product_projections', 'chat_attachments'),
    ('product_projections', 'chat_messages'),
    ('product_projections', 'chat_generation_events'),
    ('staged_results', 'listen_audio_transcriptions'),
    ('staged_results', 'listen_capture_audio_uploads'),
    ('staged_results', 'listen_capture_audio_chunks'),
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
