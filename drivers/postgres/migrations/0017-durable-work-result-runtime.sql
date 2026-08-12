-- P3 sensitive normalized-result staging. The application role never receives
-- table privileges on memory_work_staged_results. These fixed functions bind
-- every access to the transaction-local tenant and execute capability already
-- established and revalidated by the sealed PostgreSQL transaction adapter.

CREATE FUNCTION omi_memory.read_durable_work_staged_result(
  requested_account_id text,
  requested_job_id text
)
RETURNS TABLE (
  result_version text,
  staged_result_id text,
  account_id text,
  job_id text,
  accepted_work_digest text,
  work_kind text,
  input_frontier text,
  execution_contract_digest text,
  produced_attempt integer,
  produced_lease_fence bigint,
  produced_state_digest text,
  producer_worker_id text,
  result_contract_version text,
  response_digest text,
  normalized_result_digest text,
  normalized_result_json jsonb,
  stage_request_digest text,
  content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.work.execute'
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'durable work result access denied';
  END IF;

  IF NOT EXISTS (
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
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'durable work result lease denied';
  END IF;

  RETURN QUERY
  SELECT
    r.result_version, r.staged_result_id, r.account_id, r.job_id,
    r.accepted_work_digest, r.work_kind, r.input_frontier,
    r.execution_contract_digest, r.produced_attempt,
    r.produced_lease_fence, r.produced_state_digest, r.producer_worker_id,
    r.result_contract_version, r.response_digest, r.normalized_result_digest,
    r.normalized_result_json, r.stage_request_digest, r.content_hash
  FROM omi_memory.memory_work_staged_results AS r
  WHERE r.account_id = requested_account_id AND r.job_id = requested_job_id;
END;
$$;

CREATE FUNCTION omi_memory.insert_durable_work_staged_result(
  requested_account_id text,
  requested_staged_result_id text,
  requested_job_id text,
  requested_result_version text,
  requested_accepted_work_digest text,
  requested_work_kind text,
  requested_input_frontier text,
  requested_execution_contract_digest text,
  requested_produced_attempt integer,
  requested_produced_lease_fence bigint,
  requested_produced_state_digest text,
  requested_producer_worker_id text,
  requested_result_contract_version text,
  requested_response_digest text,
  requested_normalized_result_digest text,
  requested_normalized_result_json jsonb,
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
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.work.execute'
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'durable work result access denied';
  END IF;

  IF requested_producer_worker_id
       IS DISTINCT FROM current_setting('omi.principal_id', true)
     OR NOT EXISTS (
       SELECT 1
       FROM omi_memory.memory_work_heads AS h
       JOIN omi_memory.memory_work_state_revisions AS s
         ON s.account_id = h.account_id AND s.job_id = h.job_id
        AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
       WHERE h.account_id = requested_account_id
         AND h.job_id = requested_job_id
         AND s.state = 'leased'
         AND s.state_digest = requested_produced_state_digest
         AND s.attempt = requested_produced_attempt
         AND s.lease_fence = requested_produced_lease_fence
         AND s.worker_id = requested_producer_worker_id
         AND s.lease_expires_at_event_time
           > floor(extract(epoch FROM transaction_timestamp()))::bigint
     )
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'durable work result lease denied';
  END IF;

  INSERT INTO omi_memory.memory_work_staged_results (
    account_id, staged_result_id, job_id, result_version,
    accepted_work_digest, work_kind, input_frontier, execution_contract_digest,
    produced_attempt, produced_lease_fence, produced_state_digest,
    produced_state, producer_worker_id, result_contract_version,
    response_digest, normalized_result_digest, normalized_result_json,
    stage_request_digest, content_hash
  ) VALUES (
    requested_account_id, requested_staged_result_id, requested_job_id,
    requested_result_version, requested_accepted_work_digest,
    requested_work_kind, requested_input_frontier,
    requested_execution_contract_digest, requested_produced_attempt,
    requested_produced_lease_fence, requested_produced_state_digest,
    'leased', requested_producer_worker_id, requested_result_contract_version,
    requested_response_digest, requested_normalized_result_digest,
    requested_normalized_result_json, requested_stage_request_digest,
    requested_content_hash
  );
  RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION omi_memory.read_durable_work_staged_result(text, text)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.insert_durable_work_staged_result(
  text, text, text, text, text, text, text, text, integer, bigint,
  text, text, text, text, text, jsonb, text, text
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.read_durable_work_staged_result(text, text)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.insert_durable_work_staged_result(
  text, text, text, text, text, text, text, text, integer, bigint,
  text, text, text, text, text, jsonb, text, text
) TO omi_platform_application;
