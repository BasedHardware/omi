-- A9 recording admission replacement joins all sibling/custody writes.
-- Original intent and every terminal result remain immutable.
CREATE OR REPLACE FUNCTION queue_handoff_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE authority queue_authority%ROWTYPE;
BEGIN
 SELECT * INTO authority FROM queue_authority WHERE namespace=NEW.namespace FOR UPDATE;
 IF NOT FOUND OR authority.state <> 'PG_OPEN' OR authority.epoch <> NEW.epoch
   OR current_setting('omi.queue_epoch',true) IS DISTINCT FROM NEW.epoch::text THEN
  RAISE EXCEPTION 'handoff writer epoch refused' USING ERRCODE='42501';
 END IF;
 IF TG_OP='UPDATE' THEN
  IF (NEW.namespace,NEW.identity,NEW.owner_key,NEW.epoch,NEW.intent,NEW.fingerprint)
   IS DISTINCT FROM (OLD.namespace,OLD.identity,OLD.owner_key,OLD.epoch,OLD.intent,OLD.fingerprint)
   OR (NEW.admission IS DISTINCT FROM OLD.admission AND NOT (
       OLD.phase='admitted' AND NEW.phase='admitted'
       AND current_setting('omi.queue_readmission',true) IS NOT DISTINCT FROM NEW.admission->>'admission_id'
       AND current_setting('omi.privacy_fence_protocol',true)='2'))
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
