CREATE TABLE omi_memory.listen_conversation_cursor_positions (
  account_id text NOT NULL REFERENCES omi_memory.platform_accounts(account_id),
  cursor_hash text NOT NULL CHECK(cursor_hash ~ '^[a-f0-9]{64}$'),
  binding_digest text NOT NULL CHECK(binding_digest ~ '^[a-f0-9]{64}$'),
  revision bigint NOT NULL CHECK(revision >= 0),
  sequence bigint NOT NULL CHECK(sequence > 0),
  expires_at bigint NOT NULL CHECK(expires_at >= 0),
  PRIMARY KEY(account_id,cursor_hash)
);
CREATE INDEX listen_conversation_cursor_expiry ON omi_memory.listen_conversation_cursor_positions(account_id,expires_at);
REVOKE ALL ON omi_memory.listen_conversation_cursor_positions FROM PUBLIC,omi_platform_application;

DROP FUNCTION omi_memory.read_listen_conversation_snapshot();
CREATE FUNCTION omi_memory.read_listen_conversation_metadata()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_revision bigint;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'conversations.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='conversation_authority_denied';
  END IF;
  SELECT revision INTO v_revision FROM omi_memory.listen_conversation_read_revisions WHERE account_id=v_account;
  RETURN jsonb_build_object('revision',coalesce(v_revision,0),'records','[]'::jsonb);
END $function$;

REVOKE ALL ON FUNCTION omi_memory.read_listen_conversation_metadata() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_conversation_metadata() TO omi_platform_application;

