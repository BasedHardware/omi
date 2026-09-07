CREATE TABLE omi_memory.chat_messages (
  sequence bigint GENERATED ALWAYS AS IDENTITY (INCREMENT BY 1 MINVALUE 1 MAXVALUE 9007199254740991),
  account_id text NOT NULL REFERENCES omi_memory.platform_accounts(account_id),
  id text NOT NULL CHECK (id <> ''),
  text text NOT NULL,
  sender text NOT NULL CHECK (sender <> ''),
  message_type text NOT NULL CHECK (message_type <> ''),
  created_at bigint NOT NULL CHECK (created_at >= 0),
  updated_at bigint NOT NULL CHECK (updated_at >= 0),
  chat_session_id text,
  app_id text,
  journal_revision bigint NOT NULL CHECK (journal_revision >= 0),
  payload_hash text NOT NULL CHECK (payload_hash <> ''),
  message_source text NOT NULL CHECK (message_source <> ''),
  rating double precision,
  reported boolean NOT NULL,
  server_revision text,
  attachments_json jsonb CHECK (attachments_json IS NULL OR jsonb_typeof(attachments_json)='array'),
  generation_id text,
  PRIMARY KEY (account_id, id),
  UNIQUE (account_id, sequence)
);
CREATE INDEX chat_messages_history ON omi_memory.chat_messages (
  account_id, app_id, chat_session_id, created_at DESC, id DESC, sequence
);
CREATE TABLE omi_memory.chat_generation_events (
  account_id text NOT NULL REFERENCES omi_memory.platform_accounts(account_id),
  generation_id text NOT NULL CHECK (generation_id <> ''),
  sequence bigint NOT NULL CHECK (sequence > 0 AND sequence <= 9007199254740991),
  event_id text NOT NULL CHECK (event_id <> ''),
  created_at bigint NOT NULL CHECK (created_at >= 0),
  frame_json jsonb NOT NULL,
  PRIMARY KEY (account_id, generation_id, sequence),
  UNIQUE (account_id, generation_id, event_id)
);
REVOKE ALL ON omi_memory.chat_messages FROM PUBLIC, omi_platform_application;
REVOKE ALL ON omi_memory.chat_generation_events FROM PUBLIC, omi_platform_application;
ALTER TABLE omi_memory.chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE omi_memory.chat_generation_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY chat_messages_select ON omi_memory.chat_messages FOR SELECT TO omi_platform_application
  USING (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true) IN ('chat.read','chat.write'));
