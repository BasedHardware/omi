-- P3 inert Listen capture/finalization authority. The application role receives
-- fixed named operations only; no table access, route, worker, or default is
-- activated by this migration.

CREATE TABLE omi_memory.listen_capture_sessions (
  account_id text NOT NULL,
  session_id text NOT NULL CHECK (length(session_id) BETWEEN 1 AND 256 AND session_id ~ '^[!-~]+$'),
  conversation_id text NOT NULL CHECK (length(conversation_id) BETWEEN 1 AND 256 AND conversation_id ~ '^[!-~]+$'),
  client_conversation_id text CHECK (
    length(client_conversation_id) BETWEEN 1 AND 256 AND client_conversation_id ~ '^[!-~]+$'
  ),
  started_at timestamptz NOT NULL,
  source text CHECK (length(source) <= 256 AND source ~ '^[ -~]*$'),
  codec text NOT NULL CHECK (length(codec) BETWEEN 1 AND 256 AND codec ~ '^[!-~]+$'),
  sample_rate integer NOT NULL CHECK (sample_rate > 0),
  channels integer NOT NULL CHECK (channels > 0),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, session_id),
  UNIQUE (account_id, conversation_id),
  UNIQUE (account_id, client_conversation_id),
  FOREIGN KEY (account_id) REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.listen_capture_session_state_revisions (
  account_id text NOT NULL,
  session_id text NOT NULL,
  state_sequence bigint NOT NULL CHECK (state_sequence >= 0),
  state text NOT NULL CHECK (state IN (
    'active', 'interrupted', 'completed', 'entitlement_exhausted'
  )),
  event_at timestamptz NOT NULL,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, session_id, state_sequence),
  UNIQUE (account_id, session_id, state, event_at),
  FOREIGN KEY (account_id, session_id)
    REFERENCES omi_memory.listen_capture_sessions (account_id, session_id)
);

CREATE TABLE omi_memory.listen_capture_segments (
  account_id text NOT NULL,
  session_id text NOT NULL,
  ordinal bigint NOT NULL CHECK (ordinal >= 0),
  segment_id text NOT NULL CHECK (length(segment_id) BETWEEN 1 AND 256 AND segment_id ~ '^[!-~]+$'),
  text_content text NOT NULL CHECK (length(text_content) BETWEEN 1 AND 1500),
  is_user boolean NOT NULL,
  start_seconds double precision NOT NULL CHECK (
    start_seconds >= 0 AND start_seconds::text NOT IN ('NaN', 'Infinity', '-Infinity')
  ),
  end_seconds double precision NOT NULL CHECK (
    end_seconds >= start_seconds AND end_seconds::text NOT IN ('NaN', 'Infinity', '-Infinity')
  ),
  appended_at timestamptz NOT NULL,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, session_id, ordinal),
  UNIQUE (account_id, segment_id),
  FOREIGN KEY (account_id, session_id)
    REFERENCES omi_memory.listen_capture_sessions (account_id, session_id)
);

CREATE TABLE omi_memory.listen_formation_finalizations (
  account_id text NOT NULL,
  finalization_id text NOT NULL CHECK (
    length(finalization_id) BETWEEN 1 AND 256 AND finalization_id ~ '^[!-~]+$'
  ),
  formation_work_id text NOT NULL CHECK (
    length(formation_work_id) BETWEEN 1 AND 256 AND formation_work_id ~ '^[!-~]+$'
  ),
  session_id text NOT NULL,
  conversation_id text NOT NULL,
  terminal_status text NOT NULL CHECK (terminal_status IN (
    'completed', 'entitlement_exhausted'
  )),
  capture_completeness text NOT NULL,
  started_at timestamptz NOT NULL,
  ended_at timestamptz NOT NULL CHECK (ended_at >= started_at),
  source text CHECK (length(source) <= 256 AND source ~ '^[ -~]*$'),
  segment_count bigint NOT NULL CHECK (segment_count > 0),
  transcript_digest text NOT NULL CHECK (transcript_digest ~ '^[0-9a-f]{64}$'),
  finalization_digest text NOT NULL CHECK (finalization_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  CHECK (
    (terminal_status = 'completed' AND capture_completeness = 'complete')
    OR (terminal_status = 'entitlement_exhausted'
      AND capture_completeness = 'incomplete_entitlement_exhausted')
  ),
  PRIMARY KEY (account_id, finalization_id),
  UNIQUE (account_id, formation_work_id),
  UNIQUE (account_id, session_id),
  FOREIGN KEY (account_id, session_id)
    REFERENCES omi_memory.listen_capture_sessions (account_id, session_id),
  FOREIGN KEY (account_id, conversation_id)
    REFERENCES omi_memory.listen_capture_sessions (account_id, conversation_id)
);

CREATE TABLE omi_memory.listen_conversation_finalization_intents (
  account_id text NOT NULL,
  conversation_id text NOT NULL,
  finalization_id text NOT NULL,
  intent text NOT NULL CHECK (intent = 'process_memories'),
  locked boolean NOT NULL CHECK (locked),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, conversation_id),
  UNIQUE (account_id, finalization_id),
  FOREIGN KEY (account_id, finalization_id)
    REFERENCES omi_memory.listen_formation_finalizations (account_id, finalization_id)
);

