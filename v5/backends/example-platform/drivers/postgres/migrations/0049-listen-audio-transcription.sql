CREATE TABLE omi_memory.listen_audio_transcriptions (
  account_id text NOT NULL,
  session_id text NOT NULL,
  state text NOT NULL CHECK(state IN ('queued','running','completed','failed')),
  lease_token uuid,
  lease_expires_at timestamptz,
  attempts integer NOT NULL CHECK(attempts BETWEEN 0 AND 5),
  available_at timestamptz NOT NULL,
  provider_result jsonb CHECK(provider_result IS NULL OR (jsonb_typeof(provider_result)='object' AND octet_length(provider_result::text)<=6291456)),
  discarded_leading_packets integer NOT NULL DEFAULT 0 CHECK(discarded_leading_packets>=0),
  error_code text CHECK(error_code IN ('transcription_unavailable','invalid_audio','invalid_transcript','attempt_limit')),
  updated_at timestamptz NOT NULL,
  PRIMARY KEY(account_id,session_id),
  FOREIGN KEY(account_id,session_id) REFERENCES omi_memory.listen_capture_audio_uploads(account_id,session_id)
);

CREATE FUNCTION omi_memory.read_listen_audio_transcription(p_session_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_result jsonb;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='listen_authority_denied';
  END IF;
  SELECT jsonb_build_object('sessionId',u.session_id,'state',coalesce(t.state,'queued'),
    'providerResult',t.provider_result,'discardedLeadingPackets',coalesce(t.discarded_leading_packets,0),
    'errorCode',t.error_code,'updatedAt',floor(extract(epoch FROM coalesce(t.updated_at,u.upload_completed_at,s.started_at))*1000),
    'startedAt',s.started_at,'codec',u.codec_id,'chunkCount',u.chunk_count,'byteCount',u.byte_count)
    INTO v_result FROM omi_memory.listen_capture_audio_uploads u
    JOIN omi_memory.listen_capture_sessions s USING(account_id,session_id)
    LEFT JOIN omi_memory.listen_audio_transcriptions t USING(account_id,session_id)
    WHERE u.account_id=v_account AND u.session_id=p_session_id;
  RETURN v_result;
END $function$;

CREATE FUNCTION omi_memory.claim_listen_audio_transcription(p_session_id text,p_token uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),'');
  v_upload omi_memory.listen_capture_audio_uploads%ROWTYPE;
  v_job omi_memory.listen_audio_transcriptions%ROWTYPE; v_owned boolean:=false;
BEGIN
  PERFORM omi_memory.read_listen_audio_transcription(p_session_id);
  SELECT * INTO v_upload FROM omi_memory.listen_capture_audio_uploads WHERE account_id=v_account AND session_id=p_session_id FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF v_upload.upload_completed_at IS NULL THEN RAISE EXCEPTION USING ERRCODE='P1001',MESSAGE='listen_audio_not_complete'; END IF;
  INSERT INTO omi_memory.listen_audio_transcriptions(account_id,session_id,state,attempts,available_at,updated_at)
    VALUES(v_account,p_session_id,'queued',0,clock_timestamp(),clock_timestamp()) ON CONFLICT DO NOTHING;
  SELECT * INTO STRICT v_job FROM omi_memory.listen_audio_transcriptions WHERE account_id=v_account AND session_id=p_session_id FOR UPDATE;
  IF v_job.provider_result IS NULL AND v_job.state IN ('queued','running') AND v_job.available_at<=clock_timestamp()
    AND (v_job.lease_expires_at IS NULL OR v_job.lease_expires_at<=clock_timestamp()) THEN
    IF v_job.attempts>=5 THEN
      UPDATE omi_memory.listen_audio_transcriptions SET state='failed',error_code='attempt_limit',lease_token=NULL,lease_expires_at=NULL,updated_at=clock_timestamp()
        WHERE account_id=v_account AND session_id=p_session_id;
    ELSE
      UPDATE omi_memory.listen_audio_transcriptions SET state='running',attempts=attempts+1,lease_token=p_token,
        lease_expires_at=clock_timestamp()+interval '180 seconds',updated_at=clock_timestamp()
        WHERE account_id=v_account AND session_id=p_session_id;
      v_owned:=true;
    END IF;
  END IF;
  RETURN omi_memory.read_listen_audio_transcription(p_session_id)||jsonb_build_object('owned',v_owned);
