-- Original reference custody survives destructive deletion of redundant PG copies.
-- No intake repair context, TTL, final erasure certificate or journal pruning.
CREATE TABLE queue_staging_copy_custody (
 namespace text NOT NULL, recording_id text NOT NULL, owner_key text NOT NULL,
 manifest jsonb NOT NULL,
 PRIMARY KEY(namespace,recording_id),
 FOREIGN KEY(namespace,recording_id) REFERENCES queue_retained_copy_custody(namespace,recording_id)
);
CREATE TABLE queue_staging_copy_keys (
 namespace text NOT NULL, key text NOT NULL, recording_id text NOT NULL,
 owner_key text NOT NULL, cold_path text NOT NULL,
 PRIMARY KEY(namespace,key),
 FOREIGN KEY(namespace,recording_id) REFERENCES queue_staging_copy_custody(namespace,recording_id)
);
CREATE TABLE queue_staging_erasure_operations (
 namespace text NOT NULL, operation_id text NOT NULL, recording_id text NOT NULL,
 owner_key text NOT NULL, unit_token text NOT NULL, census_hash text NOT NULL,
 purge_generation bigint,
 state text NOT NULL DEFAULT 'prepared' CHECK (state IN ('prepared','committed','cancelled')),
 PRIMARY KEY(namespace,operation_id),
 FOREIGN KEY(namespace,recording_id) REFERENCES queue_staging_copy_custody(namespace,recording_id)
);
CREATE FUNCTION staging_custody_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'original staging reference custody still unresolved' USING ERRCODE='42501';
END $$;
CREATE TRIGGER staging_custody_immutable BEFORE UPDATE OR DELETE ON queue_staging_copy_custody
 FOR EACH ROW EXECUTE FUNCTION staging_custody_immutable();
CREATE TRIGGER staging_key_immutable BEFORE UPDATE OR DELETE ON queue_staging_copy_keys
 FOR EACH ROW EXECUTE FUNCTION staging_custody_immutable();
CREATE FUNCTION staging_operation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR (TG_OP='UPDATE' AND (
   (to_jsonb(NEW)-'state') IS DISTINCT FROM (to_jsonb(OLD)-'state')
   OR NOT (NEW.state=OLD.state OR (OLD.state='prepared' AND NEW.state IN ('committed','cancelled'))))) THEN
  RAISE EXCEPTION 'staging operation is immutable or already resolved' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER staging_operation_immutable BEFORE UPDATE OR DELETE ON queue_staging_erasure_operations
 FOR EACH ROW EXECUTE FUNCTION staging_operation_immutable();
CREATE TRIGGER a_staging_census_owner_lock BEFORE INSERT OR UPDATE OR DELETE ON queue_staging_copy_custody
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER a_staging_key_owner_lock BEFORE INSERT OR UPDATE OR DELETE ON queue_staging_copy_keys
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER a_staging_operation_owner_lock BEFORE INSERT OR UPDATE OR DELETE ON queue_staging_erasure_operations
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER staging_census_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_staging_copy_custody
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER staging_key_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_staging_copy_keys
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER staging_operation_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_staging_erasure_operations
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();

