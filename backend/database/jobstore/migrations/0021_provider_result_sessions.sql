-- Ordinary typed result sessions only. No runtime selector, TTL or final purge.
CREATE TABLE queue_provider_uploads (
 namespace text NOT NULL, unit_id text NOT NULL, attempt_token text NOT NULL,
 recording_id text NOT NULL, owner_key text NOT NULL, admission_id uuid NOT NULL,
 object_key text NOT NULL, bucket text NOT NULL, content_hash text NOT NULL,
 original_deadline double precision NOT NULL, effect_id uuid UNIQUE,
 generation bigint CHECK (generation>0),
 phase text NOT NULL DEFAULT 'prepared'
  CHECK (phase IN ('prepared','registered','draining','published','fenced')),
 PRIMARY KEY(namespace,unit_id,attempt_token), UNIQUE(namespace,unit_id), UNIQUE(namespace,object_key),
 FOREIGN KEY(namespace,unit_id) REFERENCES units(namespace,unit_id),
 FOREIGN KEY(namespace,recording_id) REFERENCES queue_handoffs(namespace,identity)
);
CREATE FUNCTION provider_upload_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE unit units%ROWTYPE;
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'original upload custody has no final erasure certificate' USING ERRCODE='42501';
 END IF;
 SELECT * INTO unit FROM units WHERE namespace=NEW.namespace AND unit_id=NEW.unit_id;
 IF NOT FOUND OR unit.owner_key<>NEW.owner_key OR unit.recording_id<>NEW.recording_id
  OR unit.attempt_admission_id IS DISTINCT FROM NEW.admission_id
  OR unit.custody_deadline<>NEW.original_deadline THEN
  RAISE EXCEPTION 'original upload admission/custody mismatch' USING ERRCODE='42501';
 END IF;
 IF TG_OP='INSERT' AND (NEW.phase<>'prepared' OR NEW.effect_id IS NOT NULL
  OR NEW.generation IS NOT NULL OR unit.state<>'pending' OR unit.attempt_token<>NEW.attempt_token) THEN
  RAISE EXCEPTION 'upload reservation requires original pending attempt' USING ERRCODE='42501';
 END IF;
 IF TG_OP='UPDATE' AND (
  (to_jsonb(NEW)-'phase'-'effect_id'-'generation') IS DISTINCT FROM (to_jsonb(OLD)-'phase'-'effect_id'-'generation')
  OR (OLD.effect_id IS NOT NULL AND NEW.effect_id IS DISTINCT FROM OLD.effect_id)
  OR (OLD.generation IS NOT NULL AND NEW.generation IS DISTINCT FROM OLD.generation)
  OR NOT (NEW.phase=OLD.phase OR (OLD.phase='prepared' AND NEW.phase='registered')
   OR (OLD.phase='registered' AND NEW.phase IN ('draining','published'))
   OR (OLD.phase='draining' AND NEW.phase='fenced'))) THEN
  RAISE EXCEPTION 'upload identity or irreversible outcome changed' USING ERRCODE='42501';
 END IF;
 IF NEW.phase<>'prepared' AND NEW.effect_id IS NULL THEN
  RAISE EXCEPTION 'registered upload capability binding required' USING ERRCODE='42501';
 END IF;
 IF NEW.phase='prepared' AND (NEW.effect_id IS NOT NULL OR NEW.generation IS NOT NULL) THEN
  RAISE EXCEPTION 'prepared upload cannot carry an unattached capability or generation' USING ERRCODE='42501';
 END IF;
 IF NEW.phase='published' AND NEW.generation IS NULL THEN
  RAISE EXCEPTION 'original generation required before publication' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER provider_upload_immutable BEFORE INSERT OR UPDATE OR DELETE ON queue_provider_uploads
 FOR EACH ROW EXECUTE FUNCTION provider_upload_immutable();
CREATE TRIGGER provider_upload_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_provider_uploads
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();

