CREATE OR REPLACE FUNCTION omi_memory.listen_provider_result_readable(p jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_seg jsonb; v_duration double precision; v_i integer; v_n integer; v_j integer; v_start double precision; v_end double precision; v_text text; v_units integer; v_chars integer:=0; v_bytes integer:=0;
  v_ws text:=chr(9)||chr(10)||chr(11)||chr(12)||chr(13)||chr(32)||chr(133)||chr(160)||chr(5760)||chr(8192)||chr(8193)||chr(8194)||chr(8195)||chr(8196)||chr(8197)||chr(8198)||chr(8199)||chr(8200)||chr(8201)||chr(8202)||chr(8232)||chr(8233)||chr(8239)||chr(8287)||chr(12288)||chr(65279);
BEGIN
  IF p IS NULL OR jsonb_typeof(p) IS DISTINCT FROM 'object' THEN RETURN false; END IF;
  IF jsonb_typeof(p->'durationSeconds') IS DISTINCT FROM 'number' OR jsonb_typeof(p->'segments') IS DISTINCT FROM 'array' THEN RETURN false; END IF;
  v_duration := (p->>'durationSeconds')::double precision;
  v_n := jsonb_array_length(p->'segments');
  IF v_duration IS NULL OR v_duration<=0 OR v_duration>3600 OR v_n IS NULL OR v_n>4096 THEN RETURN false; END IF;
  FOR v_i IN 0..v_n-1 LOOP
    v_seg := p->'segments'->v_i;
    IF jsonb_typeof(v_seg) IS DISTINCT FROM 'object' OR jsonb_typeof(v_seg->'text') IS DISTINCT FROM 'string'
      OR jsonb_typeof(v_seg->'start') IS DISTINCT FROM 'number' OR jsonb_typeof(v_seg->'end') IS DISTINCT FROM 'number' THEN RETURN false; END IF;
    v_text := v_seg->>'text';
    v_start := (v_seg->>'start')::double precision;
    v_end := (v_seg->>'end')::double precision;
    IF v_text IS NULL OR btrim(v_text,v_ws)='' OR position(chr(0) IN v_text)>0
      OR v_start IS NULL OR v_end IS NULL OR v_start<0 OR v_end<v_start OR v_end>v_duration+0.1 THEN RETURN false; END IF;
    v_units := 0;
    FOR v_j IN 1..length(v_text) LOOP
      v_units := v_units+CASE WHEN ascii(substr(v_text,v_j,1))>65535 THEN 2 ELSE 1 END;
      IF v_units>1500 THEN RETURN false; END IF;
    END LOOP;
    v_chars := v_chars+length(v_text);
    v_bytes := v_bytes+octet_length(v_text);
    IF v_chars>1000000 OR v_bytes>1000000 THEN RETURN false; END IF;
  END LOOP;
  RETURN true;
EXCEPTION WHEN OTHERS THEN RETURN false;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.listen_provider_result_readable(jsonb) FROM PUBLIC;
