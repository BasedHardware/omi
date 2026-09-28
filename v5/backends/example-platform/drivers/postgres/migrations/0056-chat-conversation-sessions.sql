CREATE FUNCTION omi_memory.read_chat_conversation_sessions()
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
      'chat:chat-main'::text AS id,
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
        min(m.created_at) AS created_at,
        max(m.created_at) AS updated_at,
        (array_agg(m.text ORDER BY CASE WHEN m.sender='human' THEN 0 ELSE 1 END, m.created_at, m.id))[1] AS title_text,
        (array_agg(m.text ORDER BY m.created_at DESC, m.id DESC))[1] AS last_text,
        count(*) AS n
      FROM omi_memory.chat_messages m
      WHERE m.account_id=v_account AND m.app_id IS NULL AND m.chat_session_id IS NULL
    ) AS aggregated
    WHERE n>0
  ) AS session;
  RETURN v_sessions;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_chat_conversation_sessions() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_chat_conversation_sessions() TO omi_platform_application;