END $function$;

CREATE FUNCTION omi_memory.load_listen_transcription_audio(p_session_id text,p_token uuid)
RETURNS TABLE(chunk_index integer,bytes bytea) LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),'');
BEGIN
  PERFORM omi_memory.read_listen_audio_transcription(p_session_id);
  IF NOT EXISTS(SELECT 1 FROM omi_memory.listen_audio_transcriptions WHERE account_id=v_account AND session_id=p_session_id
    AND state='running' AND lease_token=p_token AND lease_expires_at>clock_timestamp()) THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='listen_transcription_stale_lease';
  END IF;
  RETURN QUERY SELECT c.chunk_index,c.bytes FROM omi_memory.listen_capture_audio_chunks c
    WHERE c.account_id=v_account AND c.session_id=p_session_id ORDER BY c.chunk_index;
END $function$;

CREATE FUNCTION omi_memory.save_listen_audio_transcription(p_session_id text,p_token uuid,p_result jsonb,p_discarded integer,p_error text,p_retry boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_count integer;
BEGIN
  PERFORM omi_memory.read_listen_audio_transcription(p_session_id);
  IF (p_result IS NULL)=(p_error IS NULL) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='listen_transcription_invalid'; END IF;
  UPDATE omi_memory.listen_audio_transcriptions SET provider_result=p_result,discarded_leading_packets=p_discarded,
    error_code=p_error,state=CASE WHEN p_result IS NOT NULL THEN 'running' WHEN p_retry AND attempts<5 THEN 'queued' ELSE 'failed' END,
    available_at=clock_timestamp()+interval '30 seconds',lease_token=NULL,lease_expires_at=NULL,updated_at=clock_timestamp()
    WHERE account_id=v_account AND session_id=p_session_id AND state='running' AND provider_result IS NULL
      AND lease_token=p_token AND lease_expires_at>clock_timestamp();
  GET DIAGNOSTICS v_count=ROW_COUNT;
  IF v_count<>1 THEN RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='listen_transcription_stale_lease'; END IF;
  RETURN omi_memory.read_listen_audio_transcription(p_session_id);
END $function$;

CREATE FUNCTION omi_memory.complete_listen_audio_transcription(p_session_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),'');
BEGIN
  PERFORM omi_memory.read_listen_audio_transcription(p_session_id);
  UPDATE omi_memory.listen_audio_transcriptions SET state='completed',updated_at=clock_timestamp()
    WHERE account_id=v_account AND session_id=p_session_id AND state='running' AND provider_result IS NOT NULL
      AND (jsonb_array_length(provider_result->'segments')=0 OR EXISTS(
        SELECT 1 FROM omi_memory.listen_formation_finalizations f WHERE f.account_id=v_account AND f.session_id=p_session_id));
  RETURN omi_memory.read_listen_audio_transcription(p_session_id);
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_listen_audio_transcription(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.claim_listen_audio_transcription(text,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.load_listen_transcription_audio(text,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.save_listen_audio_transcription(text,uuid,jsonb,integer,text,boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.complete_listen_audio_transcription(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_audio_transcription(text) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.claim_listen_audio_transcription(text,uuid) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.load_listen_transcription_audio(text,uuid) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.save_listen_audio_transcription(text,uuid,jsonb,integer,text,boolean) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.complete_listen_audio_transcription(text) TO omi_platform_application;

CREATE OR REPLACE FUNCTION omi_memory.cleanup_surface_tables(p_surface text)
RETURNS TABLE(table_name text)
LANGUAGE sql
IMMUTABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT mapping.table_name
  FROM (VALUES
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
