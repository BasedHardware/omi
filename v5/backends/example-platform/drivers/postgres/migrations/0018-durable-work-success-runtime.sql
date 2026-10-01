-- P3 atomic durable-work success runtime. Sensitive stage and success tables
-- remain ungranted. Fixed functions expose the exact staged artifact only to
-- the sealed lease-bound adapter and one exact lease-bound success insert.

CREATE FUNCTION omi_memory.read_durable_work_success_bundle(
  requested_account_id text,
  requested_job_id text
)
RETURNS TABLE (
  staged_result_id text,
  staged_accepted_work_digest text,
  staged_work_kind text,
  staged_input_frontier text,
  staged_execution_contract_digest text,
  staged_produced_attempt integer,
  staged_produced_lease_fence bigint,
  staged_produced_state_digest text,
  staged_producer_worker_id text,
  staged_result_contract_version text,
  staged_response_digest text,
  staged_normalized_result_digest text,
  staged_normalized_result_json jsonb,
  staged_stage_request_digest text,
  staged_content_hash text,
  success_terminal_state_revision bigint,
  success_terminal_state_digest text,
  success_work_kind text,
  success_input_frontier text,
  success_result_kind text,
  success_response_digest text,
  success_result_digest text,
  success_origin_code text,
  success_graph_commit_id text,
  success_graph_commit_sequence bigint,
  success_graph_success_kind text,
  success_append_receipt_state text,
  success_staged_result_id text,
  success_staged_result_digest text,
  success_content_hash text,
  outbox_id text,
  outbox_terminal_state_revision bigint,
  outbox_terminal_state_digest text,
  outbox_terminal_state text,
  outbox_event_kind text,
  outbox_result_digest text,
  outbox_created_at_event_time bigint,
  outbox_content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.work.execute'
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'durable work success access denied';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM omi_memory.memory_work_heads AS h
    JOIN omi_memory.memory_work_state_revisions AS s
      ON s.account_id = h.account_id AND s.job_id = h.job_id
     AND s.state_revision = h.state_revision AND s.state_digest = h.state_digest
    WHERE h.account_id = requested_account_id
      AND h.job_id = requested_job_id
      AND (
        s.state = 'succeeded'
        OR (s.state = 'leased'
          AND s.worker_id = current_setting('omi.principal_id', true)
          AND s.lease_expires_at_event_time
            > floor(extract(epoch FROM transaction_timestamp()))::bigint)
      )
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'durable work success state denied';
  END IF;

  RETURN QUERY
  SELECT
    st.staged_result_id,
    st.accepted_work_digest,
    st.work_kind,
    st.input_frontier,
    st.execution_contract_digest,
    st.produced_attempt,
    st.produced_lease_fence,
    st.produced_state_digest,
    st.producer_worker_id,
    st.result_contract_version,
    st.response_digest,
    st.normalized_result_digest,
    st.normalized_result_json,
    st.stage_request_digest,
    st.content_hash,
    su.terminal_state_revision,
    su.terminal_state_digest,
    su.work_kind,
    su.input_frontier,
    su.result_kind,
    su.response_digest,
    su.result_digest,
    su.origin_code,
    su.graph_commit_id,
    su.graph_commit_sequence,
    su.graph_success_kind,
    su.append_receipt_state,
    su.staged_result_id,
    su.staged_result_digest,
    su.content_hash,
    ob.outbox_id,
    ob.terminal_state_revision,
    ob.terminal_state_digest,
    ob.terminal_state,
    ob.event_kind,
    ob.result_digest,
    ob.created_at_event_time,
    ob.content_hash
  FROM omi_memory.memory_work_staged_results AS st
  LEFT JOIN omi_memory.memory_work_success_results AS su
    ON su.account_id = st.account_id AND su.job_id = st.job_id
  LEFT JOIN omi_memory.memory_work_outbox_events AS ob
    ON ob.account_id = su.account_id AND ob.job_id = su.job_id
   AND ob.terminal_state_revision = su.terminal_state_revision
   AND ob.event_kind = 'memory_work_succeeded'
  WHERE st.account_id = requested_account_id AND st.job_id = requested_job_id;
END;
$$;

CREATE FUNCTION omi_memory.insert_durable_work_success_result(
  requested_account_id text,
  requested_job_id text,
  requested_terminal_state_revision bigint,
  requested_terminal_state_digest text,
  requested_work_kind text,
  requested_input_frontier text,
  requested_result_kind text,
  requested_response_digest text,
  requested_result_digest text,
  requested_origin_code text,
  requested_graph_commit_id text,
  requested_graph_commit_sequence bigint,
  requested_graph_success_kind text,
  requested_append_receipt_state text,
  requested_staged_result_id text,
  requested_staged_result_digest text,
  requested_content_hash text,
  requested_leased_state_digest text,
  requested_attempt integer,
  requested_lease_fence bigint,
  requested_worker_id text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.work.execute'
     OR current_setting('omi.principal_id', true) IS DISTINCT FROM requested_worker_id
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'durable work success access denied';
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
      AND s.state_digest = requested_leased_state_digest
      AND s.attempt = requested_attempt
      AND s.lease_fence = requested_lease_fence
      AND s.worker_id = requested_worker_id
      AND s.lease_expires_at_event_time
        > floor(extract(epoch FROM transaction_timestamp()))::bigint
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'durable work success lease denied';
  END IF;

  INSERT INTO omi_memory.memory_work_success_results (
    account_id, job_id, terminal_state_revision, terminal_state_digest,
    terminal_state, work_kind, input_frontier, result_kind, response_digest,
    result_digest, origin_code, graph_commit_id, graph_commit_sequence,
    graph_success_kind, append_receipt_state, staged_result_id,
    staged_result_digest, content_hash
  ) VALUES (
    requested_account_id, requested_job_id, requested_terminal_state_revision,
    requested_terminal_state_digest, 'succeeded', requested_work_kind,
    requested_input_frontier, requested_result_kind, requested_response_digest,
    requested_result_digest, requested_origin_code, requested_graph_commit_id,
    requested_graph_commit_sequence, requested_graph_success_kind,
    requested_append_receipt_state, requested_staged_result_id,
    requested_staged_result_digest, requested_content_hash
  );
  RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION omi_memory.read_durable_work_success_bundle(text, text)
  FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.insert_durable_work_success_result(
  text, text, bigint, text, text, text, text, text, text, text, text,
  bigint, text, text, text, text, text, text, integer, bigint, text
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.read_durable_work_success_bundle(text, text)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.insert_durable_work_success_result(
  text, text, bigint, text, text, text, text, text, text, text, text,
  bigint, text, text, text, text, text, text, integer, bigint, text
) TO omi_platform_application;

-- No SELECT/INSERT/UPDATE/DELETE privilege is granted on staged results or
-- success results. Work state/head/outbox and graph grants remain the narrowly
-- qualified append-only permissions from migrations 0002, 0014, and 0016.
