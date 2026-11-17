-- Durable cancellation barriers, not TTLs or final erasure certificates.
CREATE TABLE queue_original_erasure_operations (
 namespace text NOT NULL, operation_id text NOT NULL,
 recording_id text NOT NULL, owner_key text NOT NULL, unit_token text NOT NULL,
 purge_generation bigint,
 purpose text NOT NULL CHECK (purpose IN ('object','metadata')),
 payload jsonb NOT NULL,
 state text NOT NULL DEFAULT 'prepared' CHECK (state IN ('prepared','committed','cancelled')),
 PRIMARY KEY(namespace,operation_id),
 FOREIGN KEY(namespace,recording_id) REFERENCES queue_retained_copy_custody(namespace,recording_id)
);
CREATE INDEX original_erasure_recording ON queue_original_erasure_operations(namespace,recording_id);
CREATE FUNCTION original_erasure_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'original erasure cancellation barrier still has custody' USING ERRCODE='42501';
 END IF;
 IF TG_OP='UPDATE' AND (
  (NEW.namespace,NEW.operation_id,NEW.recording_id,NEW.owner_key,NEW.unit_token,NEW.purpose,NEW.payload,NEW.purge_generation)
   IS DISTINCT FROM
  (OLD.namespace,OLD.operation_id,OLD.recording_id,OLD.owner_key,OLD.unit_token,OLD.purpose,OLD.payload,OLD.purge_generation)
  OR NOT (NEW.state=OLD.state OR (OLD.state='prepared' AND NEW.state IN ('committed','cancelled')))) THEN
  RAISE EXCEPTION 'original erasure operation is immutable or already resolved' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER original_erasure_immutable BEFORE UPDATE OR DELETE ON queue_original_erasure_operations
 FOR EACH ROW EXECUTE FUNCTION original_erasure_immutable();
CREATE TRIGGER a_original_erasure_owner_lock BEFORE INSERT OR UPDATE OR DELETE ON queue_original_erasure_operations
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER original_erasure_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_original_erasure_operations
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
REVOKE ALL ON queue_original_erasure_operations FROM PUBLIC;
