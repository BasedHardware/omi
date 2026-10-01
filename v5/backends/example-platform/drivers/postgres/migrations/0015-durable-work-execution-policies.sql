-- P3 immutable execution-policy binding. Historical qualification rows remain
-- explicitly legacy/unbound; the NOT VALID checks and foreign key enforce the
-- policy coordinate on every row inserted after this migration.

CREATE FUNCTION omi_memory.valid_memory_work_retry_delays(
  delays jsonb,
  expected_count integer
)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $$
DECLARE
  delay_value jsonb;
  delay_text text;
BEGIN
  IF jsonb_typeof(delays) <> 'array'
     OR jsonb_array_length(delays) <> expected_count THEN
    RETURN false;
  END IF;
  FOR delay_value IN SELECT value FROM jsonb_array_elements(delays)
  LOOP
    IF jsonb_typeof(delay_value) <> 'number' THEN
      RETURN false;
    END IF;
    delay_text := delay_value::text;
    IF delay_text !~ '^[0-9]+$'
       OR length(delay_text) > 5
       OR delay_text::integer NOT BETWEEN 1 AND 86400 THEN
      RETURN false;
    END IF;
  END LOOP;
  RETURN true;
END
$$;

REVOKE ALL ON FUNCTION omi_memory.valid_memory_work_retry_delays(jsonb, integer)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.valid_memory_work_retry_delays(jsonb, integer)
  TO omi_platform_application;

CREATE TABLE omi_memory.memory_work_execution_policies (
  account_id text NOT NULL,
  policy_id text NOT NULL CHECK (length(policy_id) BETWEEN 1 AND 256),
  policy_version text NOT NULL
    CHECK (policy_version = 'durable-memory-work-execution-policy-v1'),
  policy_digest text NOT NULL CHECK (policy_digest ~ '^[0-9a-f]{64}$'),
  work_kind text NOT NULL CHECK (work_kind IN (
    'formation', 'promotion', 'identity_cluster', 'predicate_batch'
  )),
  execution_contract_digest text NOT NULL
    CHECK (execution_contract_digest ~ '^[0-9a-f]{64}$'),
  max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 100),
  lease_duration_seconds integer NOT NULL
    CHECK (lease_duration_seconds BETWEEN 1 AND 3600),
  retry_delays_seconds jsonb NOT NULL,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, policy_id),
  UNIQUE (
    account_id, policy_id, policy_digest, work_kind,
    execution_contract_digest, max_attempts
  ),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id),
  CHECK (omi_memory.valid_memory_work_retry_delays(
    retry_delays_seconds, max_attempts - 1
  ))
);

ALTER TABLE omi_memory.memory_work_acceptances
  ADD COLUMN execution_policy_id text,
  ADD COLUMN execution_policy_digest text
    CHECK (execution_policy_digest IS NULL OR execution_policy_digest ~ '^[0-9a-f]{64}$');

ALTER TABLE omi_memory.memory_work_acceptances
  ADD CONSTRAINT memory_work_acceptances_execution_policy_required
  CHECK (execution_policy_id IS NOT NULL AND execution_policy_digest IS NOT NULL)
  NOT VALID;

ALTER TABLE omi_memory.memory_work_acceptances
  ADD CONSTRAINT memory_work_acceptances_execution_policy_fk
  FOREIGN KEY (
    account_id, execution_policy_id, execution_policy_digest,
    work_kind, execution_contract_digest, max_attempts
  ) REFERENCES omi_memory.memory_work_execution_policies (
    account_id, policy_id, policy_digest,
    work_kind, execution_contract_digest, max_attempts
  ) NOT VALID;

REVOKE ALL ON omi_memory.memory_work_execution_policies FROM PUBLIC;
GRANT SELECT, INSERT ON omi_memory.memory_work_execution_policies
  TO omi_platform_application;

-- The application still has no UPDATE or DELETE on policy or acceptance rows.
