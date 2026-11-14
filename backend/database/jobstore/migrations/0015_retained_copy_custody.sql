-- Original records, rather than a new purpose TTL, own this erasure census.
-- This first phase retires private FS projections only. It cannot certify the
-- objects, original metadata, journal or cold copies, or release PG custody.
CREATE TABLE queue_retained_copy_custody (
 namespace text NOT NULL REFERENCES queue_authority(namespace),
 recording_id text NOT NULL, owner_key text NOT NULL,
 source_fingerprint text NOT NULL, manifest jsonb NOT NULL,
 phase text NOT NULL DEFAULT 'inventoried' CHECK (phase IN ('inventoried','private_erased')),
 PRIMARY KEY(namespace,recording_id)
);
CREATE INDEX queue_retained_copy_owner ON queue_retained_copy_custody(namespace,owner_key);
CREATE FUNCTION retained_copy_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'original retained-copy custody has no final erasure certificate' USING ERRCODE='42501';
 END IF;
 IF TG_OP='UPDATE' AND (
   (NEW.namespace,NEW.recording_id,NEW.owner_key,NEW.source_fingerprint,NEW.manifest)
    IS DISTINCT FROM (OLD.namespace,OLD.recording_id,OLD.owner_key,OLD.source_fingerprint,OLD.manifest)
   OR NOT (NEW.phase=OLD.phase OR (OLD.phase='inventoried' AND NEW.phase='private_erased'))) THEN
  RAISE EXCEPTION 'retained-copy census is immutable' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER retained_copy_immutable BEFORE UPDATE OR DELETE ON queue_retained_copy_custody
 FOR EACH ROW EXECUTE FUNCTION retained_copy_immutable();
CREATE TRIGGER privacy_retained_copy_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_retained_copy_custody
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();

-- Until all remote units have definitive outcomes, do not discard the last
-- original custodian, including paid attempt/effect metadata absent from seals.
CREATE FUNCTION retained_copy_last_custodian() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE value jsonb=to_jsonb(OLD);
BEGIN
 IF EXISTS (SELECT 1 FROM queue_retained_copy_custody c
   WHERE c.namespace=OLD.namespace AND c.owner_key=coalesce(value->>'owner_key',value->>'owner_id')
    AND (TG_TABLE_NAME='queue_journal'
     OR c.recording_id=coalesce(value->>'recording_id',value->>'identity',value->>'dedupe_key')
     OR (c.manifest->'unit_ids') ? coalesce(value->>'unit_id',value->>'identity',''))) THEN
  RAISE EXCEPTION 'unresolved retained-copy erasure keeps original PG custody' USING ERRCODE='42501';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER retained_copy_handoff BEFORE DELETE ON queue_handoffs
 FOR EACH ROW EXECUTE FUNCTION retained_copy_last_custodian();
CREATE TRIGGER retained_copy_unit BEFORE DELETE ON units
 FOR EACH ROW EXECUTE FUNCTION retained_copy_last_custodian();
CREATE TRIGGER retained_copy_recording BEFORE DELETE ON recordings
 FOR EACH ROW EXECUTE FUNCTION retained_copy_last_custodian();
CREATE TRIGGER retained_copy_custody BEFORE DELETE ON queue_custody
 FOR EACH ROW EXECUTE FUNCTION retained_copy_last_custodian();
CREATE TRIGGER retained_copy_journal BEFORE UPDATE OR DELETE ON queue_journal
 FOR EACH ROW EXECUTE FUNCTION retained_copy_last_custodian();
REVOKE ALL ON queue_retained_copy_custody FROM PUBLIC;

CREATE TRIGGER retained_copy_outbox BEFORE DELETE ON outbox
 FOR EACH ROW EXECUTE FUNCTION retained_copy_last_custodian();
