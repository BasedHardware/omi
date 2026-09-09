DO $block$
DECLARE
  prior_last_id_constraint name;
BEGIN
  SELECT constraint_row.conname
    INTO prior_last_id_constraint
  FROM pg_catalog.pg_constraint AS constraint_row
  WHERE constraint_row.conrelid =
      'omi_memory.conversation_union_cursor_positions'::regclass
    AND constraint_row.contype = 'c'
    AND pg_catalog.pg_get_constraintdef(constraint_row.oid) LIKE '%last_id%'
    AND pg_catalog.pg_get_constraintdef(constraint_row.oid) LIKE '%[!-~]%';

  IF prior_last_id_constraint IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P6200', MESSAGE = 'conversation union last_id charset check unavailable';
  END IF;

  EXECUTE pg_catalog.format(
    'ALTER TABLE omi_memory.conversation_union_cursor_positions DROP CONSTRAINT %I',
    prior_last_id_constraint
  );
END;
$block$;

ALTER TABLE omi_memory.conversation_union_cursor_positions
  ADD CONSTRAINT conversation_union_cursor_positions_last_id_length_check
  CHECK(length(last_id) BETWEEN 1 AND 256);

CREATE OR REPLACE FUNCTION omi_memory.save_conversation_union_cursor(
  p_cursor_hash text,p_binding_digest text,p_revision bigint,p_chat_snapshot_sequence bigint,
  p_last_updated_at timestamptz,p_last_updated_at_ms bigint,p_last_id text,p_last_kind text,p_expires_at bigint
)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_now bigint:=floor(extract(epoch FROM clock_timestamp()));
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'conversations.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='conversation_authority_denied';
  END IF;
  IF p_cursor_hash IS NULL OR p_cursor_hash !~ '^[a-f0-9]{64}$' OR p_binding_digest IS NULL OR p_binding_digest !~ '^[a-f0-9]{64}$'
    OR p_chat_snapshot_sequence IS NULL OR p_chat_snapshot_sequence<0
    OR p_last_updated_at IS NULL OR p_last_updated_at_ms IS NULL OR p_last_updated_at_ms<0
    OR p_last_id IS NULL OR length(p_last_id) NOT BETWEEN 1 AND 256
    OR p_last_kind IS DISTINCT FROM 'listen' AND p_last_kind IS DISTINCT FROM 'chat'
    OR (p_last_kind='chat' AND (p_last_id NOT LIKE 'chat:%' OR length(p_last_id)<=5))
    OR (p_last_kind='listen' AND p_last_id LIKE 'chat:%')
    OR p_expires_at IS NULL OR p_expires_at<=v_now OR p_expires_at>v_now+900
    OR NOT EXISTS(SELECT 1 FROM omi_memory.listen_conversation_read_revisions WHERE account_id=v_account AND revision=p_revision)
    OR (
      p_last_kind='listen' AND NOT EXISTS(
        SELECT 1 FROM omi_memory.listen_capture_sessions s
        LEFT JOIN omi_memory.listen_capture_audio_uploads u USING(account_id,session_id)
        LEFT JOIN omi_memory.listen_conversation_finalization_intents i ON i.account_id=s.account_id AND i.conversation_id=s.conversation_id
        WHERE s.account_id=v_account AND (u.upload_completed_at IS NOT NULL OR i.finalization_id IS NOT NULL)
          AND CASE WHEN u.session_id IS NOT NULL THEN 'recording:'||s.session_id ELSE s.conversation_id END=p_last_id
      )
    )
    OR (
      p_last_kind='chat' AND NOT EXISTS(
        SELECT 1 FROM omi_memory.chat_messages m
        WHERE m.account_id=v_account AND m.app_id IS NULL
          AND CASE WHEN p_last_id='chat:chat-main'
            THEN (m.chat_session_id IS NULL OR length(btrim(m.chat_session_id))=0 OR btrim(m.chat_session_id)='chat-main')
            ELSE m.chat_session_id=substr(p_last_id,6)
          END
      )
    ) THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='conversation_cursor_invalid';
  END IF;
  DELETE FROM omi_memory.conversation_union_cursor_positions WHERE account_id=v_account AND cursor_hash IN (
    SELECT cursor_hash FROM omi_memory.conversation_union_cursor_positions WHERE account_id=v_account AND expires_at<=v_now ORDER BY expires_at LIMIT 256
  );
  IF NOT EXISTS(SELECT 1 FROM omi_memory.conversation_union_cursor_positions WHERE account_id=v_account AND cursor_hash=p_cursor_hash)
    AND EXISTS(SELECT 1 FROM omi_memory.conversation_union_cursor_positions WHERE account_id=v_account OFFSET 9999 LIMIT 1) THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='conversation_cursor_capacity';
  END IF;
  INSERT INTO omi_memory.conversation_union_cursor_positions(
    account_id,cursor_hash,binding_digest,revision,chat_snapshot_sequence,last_updated_at,last_updated_at_ms,last_id,last_kind,expires_at
  ) VALUES(
    v_account,p_cursor_hash,p_binding_digest,p_revision,p_chat_snapshot_sequence,p_last_updated_at,p_last_updated_at_ms,p_last_id,p_last_kind,p_expires_at
  ) ON CONFLICT(account_id,cursor_hash) DO NOTHING;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.save_conversation_union_cursor(text,text,bigint,bigint,timestamptz,bigint,text,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.save_conversation_union_cursor(text,text,bigint,bigint,timestamptz,bigint,text,text,bigint) TO omi_platform_application;