CREATE POLICY chat_messages_insert ON omi_memory.chat_messages FOR INSERT TO omi_platform_application
  WITH CHECK (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write');
CREATE POLICY chat_messages_update ON omi_memory.chat_messages FOR UPDATE TO omi_platform_application
  USING (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write')
  WITH CHECK (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write');
CREATE POLICY chat_generation_events_select ON omi_memory.chat_generation_events FOR SELECT TO omi_platform_application
  USING (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true) IN ('chat.read','chat.write'));
CREATE POLICY chat_generation_events_insert ON omi_memory.chat_generation_events FOR INSERT TO omi_platform_application
  WITH CHECK (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write');
CREATE POLICY chat_generation_events_update ON omi_memory.chat_generation_events FOR UPDATE TO omi_platform_application
  USING (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write')
  WITH CHECK (account_id=current_setting('omi.account_id',true) AND current_setting('omi.capability',true)='chat.write');

CREATE FUNCTION omi_memory.read_chat_snapshot_sequence()
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_sequence bigint;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'chat.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='chat_authority_denied';
  END IF;
  SELECT coalesce(max(sequence),0) INTO v_sequence FROM omi_memory.chat_messages WHERE account_id=v_account;
  RETURN v_sequence;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_chat_snapshot_sequence() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_chat_snapshot_sequence() TO omi_platform_application;

CREATE FUNCTION omi_memory.read_chat_history(p_limit integer,p_snapshot_sequence bigint,p_older_created_at bigint,p_older_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_page jsonb;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'chat.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='chat_authority_denied';
  END IF;
  IF p_limit IS NULL OR p_limit<1 OR p_limit>100
    OR p_snapshot_sequence IS NULL OR p_snapshot_sequence<0
    OR (p_older_created_at IS NULL) IS DISTINCT FROM (p_older_id IS NULL)
    OR (p_older_id IS NOT NULL AND p_older_id='')
    OR (p_older_created_at IS NOT NULL AND p_older_created_at<0) THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='chat_history_invalid';
  END IF;
  WITH selected AS MATERIALIZED (
    SELECT m.id,m.text,m.sender,m.message_type,m.created_at,m.updated_at,m.chat_session_id,m.app_id,
      m.journal_revision,m.payload_hash,m.message_source,m.rating,m.reported,m.server_revision,m.attachments_json,m.generation_id
    FROM omi_memory.chat_messages m
    WHERE m.account_id=v_account AND m.app_id IS NULL AND m.chat_session_id IS NULL
      AND m.sequence<=p_snapshot_sequence
      AND (p_older_created_at IS NULL OR m.created_at<p_older_created_at OR (m.created_at=p_older_created_at AND m.id<p_older_id))
    ORDER BY m.created_at DESC, m.id DESC
    LIMIT p_limit+1
  )
  SELECT jsonb_build_object(
    'hasOlder',(SELECT count(*) FROM selected)>p_limit,
    'messages',coalesce((
      SELECT jsonb_agg(jsonb_build_object(
        'id',s.id,'text',s.text,'sender',s.sender,'type',s.message_type,'createdAt',s.created_at,'updatedAt',s.updated_at,
        'chatSessionId',s.chat_session_id,'appId',s.app_id,'journalRevision',s.journal_revision,'payloadHash',s.payload_hash,
        'messageSource',s.message_source,'rating',s.rating,'reported',s.reported,'revision',s.server_revision,
        'attachments',coalesce(s.attachments_json,'[]'::jsonb),'generationId',s.generation_id
      ) ORDER BY s.created_at DESC, s.id DESC)
      FROM (SELECT * FROM selected ORDER BY created_at DESC, id DESC LIMIT p_limit) s
    ),'[]'::jsonb)
  ) INTO v_page;
  RETURN v_page;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_chat_history(integer,bigint,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_chat_history(integer,bigint,bigint,text) TO omi_platform_application;

CREATE FUNCTION omi_memory.read_chat_message(p_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_row jsonb;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'chat.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='chat_authority_denied';
  END IF;
  IF p_id IS NULL OR p_id='' THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='chat_message_invalid';
  END IF;
  SELECT jsonb_build_object(
    'id',m.id,'text',m.text,'sender',m.sender,'type',m.message_type,'createdAt',m.created_at,'updatedAt',m.updated_at,
    'chatSessionId',m.chat_session_id,'appId',m.app_id,'journalRevision',m.journal_revision,'payloadHash',m.payload_hash,
    'messageSource',m.message_source,'rating',m.rating,'reported',m.reported,'revision',m.server_revision,
    'attachments',coalesce(m.attachments_json,'[]'::jsonb),'generationId',m.generation_id
  ) INTO v_row
  FROM omi_memory.chat_messages m
  WHERE m.account_id=v_account AND m.id=p_id;
  RETURN v_row;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_chat_message(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_chat_message(text) TO omi_platform_application;

CREATE FUNCTION omi_memory.read_chat_generation_events(p_generation_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_rows jsonb;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'chat.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='chat_authority_denied';
  END IF;
  IF p_generation_id IS NULL OR p_generation_id='' THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='chat_generation_invalid';
  END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object(
    'id',e.event_id,'generationId',e.generation_id,'sequence',e.sequence,'createdAt',e.created_at,'frame',e.frame_json
  ) ORDER BY e.sequence),'[]'::jsonb) INTO v_rows
  FROM omi_memory.chat_generation_events e
  WHERE e.account_id=v_account AND e.generation_id=p_generation_id;
  RETURN v_rows;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_chat_generation_events(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_chat_generation_events(text) TO omi_platform_application;

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
