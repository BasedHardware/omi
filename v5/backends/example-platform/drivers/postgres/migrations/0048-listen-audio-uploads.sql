CREATE TABLE omi_memory.listen_capture_audio_uploads (
  account_id text NOT NULL,
  session_id text NOT NULL,
  capture_id uuid NOT NULL,
  device_id text NOT NULL CHECK (length(device_id) BETWEEN 1 AND 128),
  device_name text CHECK (length(device_name) BETWEEN 1 AND 256),
  codec_id integer NOT NULL CHECK (codec_id BETWEEN 0 AND 255),
  byte_count bigint NOT NULL DEFAULT 0 CHECK (byte_count BETWEEN 0 AND 8388608),
  chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count BETWEEN 0 AND 65536),
  upload_completed_at timestamptz,
  PRIMARY KEY (account_id, session_id),
  UNIQUE (account_id, capture_id),
  FOREIGN KEY (account_id, session_id) REFERENCES omi_memory.listen_capture_sessions(account_id,session_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE omi_memory.listen_capture_audio_chunks (
  account_id text NOT NULL,
  session_id text NOT NULL,
  chunk_index integer NOT NULL CHECK (chunk_index BETWEEN 0 AND 65535),
  bytes bytea NOT NULL CHECK (octet_length(bytes) BETWEEN 1 AND 1048576),
  PRIMARY KEY (account_id, session_id, chunk_index),
  FOREIGN KEY (account_id,session_id) REFERENCES omi_memory.listen_capture_audio_uploads(account_id,session_id)
);

CREATE FUNCTION omi_memory.read_listen_audio_upload(p_session_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,omi_memory AS $function$
DECLARE v_account_id text := nullif(current_setting('omi.account_id',true),''); v_result jsonb;
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE='P1005', MESSAGE='listen_authority_denied';
  END IF;
  SELECT jsonb_build_object('id',u.session_id,'deviceId',u.device_id,'deviceName',u.device_name,
    'codec',u.codec_id,'state',CASE WHEN u.upload_completed_at IS NULL THEN 'open' ELSE 'complete' END,
    'byteCount',u.byte_count,'chunkCount',u.chunk_count,
    'startedAt',floor(extract(epoch FROM s.started_at)),
    'endedAt',floor(extract(epoch FROM u.upload_completed_at))) INTO v_result
  FROM omi_memory.listen_capture_audio_uploads u JOIN omi_memory.listen_capture_sessions s USING(account_id,session_id)
  WHERE u.account_id=v_account_id AND u.session_id=p_session_id;
  RETURN v_result;
END $function$;

CREATE FUNCTION omi_memory.open_listen_audio_upload(
  p_capture_id uuid,p_device_id text,p_device_name text,p_codec_id integer,
  p_session_id text,p_conversation_id text,p_started_at timestamptz,p_codec text,p_sample_rate integer,
  p_session_hash text,p_state_hash text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,omi_memory AS $function$
DECLARE v_account_id text := nullif(current_setting('omi.account_id',true),'');
  v_existing omi_memory.listen_capture_audio_uploads%ROWTYPE; v_inserted integer;
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE='P1005', MESSAGE='listen_authority_denied';
  END IF;
  INSERT INTO omi_memory.listen_capture_audio_uploads(account_id,session_id,capture_id,device_id,device_name,codec_id)
    VALUES(v_account_id,p_session_id,p_capture_id,p_device_id,p_device_name,p_codec_id)
    ON CONFLICT(account_id,capture_id) DO NOTHING;
  GET DIAGNOSTICS v_inserted=ROW_COUNT;
  SELECT * INTO STRICT v_existing FROM omi_memory.listen_capture_audio_uploads
    WHERE account_id=v_account_id AND capture_id=p_capture_id FOR UPDATE;
  IF v_existing.device_id IS DISTINCT FROM p_device_id OR v_existing.device_name IS DISTINCT FROM p_device_name
    OR v_existing.codec_id IS DISTINCT FROM p_codec_id THEN
    RAISE EXCEPTION USING ERRCODE='P1001', MESSAGE='listen_session_conflict';
  END IF;
  IF v_inserted=1 THEN
    PERFORM omi_memory.open_listen_capture_session(p_session_id,p_conversation_id,p_capture_id::text,
      p_started_at,'omi-device',p_codec,p_sample_rate,1,p_session_hash,p_state_hash);
  END IF;
  RETURN omi_memory.read_listen_audio_upload(v_existing.session_id);
END $function$;

CREATE FUNCTION omi_memory.append_listen_audio_upload(p_session_id text,p_chunk_index integer,p_bytes bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,omi_memory AS $function$
DECLARE v_account_id text := nullif(current_setting('omi.account_id',true),'');
  v_upload omi_memory.listen_capture_audio_uploads%ROWTYPE; v_bytes bytea; v_state text;
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE='P1005', MESSAGE='listen_authority_denied';
  END IF;
  PERFORM 1 FROM omi_memory.listen_capture_sessions WHERE account_id=v_account_id AND session_id=p_session_id FOR UPDATE;
  SELECT * INTO v_upload FROM omi_memory.listen_capture_audio_uploads
    WHERE account_id=v_account_id AND session_id=p_session_id FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF p_chunk_index IS NULL OR p_chunk_index<0 OR p_chunk_index>=65536 OR p_bytes IS NULL
    OR octet_length(p_bytes)<1 OR octet_length(p_bytes)>1048576 THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='listen_audio_invalid';
  END IF;
  SELECT bytes INTO v_bytes FROM omi_memory.listen_capture_audio_chunks
    WHERE account_id=v_account_id AND session_id=p_session_id AND chunk_index=p_chunk_index;
  IF FOUND THEN
    IF v_bytes IS DISTINCT FROM p_bytes THEN RAISE EXCEPTION USING ERRCODE='P1001', MESSAGE='listen_audio_conflict'; END IF;
    RETURN omi_memory.read_listen_audio_upload(p_session_id);
  END IF;
  SELECT state INTO v_state FROM omi_memory.listen_capture_session_state_revisions
    WHERE account_id=v_account_id AND session_id=p_session_id ORDER BY state_sequence DESC LIMIT 1;
  IF v_upload.upload_completed_at IS NOT NULL OR p_chunk_index<>v_upload.chunk_count OR v_state IS DISTINCT FROM 'active' THEN
    RAISE EXCEPTION USING ERRCODE='P1001', MESSAGE='listen_audio_conflict';
  END IF;
  IF v_upload.byte_count+octet_length(p_bytes)>8388608 THEN
    RAISE EXCEPTION USING ERRCODE='P1001', MESSAGE='listen_audio_too_large';
  END IF;
  INSERT INTO omi_memory.listen_capture_audio_chunks VALUES(v_account_id,p_session_id,p_chunk_index,p_bytes);
  UPDATE omi_memory.listen_capture_audio_uploads SET byte_count=byte_count+octet_length(p_bytes),chunk_count=chunk_count+1
    WHERE account_id=v_account_id AND session_id=p_session_id;
  RETURN omi_memory.read_listen_audio_upload(p_session_id);
END $function$;

CREATE FUNCTION omi_memory.complete_listen_audio_upload(p_session_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,omi_memory AS $function$
DECLARE v_account_id text := nullif(current_setting('omi.account_id',true),'');
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE='P1005', MESSAGE='listen_authority_denied';
  END IF;
  UPDATE omi_memory.listen_capture_audio_uploads SET upload_completed_at=coalesce(upload_completed_at,transaction_timestamp())
    WHERE account_id=v_account_id AND session_id=p_session_id;
  RETURN omi_memory.read_listen_audio_upload(p_session_id);
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_listen_audio_upload(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.open_listen_audio_upload(uuid,text,text,integer,text,text,timestamptz,text,integer,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.append_listen_audio_upload(text,integer,bytea) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.complete_listen_audio_upload(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_audio_upload(text) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.open_listen_audio_upload(uuid,text,text,integer,text,text,timestamptz,text,integer,text,text) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.append_listen_audio_upload(text,integer,bytea) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.complete_listen_audio_upload(text) TO omi_platform_application;

CREATE FUNCTION omi_memory.guard_listen_audio_upload_completion()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,omi_memory AS $function$
DECLARE v_completed timestamptz;
BEGIN
  SELECT upload_completed_at INTO v_completed FROM omi_memory.listen_capture_audio_uploads
    WHERE account_id=NEW.account_id AND session_id=NEW.session_id FOR UPDATE;
  IF FOUND AND v_completed IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P1002', MESSAGE='listen_audio_not_complete';
  END IF;
  RETURN NEW;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.guard_listen_audio_upload_completion() FROM PUBLIC;
CREATE TRIGGER listen_audio_completion_guard BEFORE INSERT ON omi_memory.listen_capture_session_state_revisions
  FOR EACH ROW WHEN (NEW.state IN ('completed','entitlement_exhausted')) EXECUTE FUNCTION omi_memory.guard_listen_audio_upload_completion();

CREATE OR REPLACE FUNCTION omi_memory.cleanup_surface_tables(p_surface text)
RETURNS TABLE(table_name text)
LANGUAGE sql
IMMUTABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT mapping.table_name
  FROM (VALUES
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