CREATE TABLE omi_memory.listen_formation_outbox (
  account_id text NOT NULL,
  outbox_id text NOT NULL CHECK (length(outbox_id) BETWEEN 1 AND 256 AND outbox_id ~ '^[!-~]+$'),
  finalization_id text NOT NULL,
  formation_work_id text NOT NULL,
  state text NOT NULL CHECK (state = 'pending'),
  finalization_digest text NOT NULL CHECK (finalization_digest ~ '^[0-9a-f]{64}$'),
  payload_digest text NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, outbox_id),
  UNIQUE (account_id, finalization_id),
  UNIQUE (account_id, formation_work_id),
  FOREIGN KEY (account_id, finalization_id)
    REFERENCES omi_memory.listen_formation_finalizations (account_id, finalization_id)
);

REVOKE ALL ON omi_memory.listen_capture_sessions FROM PUBLIC;
REVOKE ALL ON omi_memory.listen_capture_session_state_revisions FROM PUBLIC;
REVOKE ALL ON omi_memory.listen_capture_segments FROM PUBLIC;
REVOKE ALL ON omi_memory.listen_formation_finalizations FROM PUBLIC;
REVOKE ALL ON omi_memory.listen_conversation_finalization_intents FROM PUBLIC;
REVOKE ALL ON omi_memory.listen_formation_outbox FROM PUBLIC;

