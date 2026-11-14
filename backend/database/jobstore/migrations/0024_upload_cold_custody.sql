-- New source-bound extension; never rewrite the original retained manifest.
CREATE TABLE queue_upload_cold_custody (
 namespace text NOT NULL, unit_id text NOT NULL, recording_id text NOT NULL,
 owner_key text NOT NULL, source_fingerprint text NOT NULL,
 original_upload jsonb NOT NULL, cold_path text NOT NULL,
 PRIMARY KEY(namespace,unit_id), UNIQUE(cold_path),
 FOREIGN KEY(namespace,unit_id) REFERENCES queue_provider_uploads(namespace,unit_id),
 FOREIGN KEY(namespace,recording_id) REFERENCES queue_cold_copy_custody(namespace,recording_id)
);
CREATE FUNCTION upload_cold_source() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE upload queue_provider_uploads%ROWTYPE; original queue_handoffs%ROWTYPE;
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'upload cold custody needs final all-copy retirement proof' USING ERRCODE='42501';
 END IF;
 SELECT * INTO upload FROM queue_provider_uploads WHERE namespace=NEW.namespace AND unit_id=NEW.unit_id;
 SELECT * INTO original FROM queue_handoffs WHERE namespace=NEW.namespace AND identity=NEW.recording_id;
 IF upload.unit_id IS NULL OR original.identity IS NULL
  OR upload.owner_key<>NEW.owner_key OR upload.recording_id<>NEW.recording_id
  OR upload.admission_id::text IS DISTINCT FROM original.admission->>'admission_id'
  OR NEW.original_upload IS DISTINCT FROM (to_jsonb(upload)-'phase'-'effect_id'-'generation')
  OR NEW.source_fingerprint IS DISTINCT FROM (SELECT source_fingerprint FROM queue_cold_copy_custody
    WHERE namespace=NEW.namespace AND recording_id=NEW.recording_id) THEN
  RAISE EXCEPTION 'original upload cold source mismatch' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER a_upload_cold_owner_lock BEFORE INSERT OR UPDATE OR DELETE ON queue_upload_cold_custody
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER upload_cold_source BEFORE INSERT OR UPDATE OR DELETE ON queue_upload_cold_custody
 FOR EACH ROW EXECUTE FUNCTION upload_cold_source();
CREATE TRIGGER upload_cold_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_upload_cold_custody
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
REVOKE ALL ON queue_upload_cold_custody FROM PUBLIC;
