CREATE FUNCTION omi_memory.read_chat_history(p_limit integer,p_snapshot_sequence bigint,p_older_created_at bigint,p_older_id text,p_chat_session_id text)
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
    OR (p_older_created_at IS NOT NULL AND p_older_created_at<0)
    OR (p_chat_session_id IS NOT NULL AND (length(p_chat_session_id)=0 OR length(p_chat_session_id)>128)) THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='chat_history_invalid';
  END IF;
  WITH selected AS MATERIALIZED (
    SELECT m.id,m.text,m.sender,m.message_type,m.created_at,m.updated_at,m.chat_session_id,m.app_id,
      m.journal_revision,m.payload_hash,m.message_source,m.rating,m.reported,m.server_revision,m.attachments_json,m.generation_id
    FROM omi_memory.chat_messages m
    WHERE m.account_id=v_account AND m.app_id IS NULL
      AND CASE WHEN p_chat_session_id IS NULL
        THEN (m.chat_session_id IS NULL OR length(btrim(m.chat_session_id))=0)
        ELSE m.chat_session_id=p_chat_session_id
      END
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
REVOKE ALL ON FUNCTION omi_memory.read_chat_history(integer,bigint,bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_chat_history(integer,bigint,bigint,text,text) TO omi_platform_application;

CREATE OR REPLACE FUNCTION omi_memory.read_chat_conversation_sessions()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_sessions jsonb;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'chat.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='chat_authority_denied';
  END IF;
  SELECT coalesce(jsonb_agg(to_jsonb(session) ORDER BY session."updatedAt" DESC, session.id),'[]'::jsonb)
  INTO v_sessions
  FROM (
    SELECT
      CASE
        WHEN chat_session_id IS NULL OR length(btrim(chat_session_id))=0 THEN 'chat:chat-main'
        ELSE 'chat:' || chat_session_id
      END AS id,
      CASE
        WHEN length(btrim(title_text))=0 THEN 'Chat'
        WHEN char_length(btrim(title_text))>240 THEN left(btrim(title_text),237)||'...'
        ELSE btrim(title_text)
      END AS title,
      CASE
        WHEN length(btrim(last_text))=0 THEN 'Chat'
        WHEN char_length(btrim(last_text))>240 THEN left(btrim(last_text),237)||'...'
        ELSE btrim(last_text)
      END AS overview,
      created_at AS "createdAt",
      updated_at AS "updatedAt",
      created_at AS "startedAt",
      NULL::bigint AS "finishedAt",
      'chat'::text AS source,
      'in_progress'::text AS status,
      false AS discarded,
      false AS starred,
      'private'::text AS visibility,
      false AS "isLocked",
      NULL::text AS "folderId",
      NULL::text AS revision
    FROM (
      SELECT
        CASE
          WHEN m.chat_session_id IS NULL OR length(btrim(m.chat_session_id))=0 THEN NULL
          ELSE m.chat_session_id
        END AS chat_session_id,
        min(m.created_at) AS created_at,
        max(m.created_at) AS updated_at,
        (array_agg(m.text ORDER BY CASE WHEN m.sender='human' THEN 0 ELSE 1 END, m.created_at, m.id))[1] AS title_text,
        (array_agg(m.text ORDER BY m.created_at DESC, m.id DESC))[1] AS last_text,
        count(*) AS n
      FROM omi_memory.chat_messages m
      WHERE m.account_id=v_account AND m.app_id IS NULL
      GROUP BY 1
    ) AS aggregated
    WHERE n>0
  ) AS session;
  RETURN v_sessions;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_chat_conversation_sessions() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_chat_conversation_sessions() TO omi_platform_application;
