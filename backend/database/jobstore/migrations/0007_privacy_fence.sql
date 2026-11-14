-- G2 Rev 3 §2.2; original 0006 maps to 0006 (main ended at 0005).
CREATE TABLE privacy_owner_fence (
  owner_key        text PRIMARY KEY CHECK (owner_key ~ '^[0-9a-f]{64}$'),   -- privacy_owner_key(uid)
  generation       bigint NOT NULL CHECK (generation >= 0),
  change_seq       bigint NOT NULL DEFAULT 0,          -- bumped by EVERY close (owner or conversation)
  pending_changes  int    NOT NULL DEFAULT 0 CHECK (pending_changes >= 0),   -- count of 'pending' rows below
  state            text   NOT NULL CHECK (state IN ('open','closed','purging','erased')),
  close_reason     text   CHECK (close_reason IN ('deleted','data_protection','recording_privacy','detector','unknown')),
  purge_generation bigint,
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CHECK ((state = 'open') = (close_reason IS NULL))
);

CREATE TABLE privacy_fence_change (                  -- one row per narrowing close (per-sequence settlement)
  owner_key   text   NOT NULL,
  seq         bigint NOT NULL,
  state       text   NOT NULL CHECK (state IN ('pending','landed','abandoned','local')),
  guard_version timestamptz,                        -- G(o).update_time the Commit is preconditioned on
  PRIMARY KEY (owner_key, seq)
);

CREATE TABLE privacy_conversation_fence (
  owner_key        text NOT NULL,
  conversation_key text NOT NULL CHECK (conversation_key ~ '^[0-9a-f]{64}$'),  -- sha256(owner_key || '/' || cid)
  generation       bigint NOT NULL,
  state            text   NOT NULL CHECK (state IN ('open','closed','redirected','deleted')),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_key, conversation_key)
);  -- an absent row means generation 0, open

CREATE TABLE privacy_effect_inflight (               -- exists only while an effect is unresolved (§3.5.5)
  effect_id        uuid PRIMARY KEY,
  owner_key        text NOT NULL,
  job_key          text NOT NULL,
  kind             text NOT NULL CHECK (kind IN ('provider','vector','push','outbox','gcs_put')),
  admission_id     uuid   NOT NULL,                 -- immutable fingerprint (INV-16):
  owner_generation bigint NOT NULL,                 --   the admission and P values at registration
  change_seq       bigint NOT NULL,
  target_gens      jsonb  NOT NULL,                 --   [{conversation_key, generation}]
  conversation_keys text[] NOT NULL,               -- for conversation-scoped drains and residue targets
  state            text NOT NULL CHECK (state IN ('registered','started')),
  lease_until      timestamptz NOT NULL,            -- liveness only; never authorizes (INV-11)
  sink             jsonb                            -- gcs_put only: bucket, key, size, session capability
);
CREATE INDEX ON privacy_effect_inflight (owner_key);

CREATE TABLE privacy_residue_target (                -- retained metadata (A4)
  owner_key        text NOT NULL,
  conversation_key text,                            -- NULL = owner scope
  kind             text NOT NULL CHECK (kind IN ('vector')),
  created_at       timestamptz NOT NULL DEFAULT now(),
  passes_done      int NOT NULL DEFAULT 0
);

CREATE TABLE privacy_fence_config (enforce_protocol int NOT NULL);   -- single row; 1 = walk/shadow, 2 = enforce


ALTER TABLE privacy_fence_config ADD COLUMN singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton);
ALTER TABLE privacy_fence_config ADD CONSTRAINT privacy_protocol_value CHECK (enforce_protocol IN (1,2));
INSERT INTO privacy_fence_config(enforce_protocol) VALUES (1);

ALTER TABLE jobs ADD COLUMN admission_id uuid GENERATED ALWAYS AS ((doc->>'admission_id')::uuid) STORED;
ALTER TABLE jobs ADD COLUMN admission_version int GENERATED ALWAYS AS ((doc->>'admission_version')::int) STORED;

CREATE FUNCTION privacy_lock_key(owner text) RETURNS bigint LANGUAGE sql IMMUTABLE STRICT AS $$
 SELECT ('x' || substr(encode(sha256(convert_to('privacy_fence/' || owner, 'UTF8')), 'hex'), 1, 16))::bit(64)::bigint
$$;