CREATE FUNCTION staging_copy_mutation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE value jsonb; owner text; known queue_staging_copy_keys%ROWTYPE; current_epoch bigint;
BEGIN
 IF TG_OP='DELETE' THEN value=to_jsonb(OLD); ELSE value=to_jsonb(NEW); END IF;
 IF value->>'tbl'<>'artifacts' OR NOT EXISTS (
   SELECT 1 FROM queue_authority WHERE namespace=value->>'namespace') THEN
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
 END IF;
 owner=coalesce(value->'doc'->>'owner_key',current_setting('omi.queue_owner_key',true));
 IF owner IS NULL OR NOT EXISTS (
   SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'
    AND granted AND mode='ExclusiveLock' AND objsubid=1
    AND classid=((privacy_lock_key(owner) >> 32) & 4294967295)::oid
    AND objid=(privacy_lock_key(owner) & 4294967295)::oid) THEN
  RAISE EXCEPTION 'exclusive owner lock required before registered staging mutation' USING ERRCODE='42501';
 END IF;
 SELECT epoch INTO current_epoch FROM queue_authority WHERE namespace=value->>'namespace' FOR UPDATE;
 SELECT * INTO known FROM queue_staging_copy_keys
  WHERE namespace=value->>'namespace' AND key=value->>'key';
 IF FOUND THEN
  IF TG_OP<>'DELETE' OR NOT EXISTS (
    SELECT 1 FROM queue_staging_erasure_operations o JOIN queue_staging_copy_custody c
     ON c.namespace=o.namespace AND c.recording_id=o.recording_id
     WHERE o.namespace=known.namespace AND o.recording_id=known.recording_id
      AND o.owner_key=known.owner_key AND o.owner_key=owner AND o.state='prepared'
      AND c.manifest->>'epoch'=current_epoch::text
      AND o.operation_id=current_setting('omi.staging_erasure_operation',true)) THEN
   RAISE EXCEPTION 'staging copy requires prepared destructive unit; recreation fenced' USING ERRCODE='42501';
  END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER a_staging_copy_mutation BEFORE INSERT OR UPDATE OR DELETE ON docs
 FOR EACH ROW EXECUTE FUNCTION staging_copy_mutation_guard();
CREATE FUNCTION staging_commit_census() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.state='committed' AND EXISTS (
   SELECT 1 FROM queue_staging_copy_keys k JOIN docs d
    ON d.namespace=k.namespace AND d.tbl='artifacts' AND d.key=k.key
   WHERE k.namespace=NEW.namespace AND k.recording_id=NEW.recording_id) THEN
  RAISE EXCEPTION 'staging COMMIT still has unresolved PG copies' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER staging_commit_census AFTER INSERT OR UPDATE ON queue_staging_erasure_operations
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION staging_commit_census();
REVOKE ALL ON queue_staging_copy_custody,queue_staging_copy_keys,queue_staging_erasure_operations FROM PUBLIC;

CREATE FUNCTION staging_delete_outcome_join() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.tbl='artifacts' AND EXISTS (
   SELECT 1 FROM queue_staging_copy_keys k WHERE k.namespace=OLD.namespace AND k.key=OLD.key)
  AND NOT EXISTS (
   SELECT 1 FROM queue_staging_copy_keys k JOIN queue_staging_erasure_operations o
    ON o.namespace=k.namespace AND o.recording_id=k.recording_id AND o.owner_key=k.owner_key
   WHERE k.namespace=OLD.namespace AND k.key=OLD.key AND o.state='committed'
    AND o.operation_id=current_setting('omi.staging_erasure_operation',true)) THEN
  RAISE EXCEPTION 'staging DELETE and definitive outcome must share COMMIT' USING ERRCODE='42501';
 END IF;
 RETURN OLD;
END $$;
CREATE CONSTRAINT TRIGGER staging_delete_outcome_join AFTER DELETE ON docs
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION staging_delete_outcome_join();

-- Closed queues admit only the already-guarded destructive DELETE, never work.
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
  IF current_setting('omi.queue_epoch',true) IS DISTINCT FROM authority.epoch::text OR
   (authority.state <> 'PG_OPEN' AND NOT (
    TG_OP='DELETE' AND TG_TABLE_NAME='docs' AND value->>'tbl'='artifacts'
    AND EXISTS (SELECT 1 FROM queue_staging_copy_keys k JOIN queue_staging_erasure_operations o
      ON o.namespace=k.namespace AND o.recording_id=k.recording_id AND o.owner_key=k.owner_key
      WHERE k.namespace=ns AND k.key=value->>'key' AND o.state='prepared'
       AND o.operation_id=current_setting('omi.staging_erasure_operation',true)))) THEN
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