CREATE FUNCTION omi_memory.open_listen_capture_session(
  p_session_id text,
  p_conversation_id text,
  p_client_conversation_id text,
  p_started_at timestamptz,
  p_source text,
  p_codec text,
  p_sample_rate integer,
  p_channels integer,
  p_session_content_hash text,
  p_state_content_hash text
)
RETURNS TABLE(result text, session_id text, conversation_id text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
  v_capability text := nullif(current_setting('omi.capability', true), '');
  v_existing omi_memory.listen_capture_sessions%ROWTYPE;
  v_state text;
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id', true), '') IS NULL
    OR v_capability IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_authority_denied';
  END IF;
  SELECT * INTO v_existing
  FROM omi_memory.listen_capture_sessions s
  WHERE s.account_id = v_account_id AND s.session_id = p_session_id
  FOR UPDATE;
  IF FOUND THEN
    IF v_existing.conversation_id <> p_conversation_id
      OR v_existing.client_conversation_id IS DISTINCT FROM p_client_conversation_id
      OR v_existing.started_at <> p_started_at OR v_existing.source IS DISTINCT FROM p_source
      OR v_existing.codec <> p_codec OR v_existing.sample_rate <> p_sample_rate
      OR v_existing.channels <> p_channels OR v_existing.content_hash <> p_session_content_hash THEN
      RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'listen_session_conflict';
    END IF;
    SELECT sr.state INTO STRICT v_state
    FROM omi_memory.listen_capture_session_state_revisions sr
    WHERE sr.account_id = v_account_id AND sr.session_id = p_session_id
    ORDER BY sr.state_sequence DESC LIMIT 1;
    IF v_state <> 'active' THEN
      RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_session_not_active';
    END IF;
    RETURN QUERY SELECT 'replayed'::text, p_session_id, p_conversation_id;
    RETURN;
  END IF;
  BEGIN
    INSERT INTO omi_memory.listen_capture_sessions
      (account_id, session_id, conversation_id, client_conversation_id, started_at,
       source, codec, sample_rate, channels, content_hash)
    VALUES (v_account_id, p_session_id, p_conversation_id, p_client_conversation_id,
            p_started_at, p_source, p_codec, p_sample_rate, p_channels, p_session_content_hash);
    INSERT INTO omi_memory.listen_capture_session_state_revisions
      (account_id, session_id, state_sequence, state, event_at, content_hash)
    VALUES (v_account_id, p_session_id, 0, 'active', p_started_at, p_state_content_hash);
  EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'listen_session_conflict';
  END;
  RETURN QUERY SELECT 'opened'::text, p_session_id, p_conversation_id;
END
$function$;

CREATE FUNCTION omi_memory.append_listen_capture_segment(
  p_session_id text,
  p_segment_id text,
  p_text_content text,
  p_is_user boolean,
  p_start_seconds double precision,
  p_end_seconds double precision,
  p_appended_at timestamptz,
  p_content_hash text
)
RETURNS TABLE(result text, segment_id text, ordinal bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
  v_existing omi_memory.listen_capture_segments%ROWTYPE;
  v_state text;
  v_ordinal bigint;
  v_segment_count bigint;
  v_text_bytes bigint;
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id', true), '') IS NULL
    OR nullif(current_setting('omi.capability', true), '') IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_authority_denied';
  END IF;
  PERFORM 1 FROM omi_memory.listen_capture_sessions s
  WHERE s.account_id = v_account_id AND s.session_id = p_session_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_session_missing';
  END IF;
  SELECT * INTO v_existing FROM omi_memory.listen_capture_segments seg
  WHERE seg.account_id = v_account_id AND seg.segment_id = p_segment_id;
  IF FOUND THEN
    IF v_existing.session_id <> p_session_id
      OR v_existing.text_content <> p_text_content OR v_existing.is_user <> p_is_user
      OR v_existing.start_seconds <> p_start_seconds OR v_existing.end_seconds <> p_end_seconds
      OR v_existing.appended_at <> p_appended_at OR v_existing.content_hash <> p_content_hash THEN
      RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'listen_segment_conflict';
    END IF;
    RETURN QUERY SELECT 'replayed'::text, p_segment_id, v_existing.ordinal;
    RETURN;
  END IF;
  SELECT sr.state INTO STRICT v_state
  FROM omi_memory.listen_capture_session_state_revisions sr
  WHERE sr.account_id = v_account_id AND sr.session_id = p_session_id
  ORDER BY sr.state_sequence DESC LIMIT 1;
  IF v_state <> 'active' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_session_not_active';
  END IF;
  SELECT count(*), COALESCE(sum(octet_length(seg.text_content)), 0)
    INTO v_segment_count, v_text_bytes
  FROM omi_memory.listen_capture_segments seg
  WHERE seg.account_id = v_account_id AND seg.session_id = p_session_id;
  IF v_segment_count >= 4096 OR v_text_bytes + octet_length(p_text_content) > 1000000
    OR p_end_seconds > 2678400 THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_segment_limit';
  END IF;
  SELECT COALESCE(max(seg.ordinal) + 1, 0) INTO v_ordinal
  FROM omi_memory.listen_capture_segments seg
  WHERE seg.account_id = v_account_id AND seg.session_id = p_session_id;
  BEGIN
    INSERT INTO omi_memory.listen_capture_segments
      (account_id, session_id, ordinal, segment_id, text_content, is_user,
       start_seconds, end_seconds, appended_at, content_hash)
    VALUES (v_account_id, p_session_id, v_ordinal, p_segment_id, p_text_content,
            p_is_user, p_start_seconds, p_end_seconds, p_appended_at, p_content_hash);
  EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'listen_segment_conflict';
  END;
  RETURN QUERY SELECT 'appended'::text, p_segment_id, v_ordinal;
END
$function$;

CREATE FUNCTION omi_memory.transition_listen_capture_state(
  p_session_id text,
  p_operation text,
  p_event_at timestamptz,
  p_content_hash text
)
RETURNS TABLE(result text, state_sequence bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
  v_state text;
  v_event_at timestamptz;
  v_sequence bigint;
  v_target text;
  v_replay_sequence bigint;
  v_replay_hash text;
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id', true), '') IS NULL
    OR nullif(current_setting('omi.capability', true), '') IS DISTINCT FROM 'listen.capture.write'
    OR p_operation NOT IN ('interrupt', 'resume') THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_authority_denied';
  END IF;
  PERFORM 1 FROM omi_memory.listen_capture_sessions s
  WHERE s.account_id = v_account_id AND s.session_id = p_session_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_session_missing';
  END IF;
  SELECT sr.state, sr.event_at, sr.state_sequence
    INTO STRICT v_state, v_event_at, v_sequence
  FROM omi_memory.listen_capture_session_state_revisions sr
  WHERE sr.account_id = v_account_id AND sr.session_id = p_session_id
  ORDER BY sr.state_sequence DESC LIMIT 1;
  v_target := CASE WHEN p_operation = 'interrupt' THEN 'interrupted' ELSE 'active' END;
  SELECT sr.state_sequence, sr.content_hash INTO v_replay_sequence, v_replay_hash
  FROM omi_memory.listen_capture_session_state_revisions sr
  WHERE sr.account_id = v_account_id AND sr.session_id = p_session_id
    AND sr.state = v_target AND sr.event_at = p_event_at;
  IF FOUND THEN
    IF v_replay_hash <> p_content_hash THEN
      RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'listen_state_conflict';
    END IF;
    RETURN QUERY SELECT 'replayed'::text, v_replay_sequence;
    RETURN;
  END IF;
  IF v_state = v_target THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_state_transition_denied';
  END IF;
  IF (p_operation = 'interrupt' AND v_state <> 'active')
    OR (p_operation = 'resume' AND v_state <> 'interrupted') THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_state_transition_denied';
  END IF;
  IF p_event_at < v_event_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_state_time_invalid';
  END IF;
  v_sequence := v_sequence + 1;
  INSERT INTO omi_memory.listen_capture_session_state_revisions
    (account_id, session_id, state_sequence, state, event_at, content_hash)
  VALUES (v_account_id, p_session_id, v_sequence, v_target, p_event_at, p_content_hash);
  RETURN QUERY SELECT CASE WHEN p_operation = 'interrupt' THEN 'interrupted' ELSE 'resumed' END,
    v_sequence;
END
$function$;

CREATE FUNCTION omi_memory.read_listen_capture_finalization_input(p_session_id text)
RETURNS TABLE(
  session_id text, conversation_id text, client_conversation_id text,
  started_at timestamptz, source text, codec text, sample_rate integer, channels integer,
  current_state text, segment_ordinal bigint, segment_id text, text_content text,
  is_user boolean, start_seconds double precision, end_seconds double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id', true), '') IS NULL
    OR nullif(current_setting('omi.capability', true), '') IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_authority_denied';
  END IF;
  PERFORM 1 FROM omi_memory.listen_capture_sessions s
  WHERE s.account_id = v_account_id AND s.session_id = p_session_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_session_missing';
  END IF;
  RETURN QUERY
    SELECT s.session_id, s.conversation_id, s.client_conversation_id, s.started_at,
      s.source, s.codec, s.sample_rate, s.channels, state.state,
      seg.ordinal, seg.segment_id, seg.text_content, seg.is_user,
      seg.start_seconds, seg.end_seconds
    FROM omi_memory.listen_capture_sessions s
    JOIN LATERAL (
      SELECT sr.state FROM omi_memory.listen_capture_session_state_revisions sr
      WHERE sr.account_id = s.account_id AND sr.session_id = s.session_id
      ORDER BY sr.state_sequence DESC LIMIT 1
    ) state ON true
    LEFT JOIN omi_memory.listen_capture_segments seg
      ON seg.account_id = s.account_id AND seg.session_id = s.session_id
    WHERE s.account_id = v_account_id AND s.session_id = p_session_id
    ORDER BY seg.ordinal NULLS FIRST;
END
$function$;

CREATE FUNCTION omi_memory.seal_listen_capture_finalization(
  p_session_id text,
  p_finalization_id text,
  p_formation_work_id text,
  p_conversation_id text,
  p_terminal_status text,
  p_capture_completeness text,
  p_started_at timestamptz,
  p_ended_at timestamptz,
  p_source text,
  p_segment_count bigint,
  p_transcript_digest text,
  p_finalization_digest text,
  p_finalization_content_hash text,
  p_state_content_hash text,
  p_intent_content_hash text,
  p_outbox_id text,
  p_payload_digest text,
  p_outbox_content_hash text
)
RETURNS TABLE(result text, finalization_id text, formation_work_id text,
  transcript_digest text, finalization_digest text, segment_count bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
  v_existing omi_memory.listen_formation_finalizations%ROWTYPE;
  v_state text;
  v_sequence bigint;
  v_state_event_at timestamptz;
  v_actual_count bigint;
  v_locked_session omi_memory.listen_capture_sessions%ROWTYPE;
BEGIN
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id', true), '') IS NULL
    OR nullif(current_setting('omi.capability', true), '') IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_authority_denied';
  END IF;
  SELECT * INTO v_locked_session FROM omi_memory.listen_capture_sessions s
  WHERE s.account_id = v_account_id AND s.session_id = p_session_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_session_missing';
  END IF;
  IF v_locked_session.conversation_id <> p_conversation_id
    OR v_locked_session.started_at <> p_started_at
    OR v_locked_session.source IS DISTINCT FROM p_source THEN
    RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'listen_finalization_conflict';
  END IF;
  SELECT * INTO v_existing FROM omi_memory.listen_formation_finalizations f
  WHERE f.account_id = v_account_id AND f.session_id = p_session_id;
  IF FOUND THEN
    IF v_existing.finalization_id <> p_finalization_id
      OR v_existing.formation_work_id <> p_formation_work_id
      OR v_existing.conversation_id <> p_conversation_id
      OR v_existing.terminal_status <> p_terminal_status
      OR v_existing.capture_completeness <> p_capture_completeness
      OR v_existing.started_at <> p_started_at OR v_existing.ended_at <> p_ended_at
      OR v_existing.source IS DISTINCT FROM p_source
      OR v_existing.segment_count <> p_segment_count
      OR v_existing.transcript_digest <> p_transcript_digest
      OR v_existing.finalization_digest <> p_finalization_digest
      OR v_existing.content_hash <> p_finalization_content_hash THEN
      RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'listen_finalization_conflict';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM omi_memory.listen_conversation_finalization_intents i
      WHERE i.account_id = v_account_id AND i.conversation_id = p_conversation_id
        AND i.finalization_id = p_finalization_id AND i.intent = 'process_memories'
        AND i.locked AND i.content_hash = p_intent_content_hash
    ) OR NOT EXISTS (
      SELECT 1 FROM omi_memory.listen_formation_outbox o
      WHERE o.account_id = v_account_id AND o.outbox_id = p_outbox_id
        AND o.finalization_id = p_finalization_id
        AND o.formation_work_id = p_formation_work_id AND o.state = 'pending'
        AND o.finalization_digest = p_finalization_digest
        AND o.payload_digest = p_payload_digest
        AND o.created_at = p_ended_at AND o.content_hash = p_outbox_content_hash
    ) OR NOT EXISTS (
      SELECT 1 FROM omi_memory.listen_capture_session_state_revisions sr
      WHERE sr.account_id = v_account_id AND sr.session_id = p_session_id
        AND sr.state = p_terminal_status AND sr.event_at = p_ended_at
        AND sr.content_hash = p_state_content_hash
    ) THEN
      RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'listen_finalization_incomplete';
    END IF;
    RETURN QUERY SELECT 'replayed'::text, p_finalization_id, p_formation_work_id,
      p_transcript_digest, p_finalization_digest, p_segment_count;
    RETURN;
  END IF;
  SELECT sr.state, sr.state_sequence, sr.event_at INTO STRICT v_state, v_sequence, v_state_event_at
  FROM omi_memory.listen_capture_session_state_revisions sr
  WHERE sr.account_id = v_account_id AND sr.session_id = p_session_id
  ORDER BY sr.state_sequence DESC LIMIT 1;
  SELECT count(*) INTO v_actual_count FROM omi_memory.listen_capture_segments seg
  WHERE seg.account_id = v_account_id AND seg.session_id = p_session_id;
  IF v_state <> 'active' OR p_terminal_status NOT IN ('completed', 'entitlement_exhausted')
    OR (p_terminal_status = 'completed' AND p_capture_completeness <> 'complete')
    OR (p_terminal_status = 'entitlement_exhausted'
      AND p_capture_completeness <> 'incomplete_entitlement_exhausted')
    OR p_ended_at < v_state_event_at
    OR p_segment_count <= 0 OR v_actual_count <> p_segment_count THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_finalization_denied';
  END IF;
  INSERT INTO omi_memory.listen_formation_finalizations
    (account_id, finalization_id, formation_work_id, session_id, conversation_id,
     terminal_status, capture_completeness, started_at, ended_at, source, segment_count,
     transcript_digest, finalization_digest, content_hash)
  VALUES (v_account_id, p_finalization_id, p_formation_work_id, p_session_id,
          p_conversation_id, p_terminal_status, p_capture_completeness, p_started_at,
          p_ended_at, p_source, p_segment_count, p_transcript_digest,
          p_finalization_digest, p_finalization_content_hash);
  INSERT INTO omi_memory.listen_capture_session_state_revisions
    (account_id, session_id, state_sequence, state, event_at, content_hash)
  VALUES (v_account_id, p_session_id, v_sequence + 1, p_terminal_status,
          p_ended_at, p_state_content_hash);
  INSERT INTO omi_memory.listen_conversation_finalization_intents
    (account_id, conversation_id, finalization_id, intent, locked, content_hash)
  VALUES (v_account_id, p_conversation_id, p_finalization_id,
          'process_memories', true, p_intent_content_hash);
  INSERT INTO omi_memory.listen_formation_outbox
    (account_id, outbox_id, finalization_id, formation_work_id, state,
     finalization_digest, payload_digest, created_at, content_hash)
  VALUES (v_account_id, p_outbox_id, p_finalization_id, p_formation_work_id,
          'pending', p_finalization_digest, p_payload_digest, p_ended_at,
          p_outbox_content_hash);
  RETURN QUERY SELECT 'sealed'::text, p_finalization_id, p_formation_work_id,
    p_transcript_digest, p_finalization_digest, p_segment_count;
END
$function$;

REVOKE ALL ON FUNCTION omi_memory.open_listen_capture_session(
  text, text, text, timestamptz, text, text, integer, integer, text, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.append_listen_capture_segment(
  text, text, text, boolean, double precision, double precision, timestamptz, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.transition_listen_capture_state(
  text, text, timestamptz, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_listen_capture_finalization_input(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.seal_listen_capture_finalization(
  text, text, text, text, text, text, timestamptz, timestamptz, text, bigint,
  text, text, text, text, text, text, text, text
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.open_listen_capture_session(
  text, text, text, timestamptz, text, text, integer, integer, text, text
) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.append_listen_capture_segment(
  text, text, text, boolean, double precision, double precision, timestamptz, text
) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.transition_listen_capture_state(
  text, text, timestamptz, text
) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_capture_finalization_input(text)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.seal_listen_capture_finalization(
  text, text, text, text, text, text, timestamptz, timestamptz, text, bigint,
  text, text, text, text, text, text, text, text
) TO omi_platform_application;

-- Keep the deletion inventory closed after adding account-owned Listen rows.
CREATE OR REPLACE FUNCTION omi_memory.cleanup_surface_tables(p_surface text)
RETURNS TABLE(table_name text)
LANGUAGE sql
IMMUTABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT mapping.table_name
  FROM (VALUES
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
    ('staged_results', 'memory_query_evaluation_inputs'),
    ('staged_results', 'memory_candidate_derivation_artifacts'),
    ('staged_results', 'listen_capture_sessions'),
    ('staged_results', 'listen_capture_session_state_revisions'),
    ('staged_results', 'listen_capture_segments'),
    ('staged_results', 'listen_formation_finalizations'),
    ('staged_results', 'listen_conversation_finalization_intents'),
    ('staged_results', 'listen_formation_outbox'),
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
    ('authoritative_memory', 'memory_formation_outcomes'),
    ('authoritative_memory', 'memory_formation_placement_outcomes'),
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
