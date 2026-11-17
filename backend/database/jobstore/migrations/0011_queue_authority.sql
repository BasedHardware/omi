-- D queue authority and D4/W4 corrected typed schema. Dark: no serving factory
-- selects these tables. 0006 is the G2 Rev 3 fence; 0007 adds the next layer.
CREATE TABLE queue_authority (
 namespace text PRIMARY KEY,
 state text NOT NULL DEFAULT 'FS_OPEN' CHECK (state IN ('FS_OPEN','FS_CLOSING','BOTH_CLOSED','PG_OPEN','PG_CLOSING')),
 epoch bigint NOT NULL DEFAULT 0 CHECK (epoch >= 0),
 committed_seq bigint NOT NULL DEFAULT 0,
 copier_stopped boolean NOT NULL DEFAULT true,
 applied_seq bigint NOT NULL DEFAULT 0 CHECK (applied_seq >= 0 AND applied_seq <= committed_seq)
);
CREATE TABLE queue_journal (
 namespace text NOT NULL, seq bigint NOT NULL, epoch bigint NOT NULL,
 family text NOT NULL, identity jsonb NOT NULL, operation text NOT NULL CHECK (operation IN ('put','delete')),
 owner_key text NOT NULL, body jsonb, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(namespace,seq)
);
CREATE INDEX queue_journal_owner ON queue_journal(namespace,owner_key);
CREATE TABLE queue_custody (
 namespace text NOT NULL, identity text NOT NULL, owner_key text NOT NULL,
 epoch bigint NOT NULL, admission_id uuid NOT NULL,
 phase text NOT NULL CHECK (phase IN ('admitted','completed','projected','acked')),
 fingerprint text NOT NULL, completion jsonb, projection_receipt text,
 PRIMARY KEY(namespace,identity)
);

CREATE TABLE units (
 namespace text NOT NULL, unit_id text NOT NULL, owner_key text NOT NULL,
 recording_id text NOT NULL, capture_at float8 NOT NULL, stage text NOT NULL,
 state text NOT NULL CHECK (state IN ('pending','result_ready','quarantined','privacy_blocked')),
 class smallint NOT NULL CHECK (class IN (0,1)), hold_reason text,
 owner_turn bigint NOT NULL, due_at float8, lease_token text, lease_until float8 NOT NULL DEFAULT 0,
 attempt_token text, attempt_history jsonb NOT NULL DEFAULT '[]', attempts int NOT NULL DEFAULT 0,
 custody_deadline float8 NOT NULL, privacy_generation bigint NOT NULL,
 admission jsonb NOT NULL, result jsonb, created_at float8 NOT NULL,
 PRIMARY KEY(namespace,unit_id)
);
CREATE INDEX units_pull ON units(namespace,stage,class,owner_turn,capture_at)
 WHERE state='pending' AND hold_reason IS NULL;
CREATE INDEX units_owner_pending ON units(namespace,owner_key) WHERE state='pending' AND hold_reason IS NULL;
CREATE INDEX units_recording ON units(namespace,recording_id) WHERE state <> 'pending';
CREATE TABLE recordings (
 namespace text NOT NULL, recording_id text NOT NULL, owner_key text NOT NULL,
 units_total int NOT NULL CHECK (units_total > 0), units_final int NOT NULL DEFAULT 0,
 projection_state text NOT NULL DEFAULT 'pending' CHECK (projection_state IN ('pending','projected','revoked')),
 first_capture_at float8, partial_deadline float8, projection_task_id bigint,
 CHECK (units_final >= 0 AND units_final <= units_total),
 PRIMARY KEY(namespace,recording_id)
);
CREATE TABLE budgets (
 namespace text NOT NULL, scope text NOT NULL, period text NOT NULL,
 decision text CHECK (decision IN ('allowed','refused')), limit_value numeric NOT NULL,
 reserved numeric NOT NULL DEFAULT 0, spent numeric NOT NULL DEFAULT 0,
 CHECK (reserved >= 0 AND spent >= 0 AND reserved+spent <= limit_value),
 PRIMARY KEY(namespace,scope,period)
);
CREATE TRIGGER privacy_units_protocol BEFORE INSERT OR UPDATE OR DELETE ON units
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER privacy_recordings_protocol BEFORE INSERT OR UPDATE OR DELETE ON recordings
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER privacy_budgets_protocol BEFORE INSERT OR UPDATE OR DELETE ON budgets
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER privacy_custody_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_custody
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();

CREATE FUNCTION queue_authority_monotone() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.epoch < OLD.epoch OR NEW.committed_seq < OLD.committed_seq OR NEW.applied_seq < OLD.applied_seq THEN
  RAISE EXCEPTION 'queue counters cannot decrease';
 END IF;
 IF NEW.state <> OLD.state THEN
  IF NEW.epoch <> OLD.epoch+1 OR NOT (
   (OLD.state='FS_OPEN' AND NEW.state='FS_CLOSING') OR
   (OLD.state='FS_CLOSING' AND NEW.state='BOTH_CLOSED') OR
   (OLD.state='BOTH_CLOSED' AND NEW.state IN ('PG_OPEN','FS_OPEN')) OR
   (OLD.state='PG_OPEN' AND NEW.state='PG_CLOSING') OR
   (OLD.state='PG_CLOSING' AND NEW.state='BOTH_CLOSED')) THEN
   RAISE EXCEPTION 'invalid queue authority transition';
  END IF;
 ELSIF NEW.epoch <> OLD.epoch THEN
  RAISE EXCEPTION 'epoch changes only on authority transition';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER queue_authority_monotone BEFORE UPDATE ON queue_authority
 FOR EACH ROW EXECUTE FUNCTION queue_authority_monotone();

-- Registered PG-authoritative namespaces fence old images at the database, and
-- every mutation (including expiry/delete/custody/outbox) joins its journal.
-- Unregistered namespaces retain the existing dark mirror behavior.
CREATE FUNCTION queue_mutation_journal() RETURNS trigger LANGUAGE plpgsql AS $$
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
  ident=jsonb_strip_nulls(jsonb_build_object('key',value->'key','tbl',value->'tbl',
   'unit_id',value->'unit_id','recording_id',value->'recording_id','identity',value->'identity',
   'id',value->'id','scope',value->'scope','period',value->'period'));
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
CREATE TRIGGER queue_jobs_journal AFTER INSERT OR UPDATE OR DELETE ON jobs FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE TRIGGER queue_results_journal AFTER INSERT OR UPDATE OR DELETE ON results FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE TRIGGER queue_control_journal AFTER INSERT OR UPDATE OR DELETE ON control FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE TRIGGER queue_docs_journal AFTER INSERT OR UPDATE OR DELETE ON docs FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE TRIGGER queue_outbox_journal AFTER INSERT OR UPDATE OR DELETE ON outbox FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE TRIGGER queue_units_journal AFTER INSERT OR UPDATE OR DELETE ON units FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE TRIGGER queue_recordings_journal AFTER INSERT OR UPDATE OR DELETE ON recordings FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE TRIGGER queue_budgets_journal AFTER INSERT OR UPDATE OR DELETE ON budgets FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE TRIGGER queue_custody_journal AFTER INSERT OR UPDATE OR DELETE ON queue_custody FOR EACH ROW EXECUTE FUNCTION queue_mutation_journal();
CREATE TRIGGER privacy_journal_protocol BEFORE INSERT OR UPDATE OR DELETE ON queue_journal
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
