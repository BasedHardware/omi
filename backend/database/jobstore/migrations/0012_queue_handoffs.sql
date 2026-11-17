-- Durable handoff state. No factory selects this path. The caller's queue
-- mutation and completion seal join this row's PostgreSQL transaction.
CREATE TABLE queue_handoffs (
 namespace text NOT NULL REFERENCES queue_authority(namespace),
 identity text NOT NULL, owner_key text NOT NULL,
 epoch bigint NOT NULL, intent jsonb NOT NULL, fingerprint text NOT NULL,
 admission jsonb NOT NULL,
 phase text NOT NULL DEFAULT 'admitted' CHECK (phase IN ('admitted','completed','acked')),
 completion jsonb, completion_hash text, projection_receipt text,
 PRIMARY KEY(namespace,identity),
 CHECK ((phase='admitted' AND completion IS NULL AND completion_hash IS NULL AND projection_receipt IS NULL)
     OR (phase='completed' AND completion IS NOT NULL AND completion_hash IS NOT NULL AND projection_receipt IS NULL)
     OR (phase='acked' AND completion IS NOT NULL AND completion_hash IS NOT NULL AND projection_receipt IS NOT NULL))
);
CREATE FUNCTION queue_handoff_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE authority queue_authority%ROWTYPE;
BEGIN
 SELECT * INTO authority FROM queue_authority WHERE namespace=NEW.namespace FOR UPDATE;
 IF NOT FOUND OR authority.state <> 'PG_OPEN' OR authority.epoch <> NEW.epoch
   OR current_setting('omi.queue_epoch',true) IS DISTINCT FROM NEW.epoch::text THEN
  RAISE EXCEPTION 'handoff writer epoch refused' USING ERRCODE='42501';
 END IF;
 IF TG_OP='UPDATE' THEN
  IF (NEW.namespace,NEW.identity,NEW.owner_key,NEW.epoch,NEW.intent,NEW.fingerprint,NEW.admission)
   IS DISTINCT FROM (OLD.namespace,OLD.identity,OLD.owner_key,OLD.epoch,OLD.intent,OLD.fingerprint,OLD.admission)
   OR (OLD.completion IS NOT NULL AND (NEW.completion,NEW.completion_hash) IS DISTINCT FROM (OLD.completion,OLD.completion_hash))
   OR (OLD.projection_receipt IS NOT NULL AND NEW.projection_receipt IS DISTINCT FROM OLD.projection_receipt)
   OR NOT (NEW.phase=OLD.phase OR (OLD.phase='admitted' AND NEW.phase='completed') OR (OLD.phase='completed' AND NEW.phase='acked')) THEN
   RAISE EXCEPTION 'immutable handoff or invalid transition';
  END IF;
 ELSIF NEW.phase <> 'admitted' THEN
  RAISE EXCEPTION 'handoff must begin admitted';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER queue_handoff_immutable BEFORE INSERT OR UPDATE ON queue_handoffs
 FOR EACH ROW EXECUTE FUNCTION queue_handoff_immutable();
CREATE TRIGGER privacy_handoff_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_handoffs
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER queue_handoff_journal AFTER INSERT OR UPDATE OR DELETE ON queue_handoffs
 FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE INDEX queue_handoff_owner ON queue_handoffs(namespace,owner_key);
REVOKE ALL ON queue_handoffs FROM PUBLIC;