-- The actual GCS COMPLETE/retirement and durable job reference share COMMIT.
CREATE FUNCTION provider_upload_effect_join() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE upload queue_provider_uploads%ROWTYPE;
BEGIN
 IF TG_TABLE_NAME='privacy_effect_inflight' THEN
  SELECT * INTO upload FROM queue_provider_uploads WHERE effect_id=OLD.effect_id;
 ELSE
  SELECT * INTO upload FROM queue_provider_uploads
   WHERE namespace=NEW.namespace AND unit_id=NEW.unit_id AND attempt_token=NEW.attempt_token;
 END IF;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF upload.phase='prepared' THEN RETURN NULL; END IF;
 IF (upload.phase IN ('published','fenced')) = EXISTS (
  SELECT 1 FROM privacy_effect_inflight WHERE effect_id=upload.effect_id) THEN
  RAISE EXCEPTION 'GCS capability and original upload outcome must share COMMIT' USING ERRCODE='42501';
 END IF;
 IF upload.phase IN ('registered','draining') AND NOT EXISTS (
  SELECT 1 FROM privacy_effect_inflight e WHERE e.effect_id=upload.effect_id
   AND e.kind='gcs_put' AND e.owner_key=upload.owner_key AND e.admission_id=upload.admission_id
   AND e.sink->>'namespace'=upload.namespace AND e.sink->>'unit_id'=upload.unit_id
   AND e.sink->>'attempt_token'=upload.attempt_token
   AND e.sink->>'bucket'=upload.bucket AND e.sink->>'key'=upload.object_key) THEN
  RAISE EXCEPTION 'GCS original source/sink binding mismatch' USING ERRCODE='42501';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER provider_upload_effect_join AFTER INSERT OR UPDATE ON queue_provider_uploads
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION provider_upload_effect_join();
CREATE CONSTRAINT TRIGGER provider_upload_retirement_join AFTER DELETE ON privacy_effect_inflight
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION provider_upload_effect_join();

CREATE FUNCTION provider_upload_terminal_reference() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE upload queue_provider_uploads%ROWTYPE;
BEGIN
 IF NEW.state='result_ready' THEN
  SELECT * INTO upload FROM queue_provider_uploads WHERE namespace=NEW.namespace AND unit_id=NEW.unit_id;
  IF FOUND AND (upload.phase<>'published' OR upload.admission_id IS DISTINCT FROM NEW.attempt_admission_id
   OR NEW.result->>'result_uri' IS DISTINCT FROM
    ('gs://'||upload.bucket||'/'||upload.object_key||'#'||upload.generation::text)) THEN
   RAISE EXCEPTION 'terminal result differs from original published object' USING ERRCODE='42501';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER provider_upload_terminal_reference BEFORE UPDATE ON units
 FOR EACH ROW EXECUTE FUNCTION provider_upload_terminal_reference();
REVOKE ALL ON queue_provider_uploads FROM PUBLIC;

CREATE FUNCTION provider_upload_owner_lock() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE exclusive_needed boolean;
BEGIN
 exclusive_needed=NEW.phase IN ('draining','fenced');
 IF NOT EXISTS (SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'
  AND granted AND (mode='ExclusiveLock' OR (NOT exclusive_needed AND mode='ShareLock')) AND objsubid=1
  AND classid=((privacy_lock_key(NEW.owner_key) >> 32) & 4294967295)::oid
  AND objid=(privacy_lock_key(NEW.owner_key) & 4294967295)::oid) THEN
  RAISE EXCEPTION 'original upload owner guard required before mutation' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER a_provider_upload_owner_lock BEFORE INSERT OR UPDATE ON queue_provider_uploads
 FOR EACH ROW EXECUTE FUNCTION provider_upload_owner_lock();
CREATE TRIGGER provider_upload_journal AFTER INSERT OR UPDATE OR DELETE ON queue_provider_uploads
 FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();

-- Narrow closed-queue upload-fencing progress, never a new work publication.
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
       AND o.operation_id=current_setting('omi.staging_erasure_operation',true)))
    AND NOT (TG_OP='UPDATE' AND TG_TABLE_NAME='queue_provider_uploads'
     AND value->>'phase' IN ('draining','fenced'))) THEN
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
