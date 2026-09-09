CREATE OR REPLACE FUNCTION omi_memory.read_listen_conversation_page(p_limit integer,p_cursor_hash text,p_binding_digest text,p_revision bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_revision bigint; v_after bigint:=0; v_records jsonb;
  v_ws text:=chr(9)||chr(10)||chr(11)||chr(12)||chr(13)||chr(32)||chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||chr(8239)||chr(8287)||chr(12288)||chr(65279);
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
        SELECT coalesce(left(btrim(string_agg(left(btrim(segment.text_content,v_ws),240),' ' ORDER BY segment.ordinal),v_ws),240),'')
        FROM omi_memory.listen_capture_segments segment
        WHERE segment.account_id=s.account_id AND segment.session_id=s.session_id AND segment.ordinal<240
      ) WHEN t.state='completed' AND jsonb_typeof(t.provider_result->'segments')='array' THEN (
        SELECT coalesce(left(btrim(string_agg(left(btrim(segment.value->>'text',v_ws),240),' ' ORDER BY segment.ordinal),v_ws),240),'')
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

CREATE OR REPLACE FUNCTION omi_memory.read_listen_conversation_union_page(p_limit integer,p_cursor_hash text,p_binding_digest text,p_revision bigint,p_chat_snapshot_sequence bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_revision bigint;
  v_after_id text:=NULL; v_after_updated_at timestamptz:=NULL; v_after_updated_at_ms bigint:=NULL; v_records jsonb;
  v_ws text:=chr(9)||chr(10)||chr(11)||chr(12)||chr(13)||chr(32)||chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||chr(8239)||chr(8287)||chr(12288)||chr(65279);
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'conversations.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='conversation_authority_denied';
  END IF;
  IF p_limit IS NULL OR p_limit<0 OR p_limit>10000 OR p_binding_digest IS NULL OR p_binding_digest !~ '^[a-f0-9]{64}$'
    OR p_chat_snapshot_sequence IS NULL OR p_chat_snapshot_sequence<0
    OR (p_cursor_hash IS NOT NULL AND p_cursor_hash !~ '^[a-f0-9]{64}$') THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='conversation_page_invalid';
  END IF;
  SELECT coalesce(revision,0) INTO v_revision FROM omi_memory.listen_conversation_read_revisions WHERE account_id=v_account;
  v_revision:=coalesce(v_revision,0);
  IF p_revision IS DISTINCT FROM v_revision THEN RETURN NULL; END IF;
  IF p_cursor_hash IS NOT NULL THEN
    SELECT last_updated_at,last_updated_at_ms,last_id INTO v_after_updated_at,v_after_updated_at_ms,v_after_id
    FROM omi_memory.conversation_union_cursor_positions
    WHERE account_id=v_account AND cursor_hash=p_cursor_hash AND binding_digest=p_binding_digest AND revision=v_revision
      AND chat_snapshot_sequence=p_chat_snapshot_sequence
      AND expires_at>floor(extract(epoch FROM clock_timestamp()));
    IF v_after_id IS NULL THEN RETURN NULL; END IF;
  END IF;
  WITH selected AS MATERIALIZED (
    SELECT s.account_id,s.session_id FROM omi_memory.listen_capture_sessions s
    LEFT JOIN omi_memory.listen_capture_audio_uploads u USING(account_id,session_id)
    LEFT JOIN omi_memory.listen_audio_transcriptions t USING(account_id,session_id)
    LEFT JOIN omi_memory.listen_conversation_finalization_intents i ON i.account_id=s.account_id AND i.conversation_id=s.conversation_id
    LEFT JOIN omi_memory.listen_formation_finalizations f ON f.account_id=s.account_id AND f.session_id=s.session_id
    WHERE s.account_id=v_account AND (u.upload_completed_at IS NOT NULL OR i.finalization_id IS NOT NULL)
      AND (
        v_after_id IS NULL
        OR coalesce(t.updated_at,u.upload_completed_at,f.ended_at)<v_after_updated_at
        OR (
          coalesce(t.updated_at,u.upload_completed_at,f.ended_at)=v_after_updated_at
          AND CASE WHEN u.session_id IS NOT NULL THEN 'recording:'||s.session_id ELSE s.conversation_id END>v_after_id
        )
      )
    ORDER BY coalesce(t.updated_at,u.upload_completed_at,f.ended_at) DESC,
      CASE WHEN u.session_id IS NOT NULL THEN 'recording:'||s.session_id ELSE s.conversation_id END ASC
    LIMIT p_limit
  ) SELECT coalesce(jsonb_agg(to_jsonb(record) ORDER BY record.sequence),'[]'::jsonb) INTO v_records FROM (
    SELECT s.conversation_sequence AS sequence,s.session_id,s.conversation_id,s.source,u.session_id IS NOT NULL AS device,
      u.captured_at_ms,s.started_at,coalesce(u.upload_completed_at,f.ended_at) AS ended_at,
      coalesce(t.updated_at,u.upload_completed_at,f.ended_at) AS updated_at,
      CASE WHEN u.session_id IS NULL THEN 'completed' ELSE coalesce(t.state,'queued') END AS state,
      coalesce(i.locked,false) AS locked,
      CASE WHEN u.session_id IS NULL THEN (
        SELECT coalesce(left(btrim(string_agg(left(btrim(segment.text_content,v_ws),240),' ' ORDER BY segment.ordinal),v_ws),240),'')
        FROM omi_memory.listen_capture_segments segment
        WHERE segment.account_id=s.account_id AND segment.session_id=s.session_id AND segment.ordinal<240
      ) WHEN t.state='completed' AND jsonb_typeof(t.provider_result->'segments')='array' THEN (
        SELECT coalesce(left(btrim(string_agg(left(btrim(segment.value->>'text',v_ws),240),' ' ORDER BY segment.ordinal),v_ws),240),'')
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
  RETURN jsonb_build_object(
    'revision',v_revision,
    'records',v_records,
    'after',CASE WHEN v_after_id IS NULL THEN NULL ELSE jsonb_build_object('updatedAt',v_after_updated_at_ms,'id',v_after_id) END
  );
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_listen_conversation_union_page(integer,text,text,bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_conversation_union_page(integer,text,text,bigint,bigint) TO omi_platform_application;
