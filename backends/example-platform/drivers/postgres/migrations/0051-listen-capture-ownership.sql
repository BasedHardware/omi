ALTER TABLE omi_memory.listen_capture_audio_uploads ADD COLUMN captured_account_epoch bigint CHECK(captured_account_epoch>=0);
ALTER TABLE omi_memory.listen_capture_audio_uploads ALTER COLUMN captured_account_epoch SET DEFAULT nullif(current_setting('omi.account_epoch',true),'')::bigint;

CREATE FUNCTION omi_memory.assert_listen_audio_upload_epoch(p_session_id text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_epoch bigint;
BEGIN
  IF v_account IS NULL OR current_setting('omi.capability',true) IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='listen_authority_denied';
  END IF;
  SELECT captured_account_epoch INTO v_epoch FROM omi_memory.listen_capture_audio_uploads
    WHERE account_id=v_account AND session_id=p_session_id;
  IF FOUND AND (v_epoch IS NULL OR v_epoch IS DISTINCT FROM nullif(current_setting('omi.account_epoch',true),'')::bigint) THEN
    RAISE EXCEPTION USING ERRCODE='P1006',MESSAGE='capture_ownership_changed';
  END IF;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.assert_listen_audio_upload_epoch(text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION omi_memory.open_listen_audio_upload(
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
  PERFORM omi_memory.assert_listen_audio_upload_epoch(v_existing.session_id);
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

CREATE OR REPLACE FUNCTION omi_memory.append_listen_audio_upload(p_session_id text,p_chunk_index integer,p_bytes bytea)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,omi_memory AS $function$
DECLARE v_account_id text := nullif(current_setting('omi.account_id',true),'');
  v_upload omi_memory.listen_capture_audio_uploads%ROWTYPE; v_bytes bytea; v_state text;
BEGIN
  PERFORM omi_memory.assert_listen_audio_upload_epoch(p_session_id);
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

CREATE OR REPLACE FUNCTION omi_memory.complete_listen_audio_upload(p_session_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,omi_memory AS $function$
DECLARE v_account_id text := nullif(current_setting('omi.account_id',true),'');
BEGIN
  PERFORM omi_memory.assert_listen_audio_upload_epoch(p_session_id);
  IF v_account_id IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'listen.capture.write' THEN
    RAISE EXCEPTION USING ERRCODE='P1005', MESSAGE='listen_authority_denied';
  END IF;
  UPDATE omi_memory.listen_capture_audio_uploads SET upload_completed_at=coalesce(upload_completed_at,transaction_timestamp())
    WHERE account_id=v_account_id AND session_id=p_session_id;
  RETURN omi_memory.read_listen_audio_upload(p_session_id);
END $function$;

CREATE OR REPLACE FUNCTION omi_memory.claim_listen_audio_transcription(p_session_id text,p_token uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),'');
  v_upload omi_memory.listen_capture_audio_uploads%ROWTYPE;
  v_job omi_memory.listen_audio_transcriptions%ROWTYPE; v_owned boolean:=false;
BEGIN
  PERFORM omi_memory.assert_listen_audio_upload_epoch(p_session_id);
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

CREATE OR REPLACE FUNCTION omi_memory.load_listen_transcription_audio(p_session_id text,p_token uuid)
RETURNS TABLE(chunk_index integer,bytes bytea) LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),'');
BEGIN
  PERFORM omi_memory.assert_listen_audio_upload_epoch(p_session_id);
  PERFORM omi_memory.read_listen_audio_transcription(p_session_id);
  IF NOT EXISTS(SELECT 1 FROM omi_memory.listen_audio_transcriptions WHERE account_id=v_account AND session_id=p_session_id
    AND state='running' AND lease_token=p_token AND lease_expires_at>clock_timestamp()) THEN
    RAISE EXCEPTION USING ERRCODE='P1002',MESSAGE='listen_transcription_stale_lease';
  END IF;
  RETURN QUERY SELECT c.chunk_index,c.bytes FROM omi_memory.listen_capture_audio_chunks c
    WHERE c.account_id=v_account AND c.session_id=p_session_id ORDER BY c.chunk_index;
END $function$;

CREATE OR REPLACE FUNCTION omi_memory.save_listen_audio_transcription(p_session_id text,p_token uuid,p_result jsonb,p_discarded integer,p_error text,p_retry boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_count integer;
BEGIN
  PERFORM omi_memory.assert_listen_audio_upload_epoch(p_session_id);
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

CREATE OR REPLACE FUNCTION omi_memory.complete_listen_audio_transcription(p_session_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),'');
BEGIN
  PERFORM omi_memory.assert_listen_audio_upload_epoch(p_session_id);
  PERFORM omi_memory.read_listen_audio_transcription(p_session_id);
  UPDATE omi_memory.listen_audio_transcriptions SET state='completed',updated_at=clock_timestamp()
    WHERE account_id=v_account AND session_id=p_session_id AND state='running' AND provider_result IS NOT NULL
      AND (jsonb_array_length(provider_result->'segments')=0 OR EXISTS(
        SELECT 1 FROM omi_memory.listen_formation_finalizations f WHERE f.account_id=v_account AND f.session_id=p_session_id));
  RETURN omi_memory.read_listen_audio_transcription(p_session_id);
END $function$;

