-- Original terminal evidence survives capability retirement; no URL, TTL or final certificate.
CREATE TABLE queue_upload_terminal_receipts (
 namespace text NOT NULL, unit_id text NOT NULL, attempt_token text NOT NULL,
 owner_key text NOT NULL, admission_id uuid NOT NULL, effect_id uuid NOT NULL UNIQUE,
 original_deadline double precision NOT NULL, generation bigint CHECK (generation>0),
 status integer NOT NULL CHECK (status IN (200,201,404,410,412,499)),
 sink_hash text NOT NULL CHECK (sink_hash ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(namespace,unit_id),
 FOREIGN KEY(namespace,unit_id,attempt_token) REFERENCES queue_provider_uploads(namespace,unit_id,attempt_token),
 CHECK (generation IS NOT NULL OR status IN (412,499))
);
CREATE FUNCTION upload_terminal_source() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE upload queue_provider_uploads%ROWTYPE;
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'original terminal receipt remains in custody' USING ERRCODE='42501';
 END IF;
 SELECT * INTO upload FROM queue_provider_uploads WHERE namespace=NEW.namespace AND unit_id=NEW.unit_id;
 IF NOT FOUND OR upload.phase<>'draining'
  OR (NEW.attempt_token,NEW.owner_key,NEW.admission_id,NEW.effect_id,NEW.original_deadline,NEW.generation)
    IS DISTINCT FROM
     (upload.attempt_token,upload.owner_key,upload.admission_id,upload.effect_id,upload.original_deadline,upload.generation)
  OR NOT EXISTS (SELECT 1 FROM privacy_effect_inflight WHERE effect_id=NEW.effect_id AND kind='gcs_put'
    AND owner_key=NEW.owner_key AND admission_id=NEW.admission_id) THEN
  RAISE EXCEPTION 'terminal receipt requires original draining capability' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER a_upload_terminal_owner_lock BEFORE INSERT OR UPDATE OR DELETE ON queue_upload_terminal_receipts
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER upload_terminal_source BEFORE INSERT OR UPDATE OR DELETE ON queue_upload_terminal_receipts
 FOR EACH ROW EXECUTE FUNCTION upload_terminal_source();
CREATE TRIGGER upload_terminal_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_upload_terminal_receipts
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE FUNCTION upload_terminal_join() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE upload queue_provider_uploads%ROWTYPE;
BEGIN
 SELECT * INTO upload FROM queue_provider_uploads WHERE namespace=NEW.namespace AND unit_id=NEW.unit_id;
 IF TG_TABLE_NAME='queue_upload_terminal_receipts' AND upload.phase<>'fenced' THEN
  RAISE EXCEPTION 'terminal receipt must share fenced COMMIT' USING ERRCODE='42501';
 END IF;
 IF upload.phase='fenced' AND (NOT EXISTS (
  SELECT 1 FROM queue_upload_terminal_receipts r WHERE r.namespace=upload.namespace AND r.unit_id=upload.unit_id
   AND r.attempt_token=upload.attempt_token AND r.effect_id=upload.effect_id
   AND r.generation IS NOT DISTINCT FROM upload.generation)
  OR EXISTS (SELECT 1 FROM privacy_effect_inflight WHERE effect_id=upload.effect_id)) THEN
  RAISE EXCEPTION 'terminal proof, fencing and capability retirement must share COMMIT' USING ERRCODE='42501';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER upload_terminal_join AFTER INSERT ON queue_upload_terminal_receipts
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION upload_terminal_join();
CREATE CONSTRAINT TRIGGER upload_terminal_fenced_join AFTER INSERT OR UPDATE ON queue_provider_uploads
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION upload_terminal_join();
REVOKE ALL ON queue_upload_terminal_receipts FROM PUBLIC;
-- contract: strict superset of existing progress purposes, never destructive final PG cleanup.
ALTER TABLE queue_original_erasure_operations DROP CONSTRAINT queue_original_erasure_operations_purpose_check;
ALTER TABLE queue_original_erasure_operations ADD CHECK
 (purpose IN ('object','metadata','published_object','published_reference','fenced_object','fenced_reference'));