CREATE FUNCTION omi_memory.read_listen_conversation_page(p_limit integer,p_cursor_hash text,p_binding_digest text,p_revision bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_revision bigint; v_after bigint:=0; v_records jsonb;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'conversations.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='conversation_authority_denied';
  END IF;
  IF p_limit IS NULL OR p_limit<0 OR p_limit>10000 OR p_binding_digest IS NULL OR p_binding_digest !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='conversation_page_invalid';
  END IF;
  SELECT coalesce(revision,0) INTO v_revision FROM omi_memory.listen_conversation_read_revisions WHERE account_id=v_account;
  v_revision:=coalesce(v_revision,0);
  IF p_revision IS DISTINCT FROM v_revision THEN RETURN NULL; END IF;
  IF p_cursor_hash IS NOT NULL THEN
    SELECT sequence INTO v_after FROM omi_memory.listen_conversation_cursor_positions
    WHERE account_id=v_account AND cursor_hash=p_cursor_hash AND binding_digest=p_binding_digest AND revision=v_revision
      AND expires_at>floor(extract(epoch FROM clock_timestamp()));
    IF v_after IS NULL THEN RETURN NULL; END IF;
  END IF;
  WITH selected AS MATERIALIZED (
    SELECT s.account_id,s.session_id FROM omi_memory.listen_capture_sessions s
    WHERE s.account_id=v_account AND s.conversation_sequence>=v_after AND (
      EXISTS(SELECT 1 FROM omi_memory.listen_capture_audio_uploads u WHERE u.account_id=s.account_id AND u.session_id=s.session_id AND u.upload_completed_at IS NOT NULL)
      OR EXISTS(SELECT 1 FROM omi_memory.listen_conversation_finalization_intents i WHERE i.account_id=s.account_id AND i.conversation_id=s.conversation_id)
    ) ORDER BY s.conversation_sequence LIMIT p_limit
  ) SELECT coalesce(jsonb_agg(to_jsonb(record) ORDER BY record.sequence),'[]'::jsonb) INTO v_records FROM (
    SELECT s.conversation_sequence AS sequence,s.session_id,s.conversation_id,s.source,u.session_id IS NOT NULL AS device,
      s.started_at,coalesce(u.upload_completed_at,f.ended_at) AS ended_at,
      coalesce(t.updated_at,u.upload_completed_at,f.ended_at) AS updated_at,
      CASE WHEN u.session_id IS NULL THEN 'completed' ELSE coalesce(t.state,'queued') END AS state,
      coalesce(i.locked,false) AS locked,
      CASE WHEN u.session_id IS NULL THEN (
        SELECT coalesce(left(string_agg(left(segment.text_content,240),' ' ORDER BY segment.ordinal),240),'')
        FROM omi_memory.listen_capture_segments segment
        WHERE segment.account_id=s.account_id AND segment.session_id=s.session_id AND segment.ordinal<240
      ) WHEN t.state='completed' AND jsonb_typeof(t.provider_result->'segments')='array' THEN (
        SELECT coalesce(left(string_agg(left(segment.value->>'text',240),' ' ORDER BY segment.ordinal),240),'')
        FROM jsonb_array_elements(t.provider_result->'segments') WITH ORDINALITY AS segment(value,ordinal)
        WHERE segment.ordinal<=240
      ) ELSE NULL END AS excerpt
    FROM selected JOIN omi_memory.listen_capture_sessions s USING(account_id,session_id)
    LEFT JOIN omi_memory.listen_capture_audio_uploads u USING(account_id,session_id)
    LEFT JOIN omi_memory.listen_audio_transcriptions t USING(account_id,session_id)
    LEFT JOIN omi_memory.listen_conversation_finalization_intents i ON i.account_id=s.account_id AND i.conversation_id=s.conversation_id
    LEFT JOIN omi_memory.listen_formation_finalizations f ON f.account_id=s.account_id AND f.session_id=s.session_id
    WHERE s.account_id=v_account AND (u.upload_completed_at IS NOT NULL OR i.finalization_id IS NOT NULL)
    ORDER BY s.conversation_sequence
  ) AS record;
  RETURN jsonb_build_object('revision',v_revision,'records',v_records);
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_listen_conversation_page(integer,text,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_conversation_page(integer,text,text,bigint) TO omi_platform_application;

CREATE FUNCTION omi_memory.save_listen_conversation_cursor(p_cursor_hash text,p_binding_digest text,p_revision bigint,p_sequence bigint,p_expires_at bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_now bigint:=floor(extract(epoch FROM clock_timestamp()));
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'conversations.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='conversation_authority_denied';
  END IF;
  IF p_cursor_hash IS NULL OR p_cursor_hash !~ '^[a-f0-9]{64}$' OR p_binding_digest IS NULL OR p_binding_digest !~ '^[a-f0-9]{64}$'
    OR p_expires_at IS NULL OR p_expires_at<=v_now OR p_expires_at>v_now+900
    OR NOT EXISTS(SELECT 1 FROM omi_memory.listen_conversation_read_revisions WHERE account_id=v_account AND revision=p_revision)
    OR NOT EXISTS(SELECT 1 FROM omi_memory.listen_capture_sessions WHERE account_id=v_account AND conversation_sequence=p_sequence) THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='conversation_cursor_invalid';
  END IF;
  DELETE FROM omi_memory.listen_conversation_cursor_positions WHERE account_id=v_account AND cursor_hash IN (
    SELECT cursor_hash FROM omi_memory.listen_conversation_cursor_positions WHERE account_id=v_account AND expires_at<=v_now ORDER BY expires_at LIMIT 256
  );
  IF NOT EXISTS(SELECT 1 FROM omi_memory.listen_conversation_cursor_positions WHERE account_id=v_account AND cursor_hash=p_cursor_hash)
    AND EXISTS(SELECT 1 FROM omi_memory.listen_conversation_cursor_positions WHERE account_id=v_account OFFSET 9999 LIMIT 1) THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='conversation_cursor_capacity';
  END IF;
  INSERT INTO omi_memory.listen_conversation_cursor_positions(account_id,cursor_hash,binding_digest,revision,sequence,expires_at)
  VALUES(v_account,p_cursor_hash,p_binding_digest,p_revision,p_sequence,p_expires_at) ON CONFLICT(account_id,cursor_hash) DO NOTHING;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.save_listen_conversation_cursor(text,text,bigint,bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.save_listen_conversation_cursor(text,text,bigint,bigint,bigint) TO omi_platform_application;

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
