-- P3 exact formation input persistence. The sensitive snapshot is staged in a
-- committed transaction before work acceptance; therefore a failed acceptance
-- may leave an inert orphan, while accepted formation work can never lose the
-- exact bytes required after process loss.

CREATE TABLE omi_memory.memory_formation_work_inputs (
  account_id text NOT NULL,
  staged_input_id text NOT NULL CHECK (staged_input_id ~ '^fwi1_[0-9a-f]{64}$'),
  job_id text NOT NULL CHECK (length(job_id) BETWEEN 1 AND 256),
  input_version text NOT NULL CHECK (input_version = 'formation-work-staged-input-v1'),
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  accepted_work_digest text NOT NULL CHECK (accepted_work_digest ~ '^[0-9a-f]{64}$'),
  input_frontier text NOT NULL CHECK (length(input_frontier) BETWEEN 1 AND 256),
  input_digest text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
  execution_contract_digest text NOT NULL
    CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  snapshot_digest text NOT NULL CHECK (snapshot_digest ~ '^[0-9a-f]{64}$'),
  snapshot_version text NOT NULL CHECK (snapshot_version = 'formation-input-snapshot-v1'),
  snapshot_json jsonb NOT NULL CHECK (
    jsonb_typeof(snapshot_json) = 'object'
    AND octet_length(snapshot_json::text) <= 524288
  ),
  stage_request_digest text NOT NULL CHECK (stage_request_digest ~ '^[0-9a-f]{64}$'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, job_id),
  UNIQUE (account_id, staged_input_id),
  FOREIGN KEY (account_id) REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE FUNCTION omi_memory.require_formation_work_input()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
BEGIN
  IF NEW.work_kind = 'formation' AND NOT EXISTS (
    SELECT 1
    FROM omi_memory.memory_formation_work_inputs AS i
    WHERE i.account_id = NEW.account_id
      AND i.job_id = NEW.job_id
      AND i.account_epoch = NEW.account_epoch
      AND i.accepted_work_digest = NEW.accepted_work_digest
      AND i.input_frontier = NEW.input_frontier
      AND i.input_digest = NEW.input_digest
      AND i.execution_contract_digest = NEW.execution_contract_digest
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '23503', MESSAGE = 'formation work input missing';
  END IF;
  RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER memory_formation_acceptance_requires_input
AFTER INSERT ON omi_memory.memory_work_acceptances
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION omi_memory.require_formation_work_input();

CREATE FUNCTION omi_memory.read_formation_work_input(
  requested_account_id text,
  requested_job_id text
)
RETURNS TABLE (
  input_version text,
  staged_input_id text,
  account_id text,
  job_id text,
  account_epoch bigint,
  accepted_work_digest text,
  input_frontier text,
  input_digest text,
  execution_contract_digest text,
  snapshot_digest text,
  snapshot_json jsonb,
  stage_request_digest text,
  content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
DECLARE
  capability text := current_setting('omi.capability', true);
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR capability NOT IN ('memories.work.accept', 'memories.work.execute')
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'formation work input access denied';
  END IF;

  IF capability = 'memories.work.execute' AND NOT EXISTS (
    SELECT 1
    FROM omi_memory.memory_work_heads AS h
    JOIN omi_memory.memory_work_state_revisions AS s
      ON s.account_id = h.account_id AND s.job_id = h.job_id
     AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
    WHERE h.account_id = requested_account_id
      AND h.job_id = requested_job_id
      AND s.state = 'leased'
      AND s.worker_id = current_setting('omi.principal_id', true)
      AND s.lease_expires_at_event_time
        > floor(extract(epoch FROM transaction_timestamp()))::bigint
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'formation work input lease denied';
  END IF;

  RETURN QUERY
  SELECT
    i.input_version, i.staged_input_id, i.account_id, i.job_id, i.account_epoch,
    i.accepted_work_digest, i.input_frontier, i.input_digest,
    i.execution_contract_digest, i.snapshot_digest, i.snapshot_json,
    i.stage_request_digest, i.content_hash
  FROM omi_memory.memory_formation_work_inputs AS i
  WHERE i.account_id = requested_account_id AND i.job_id = requested_job_id;
END;
$$;

CREATE FUNCTION omi_memory.insert_formation_work_input(
  requested_account_id text,
  requested_staged_input_id text,
  requested_job_id text,
  requested_input_version text,
  requested_account_epoch bigint,
  requested_accepted_work_digest text,
  requested_input_frontier text,
  requested_input_digest text,
  requested_execution_contract_digest text,
  requested_snapshot_digest text,
  requested_snapshot_version text,
  requested_snapshot_json jsonb,
  requested_stage_request_digest text,
  requested_content_hash text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.work.accept'
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'formation work input access denied';
  END IF;

  INSERT INTO omi_memory.memory_formation_work_inputs (
    account_id, staged_input_id, job_id, input_version, account_epoch,
    accepted_work_digest, input_frontier, input_digest, execution_contract_digest,
    snapshot_digest, snapshot_version, snapshot_json, stage_request_digest, content_hash
  ) VALUES (
    requested_account_id, requested_staged_input_id, requested_job_id,
    requested_input_version, requested_account_epoch, requested_accepted_work_digest,
    requested_input_frontier, requested_input_digest,
    requested_execution_contract_digest, requested_snapshot_digest,
    requested_snapshot_version, requested_snapshot_json,
    requested_stage_request_digest, requested_content_hash
  );
  RETURN true;
END;
$$;

REVOKE ALL ON omi_memory.memory_formation_work_inputs FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.require_formation_work_input() FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_formation_work_input(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.insert_formation_work_input(
  text, text, text, text, bigint, text, text, text, text, text, text, jsonb, text, text
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.read_formation_work_input(text, text)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.insert_formation_work_input(
  text, text, text, text, bigint, text, text, text, text, text, text, jsonb, text, text
) TO omi_platform_application;

-- No direct table grant and no runtime composition. The trigger protects only
-- newly inserted formation acceptances; historical rows remain readable only
-- through their existing explicitly legacy paths.
