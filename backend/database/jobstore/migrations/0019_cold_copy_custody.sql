-- Every new cold reference belongs to the original recording lifetime.
CREATE TABLE queue_cold_copy_custody (
 namespace text NOT NULL, recording_id text NOT NULL, owner_key text NOT NULL,
 source_fingerprint text NOT NULL, manifest jsonb NOT NULL,
 PRIMARY KEY(namespace,recording_id),
 FOREIGN KEY(namespace,recording_id) REFERENCES queue_handoffs(namespace,identity)
);
CREATE FUNCTION cold_copy_custody_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'cold-copy custody requires final retirement proof' USING ERRCODE='42501';
END $$;
CREATE TRIGGER cold_copy_custody_immutable BEFORE UPDATE OR DELETE ON queue_cold_copy_custody
 FOR EACH ROW EXECUTE FUNCTION cold_copy_custody_immutable();
CREATE TRIGGER a_cold_copy_owner_lock BEFORE INSERT OR UPDATE OR DELETE ON queue_cold_copy_custody
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER cold_copy_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_cold_copy_custody
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
REVOKE ALL ON queue_cold_copy_custody FROM PUBLIC;

CREATE OR REPLACE FUNCTION retained_copy_last_custodian() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE value jsonb=to_jsonb(OLD);
BEGIN
 IF EXISTS (SELECT 1 FROM (
    SELECT namespace,recording_id,owner_key,manifest FROM queue_retained_copy_custody
    UNION ALL
    SELECT namespace,recording_id,owner_key,manifest FROM queue_cold_copy_custody) c
   WHERE c.namespace=OLD.namespace AND c.owner_key=coalesce(value->>'owner_key',value->>'owner_id')
    AND (TG_TABLE_NAME='queue_journal'
     OR c.recording_id=coalesce(value->>'recording_id',value->>'identity',value->>'dedupe_key')
     OR (c.manifest->'unit_ids') ? coalesce(value->>'unit_id',value->>'identity',''))) THEN
  RAISE EXCEPTION 'unresolved retained-copy erasure keeps original PG custody' USING ERRCODE='42501';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
