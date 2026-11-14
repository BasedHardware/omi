-- Original admission, not a numeric PG row ID or coalescing version, owns a
-- typed recording task's incarnation. Legacy rows remain unknown, not guessed.
ALTER TABLE outbox ADD COLUMN logical_generation text;
CREATE FUNCTION queue_outbox_generation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.logical_generation IS DISTINCT FROM OLD.logical_generation THEN
  RAISE EXCEPTION 'outbox logical generation is immutable' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER queue_outbox_generation_immutable BEFORE UPDATE ON outbox
 FOR EACH ROW EXECUTE FUNCTION queue_outbox_generation_immutable();

CREATE OR REPLACE FUNCTION queue_mutation_journal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
 value jsonb; ns text; authority queue_authority%ROWTYPE; owner text; ident jsonb; next_seq bigint;
BEGIN
 IF TG_OP='DELETE' THEN value=to_jsonb(OLD); ELSE value=to_jsonb(NEW); END IF;
 ns=value->>'namespace';
 SELECT * INTO authority FROM queue_authority WHERE namespace=ns FOR UPDATE;
 IF NOT FOUND THEN
  IF TG_TABLE_NAME IN ('units','recordings','budgets','queue_custody') THEN
   RAISE EXCEPTION 'typed queue namespace has no authority';
  END IF;
 ELSIF authority.state <> 'FS_OPEN' THEN
  IF authority.state <> 'PG_OPEN' OR current_setting('omi.queue_epoch',true) IS DISTINCT FROM authority.epoch::text THEN
   RAISE EXCEPTION 'queue writer epoch refused' USING ERRCODE='42501';
  END IF;
  owner=coalesce(value->>'owner_key',value->'doc'->>'owner_key',current_setting('omi.queue_owner_key',true));
  IF owner IS NULL OR owner !~ '^[0-9a-f]{64}$' THEN
   RAISE EXCEPTION 'unknown queue owner binding; activation blocked';
  END IF;
  IF TG_TABLE_NAME='outbox' THEN
   ident=jsonb_strip_nulls(jsonb_build_object('kind',value->'kind',
    'dedupe_key',value->'dedupe_key','generation',value->'logical_generation'));
  ELSE
   ident=jsonb_strip_nulls(jsonb_build_object('key',value->'key','tbl',value->'tbl',
    'unit_id',value->'unit_id','recording_id',value->'recording_id','identity',value->'identity',
    'id',value->'id','scope',value->'scope','period',value->'period'));
  END IF;
  UPDATE queue_authority SET committed_seq=committed_seq+1 WHERE namespace=ns RETURNING committed_seq INTO next_seq;
  INSERT INTO queue_journal(namespace,seq,epoch,family,identity,operation,owner_key,body)
   VALUES(ns,next_seq,authority.epoch,TG_TABLE_NAME,ident,
    CASE WHEN TG_OP='DELETE' THEN 'delete' ELSE 'put' END,owner,
    CASE WHEN TG_OP='DELETE' THEN NULL ELSE value END);
 ELSIF TG_TABLE_NAME IN ('units','recordings','budgets','queue_custody') THEN
  RAISE EXCEPTION 'typed queue writes require PG authority';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
