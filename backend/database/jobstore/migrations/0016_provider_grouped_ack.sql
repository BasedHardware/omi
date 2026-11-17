-- A typed handoff cannot be acknowledged independently of the recording,
-- original unit custody and the one recording projection task. Deferred until
-- COMMIT so the concrete adapter can update all four families atomically.
CREATE FUNCTION typed_provider_grouped_ack() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE recording recordings%ROWTYPE; expected int; actual int;
BEGIN
 IF NEW.phase <> 'acked' OR (NEW.completion->>'protocol') IS DISTINCT FROM 'typed_provider_v1' THEN
  RETURN NULL;
 END IF;
 IF jsonb_typeof(NEW.completion->'units') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION 'typed provider terminal census required' USING ERRCODE='42501';
 END IF;
 SELECT * INTO recording FROM recordings
  WHERE namespace=NEW.namespace AND recording_id=NEW.identity;
 expected=jsonb_array_length(NEW.completion->'units');
 IF NOT FOUND OR recording.owner_key <> NEW.owner_key
   OR recording.projection_state <> 'projected'
   OR recording.units_total <> expected OR recording.units_final <> expected
   OR NOT EXISTS (SELECT 1 FROM outbox WHERE namespace=NEW.namespace
     AND id=recording.projection_task_id AND kind='project_conversation'
     AND dedupe_key=NEW.identity AND owner_id=NEW.owner_key AND done_at IS NOT NULL)
 THEN
  RAISE EXCEPTION 'typed provider grouped acknowledgement required' USING ERRCODE='42501';
 END IF;
 IF expected NOT BETWEEN 1 AND 128 OR expected <> (
   SELECT count(DISTINCT u->>'unit_id') FROM jsonb_array_elements(NEW.completion->'units') u
 ) OR expected <> (SELECT count(*) FROM units WHERE namespace=NEW.namespace AND recording_id=NEW.identity) THEN
  RAISE EXCEPTION 'typed provider terminal census required' USING ERRCODE='42501';
 END IF;
 SELECT count(*) INTO actual FROM units q
  JOIN jsonb_array_elements(NEW.completion->'units') u ON q.unit_id=u->>'unit_id'
  WHERE q.namespace=NEW.namespace AND q.recording_id=NEW.identity AND q.owner_key=NEW.owner_key
    AND q.admission=NEW.admission AND q.state='result_ready'
    AND q.source=u->'source' AND q.result=u->'result' AND to_jsonb(q.settled_at)=u->'settled_at';
 IF actual <> expected THEN
  RAISE EXCEPTION 'typed provider original terminal seal required' USING ERRCODE='42501';
 END IF;
 SELECT count(*) INTO actual FROM queue_custody c
  JOIN jsonb_array_elements(NEW.completion->'units') u ON c.identity=u->>'unit_id'
  WHERE c.namespace=NEW.namespace AND c.owner_key=NEW.owner_key AND c.phase='acked'
    AND c.admission_id::text=NEW.admission->>'admission_id'
    AND c.projection_receipt=NEW.projection_receipt;
 IF actual <> expected THEN
  RAISE EXCEPTION 'typed provider grouped custody acknowledgement required' USING ERRCODE='42501';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER typed_provider_grouped_ack AFTER INSERT OR UPDATE ON queue_handoffs
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION typed_provider_grouped_ack();