CREATE FUNCTION privacy_monotone() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 -- Closers must acquire L_x BEFORE reading. Never upgrade a shared lock here.
 IF NOT EXISTS (SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'
   AND granted AND mode='ExclusiveLock' AND objsubid=1
   AND classid=((privacy_lock_key(NEW.owner_key) >> 32) & 4294967295)::oid
   AND objid=(privacy_lock_key(NEW.owner_key) & 4294967295)::oid) THEN
  RAISE EXCEPTION 'exclusive privacy lock required before transition';
 END IF;
 IF NEW.generation < OLD.generation THEN RAISE EXCEPTION 'privacy generation decreased'; END IF;
 IF TG_TABLE_NAME = 'privacy_owner_fence' THEN
  IF NEW.change_seq < OLD.change_seq THEN RAISE EXCEPTION 'privacy sequence decreased'; END IF;
  IF OLD.state = 'erased' AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'erased fence is terminal'; END IF;
 ELSE
  IF OLD.state = 'deleted' AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'deleted fence is terminal'; END IF;
 END IF;
 IF NEW.state = 'open' AND OLD.state <> 'open' AND NEW.generation <> OLD.generation + 1 THEN
  RAISE EXCEPTION 'reopen requires next generation';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER privacy_owner_monotone BEFORE UPDATE ON privacy_owner_fence
 FOR EACH ROW EXECUTE FUNCTION privacy_monotone();
CREATE TRIGGER privacy_conversation_monotone BEFORE UPDATE ON privacy_conversation_fence
 FOR EACH ROW EXECUTE FUNCTION privacy_monotone();
CREATE FUNCTION privacy_change_terminal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.state <> 'pending' AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'settled change is immutable'; END IF;
 IF NEW.owner_key <> OLD.owner_key OR NEW.seq <> OLD.seq OR NEW.guard_version IS DISTINCT FROM OLD.guard_version THEN
  RAISE EXCEPTION 'change identity is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER privacy_change_terminal BEFORE UPDATE ON privacy_fence_change
 FOR EACH ROW EXECUTE FUNCTION privacy_change_terminal();

CREATE FUNCTION privacy_protocol_barrier() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (SELECT enforce_protocol FROM privacy_fence_config WHERE singleton) = 2
   AND current_setting('omi.privacy_fence_protocol', true) IS DISTINCT FROM '2' THEN
  RAISE EXCEPTION 'privacy protocol 2 required' USING ERRCODE = '42501';
 END IF;
 IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER privacy_jobs_protocol BEFORE INSERT OR UPDATE OR DELETE ON jobs
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER privacy_results_protocol BEFORE INSERT OR UPDATE OR DELETE ON results
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER privacy_docs_protocol BEFORE INSERT OR UPDATE OR DELETE ON docs
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER privacy_outbox_protocol BEFORE INSERT OR UPDATE OR DELETE ON outbox
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
CREATE TRIGGER privacy_effect_protocol BEFORE INSERT OR UPDATE OR DELETE ON privacy_effect_inflight
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();

-- No role or IAM mutation: runtime grants are supplied separately by an operator.
REVOKE ALL ON privacy_owner_fence, privacy_conversation_fence, privacy_fence_change,
 privacy_fence_config, privacy_residue_target FROM PUBLIC;

CREATE FUNCTION privacy_effect_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.effect_id,NEW.owner_key,NEW.job_key,NEW.kind,NEW.admission_id,NEW.owner_generation,
     NEW.change_seq,NEW.target_gens,NEW.conversation_keys,NEW.sink) IS DISTINCT FROM
    (OLD.effect_id,OLD.owner_key,OLD.job_key,OLD.kind,OLD.admission_id,OLD.owner_generation,
     OLD.change_seq,OLD.target_gens,OLD.conversation_keys,OLD.sink) THEN
  RAISE EXCEPTION 'effect admission fingerprint and sink are immutable';
 END IF;
 IF OLD.state='started' AND NEW.state<>'started' THEN RAISE EXCEPTION 'START is irreversible'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER privacy_effect_immutable BEFORE UPDATE ON privacy_effect_inflight
 FOR EACH ROW EXECUTE FUNCTION privacy_effect_immutable();
CREATE TRIGGER privacy_control_protocol BEFORE INSERT OR UPDATE OR DELETE ON control
 FOR EACH ROW EXECUTE FUNCTION privacy_protocol_barrier();
