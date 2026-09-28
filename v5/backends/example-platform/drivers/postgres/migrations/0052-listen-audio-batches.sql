CREATE FUNCTION omi_memory.append_listen_audio_upload_batch(p_session_id text,p_chunks jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_chunk jsonb; v_index integer; v_previous integer; v_bytes bytea; v_total integer:=0; v_session jsonb;
BEGIN
  PERFORM omi_memory.assert_listen_audio_upload_epoch(p_session_id);
  IF p_chunks IS NULL OR jsonb_typeof(p_chunks)<>'array' THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='listen_audio_invalid';
  END IF;
  IF jsonb_array_length(p_chunks)<1 OR jsonb_array_length(p_chunks)>128 OR octet_length(p_chunks::text)>2097152 THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='listen_audio_invalid';
  END IF;
  FOR v_chunk IN SELECT value FROM jsonb_array_elements(p_chunks) LOOP
    IF jsonb_typeof(v_chunk)<>'object' OR jsonb_typeof(v_chunk->'chunkIndex') IS DISTINCT FROM 'number'
      OR jsonb_typeof(v_chunk->'bytesBase64') IS DISTINCT FROM 'string'
      OR (SELECT count(*) FROM jsonb_object_keys(v_chunk))<>2 THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='listen_audio_invalid';
    END IF;
    v_index:=(v_chunk->>'chunkIndex')::integer;
    IF (v_chunk->>'chunkIndex')::numeric<>v_index OR v_index<0 OR v_index>65535
      OR (v_previous IS NOT NULL AND v_index<>v_previous+1) THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='listen_audio_invalid';
    END IF;
    v_bytes:=decode(v_chunk->>'bytesBase64','base64');
    v_total:=v_total+octet_length(v_bytes);
    IF octet_length(v_bytes)<1 OR v_total>1048576
      OR replace(encode(v_bytes,'base64'),E'\n','') IS DISTINCT FROM v_chunk->>'bytesBase64' THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='listen_audio_invalid';
    END IF;
    v_session:=omi_memory.append_listen_audio_upload(p_session_id,v_index,v_bytes);
    IF v_session IS NULL THEN RETURN NULL; END IF;
    v_previous:=v_index;
  END LOOP;
  RETURN v_session;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.append_listen_audio_upload_batch(text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.append_listen_audio_upload_batch(text,jsonb) TO omi_platform_application;
