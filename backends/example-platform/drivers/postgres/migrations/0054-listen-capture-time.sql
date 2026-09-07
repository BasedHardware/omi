ALTER TABLE omi_memory.listen_capture_audio_uploads ADD COLUMN captured_at_ms bigint
  CHECK(captured_at_ms>=0 AND captured_at_ms<=8640000000000000);
DROP FUNCTION omi_memory.open_listen_audio_upload(uuid,text,text,integer,text,text,timestamptz,text,integer,text,text);

CREATE OR REPLACE FUNCTION omi_memory.read_listen_audio_upload(p_session_id text)
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
    'startedAt',floor(extract(epoch FROM s.started_at)*1000),
    'endedAt',floor(extract(epoch FROM u.upload_completed_at)*1000))
    || CASE WHEN u.captured_at_ms IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('capturedAtMs',u.captured_at_ms) END INTO v_result
  FROM omi_memory.listen_capture_audio_uploads u JOIN omi_memory.listen_capture_sessions s USING(account_id,session_id)
  WHERE u.account_id=v_account_id AND u.session_id=p_session_id;
  RETURN v_result;
END $function$;

CREATE FUNCTION omi_memory.open_listen_audio_upload(
  p_capture_id uuid,p_device_id text,p_device_name text,p_codec_id integer,
  p_session_id text,p_conversation_id text,p_started_at timestamptz,p_codec text,p_sample_rate integer,
  p_session_hash text,p_state_hash text,p_captured_at_ms bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,omi_memory AS $function$
DECLARE v_account_id text := nullif(current_setting('omi.account_id',true),'');
  v_existing omi_memory.listen_capture_audio_uploads%ROWTYPE; v_inserted integer;
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE='P1005', MESSAGE='listen_authority_denied';
  END IF;
  IF p_captured_at_ms IS NOT NULL AND (p_captured_at_ms<0 OR p_captured_at_ms>8640000000000000) THEN
    RAISE EXCEPTION USING ERRCODE='22023', MESSAGE='listen_capture_time_invalid';
  END IF;
  INSERT INTO omi_memory.listen_capture_audio_uploads(account_id,session_id,capture_id,device_id,device_name,codec_id,captured_at_ms)
    VALUES(v_account_id,p_session_id,p_capture_id,p_device_id,p_device_name,p_codec_id,p_captured_at_ms)
    ON CONFLICT(account_id,capture_id) DO NOTHING;
  GET DIAGNOSTICS v_inserted=ROW_COUNT;
  SELECT * INTO STRICT v_existing FROM omi_memory.listen_capture_audio_uploads
    WHERE account_id=v_account_id AND capture_id=p_capture_id FOR UPDATE;
  PERFORM omi_memory.assert_listen_audio_upload_epoch(v_existing.session_id);
  IF v_existing.device_id IS DISTINCT FROM p_device_id OR v_existing.device_name IS DISTINCT FROM p_device_name
    OR v_existing.codec_id IS DISTINCT FROM p_codec_id OR v_existing.captured_at_ms IS DISTINCT FROM p_captured_at_ms THEN
    RAISE EXCEPTION USING ERRCODE='P1001', MESSAGE='listen_session_conflict';
  END IF;
  IF v_inserted=1 THEN
    PERFORM omi_memory.open_listen_capture_session(p_session_id,p_conversation_id,p_capture_id::text,
      p_started_at,'omi-device',p_codec,p_sample_rate,1,p_session_hash,p_state_hash);
  END IF;
  RETURN omi_memory.read_listen_audio_upload(v_existing.session_id);
END $function$;

REVOKE ALL ON FUNCTION omi_memory.open_listen_audio_upload(uuid,text,text,integer,text,text,timestamptz,text,integer,text,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.open_listen_audio_upload(uuid,text,text,integer,text,text,timestamptz,text,integer,text,text,bigint) TO omi_platform_application;

CREATE OR REPLACE FUNCTION omi_memory.read_listen_conversation_page(p_limit integer,p_cursor_hash text,p_binding_digest text,p_revision bigint)
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
      u.captured_at_ms,s.started_at,coalesce(u.upload_completed_at,f.ended_at) AS ended_at,
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
