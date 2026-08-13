-- P3 bounded Listen-to-formation delivery. The source outbox stays immutable;
-- append-only delivery revisions and a fenced head make retries observable.

CREATE TABLE omi_memory.listen_formation_delivery_revisions (
  account_id text NOT NULL,
  outbox_id text NOT NULL,
  state_revision bigint NOT NULL CHECK (state_revision > 0),
  state_digest text NOT NULL CHECK (state_digest ~ '^[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN (
    'leased', 'retryable_failed', 'dead_letter', 'accepted'
  )),
  attempt integer NOT NULL CHECK (attempt > 0),
  lease_fence bigint NOT NULL CHECK (lease_fence = attempt),
  worker_id text NOT NULL CHECK (length(worker_id) BETWEEN 1 AND 256),
  leased_at timestamptz,
  lease_expires_at timestamptz,
  failure_code text CHECK (failure_code IS NULL OR failure_code IN (
    'dependency_unavailable', 'serialization_retryable', 'payload_invalid',
    'formation_ineligible', 'acceptance_conflict', 'worker_lost'
  )),
  failed_at timestamptz,
  next_eligible_at timestamptz,
  accepted_work_digest text CHECK (
    accepted_work_digest IS NULL OR accepted_work_digest ~ '^[0-9a-f]{64}$'
  ),
  accepted_at timestamptz,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, outbox_id, state_revision),
  UNIQUE (account_id, outbox_id, state_revision, state_digest),
  FOREIGN KEY (account_id, outbox_id)
    REFERENCES omi_memory.listen_formation_outbox (account_id, outbox_id),
  CHECK (
    (state = 'leased'
      AND leased_at IS NOT NULL AND lease_expires_at > leased_at
      AND failure_code IS NULL AND failed_at IS NULL AND next_eligible_at IS NULL
      AND accepted_work_digest IS NULL AND accepted_at IS NULL)
    OR (state = 'retryable_failed'
      AND leased_at IS NULL AND lease_expires_at IS NULL
      AND failure_code IS NOT NULL AND failed_at IS NOT NULL
      AND next_eligible_at > failed_at
      AND accepted_work_digest IS NULL AND accepted_at IS NULL)
    OR (state = 'dead_letter'
      AND leased_at IS NULL AND lease_expires_at IS NULL
      AND failure_code IS NOT NULL AND failed_at IS NOT NULL
      AND next_eligible_at IS NULL
      AND accepted_work_digest IS NULL AND accepted_at IS NULL)
    OR (state = 'accepted'
      AND leased_at IS NULL AND lease_expires_at IS NULL
      AND failure_code IS NULL AND failed_at IS NULL AND next_eligible_at IS NULL
      AND accepted_work_digest IS NOT NULL AND accepted_at IS NOT NULL)
  )
);

CREATE TABLE omi_memory.listen_formation_delivery_heads (
  account_id text NOT NULL,
  outbox_id text NOT NULL,
  state_revision bigint NOT NULL CHECK (state_revision > 0),
  state_digest text NOT NULL CHECK (state_digest ~ '^[0-9a-f]{64}$'),
  updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, outbox_id),
  FOREIGN KEY (account_id, outbox_id, state_revision, state_digest)
    REFERENCES omi_memory.listen_formation_delivery_revisions
      (account_id, outbox_id, state_revision, state_digest)
);

REVOKE ALL ON omi_memory.listen_formation_delivery_revisions FROM PUBLIC;
REVOKE ALL ON omi_memory.listen_formation_delivery_heads FROM PUBLIC;

CREATE FUNCTION omi_memory.select_next_listen_formation_delivery()
RETURNS TABLE(
  outbox_id text, finalization_id text, formation_work_id text,
  finalization_digest text, payload_digest text,
  previous_state_revision bigint, previous_state_digest text,
  previous_state text, previous_attempt integer,
  previous_lease_expires_at timestamptz, db_now timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
BEGIN
  IF v_account_id IS NULL
    OR nullif(current_setting('omi.principal_id', true), '') IS NULL
    OR nullif(current_setting('omi.capability', true), '')
      IS DISTINCT FROM 'memories.work.accept' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_delivery_authority_denied';
  END IF;
  RETURN QUERY
  SELECT o.outbox_id, o.finalization_id, o.formation_work_id,
         o.finalization_digest, o.payload_digest,
         h.state_revision, h.state_digest, r.state, r.attempt,
         r.lease_expires_at, transaction_timestamp()
  FROM omi_memory.listen_formation_outbox o
  LEFT JOIN omi_memory.listen_formation_delivery_heads h
    ON h.account_id = o.account_id AND h.outbox_id = o.outbox_id
  LEFT JOIN omi_memory.listen_formation_delivery_revisions r
    ON r.account_id = h.account_id AND r.outbox_id = h.outbox_id
   AND r.state_revision = h.state_revision AND r.state_digest = h.state_digest
  WHERE o.account_id = v_account_id AND o.state = 'pending'
    AND (
      h.outbox_id IS NULL
      OR (r.state = 'retryable_failed'
        AND r.next_eligible_at <= transaction_timestamp())
      OR (r.state = 'leased'
        AND r.lease_expires_at <= transaction_timestamp())
    )
  ORDER BY o.created_at, o.outbox_id
  FOR UPDATE OF o SKIP LOCKED
  LIMIT 1;
END
$function$;

CREATE FUNCTION omi_memory.claim_listen_formation_delivery(
  p_outbox_id text,
  p_finalization_id text,
  p_formation_work_id text,
  p_finalization_digest text,
  p_payload_digest text,
  p_previous_state_revision bigint,
  p_previous_state_digest text,
  p_state_revision bigint,
  p_state_digest text,
  p_attempt integer,
  p_lease_expires_at timestamptz,
  p_content_hash text
)
RETURNS TABLE(
  result text, worker_id text, leased_at timestamptz,
  lease_expires_at timestamptz, lease_fence bigint
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
  v_worker_id text := nullif(current_setting('omi.principal_id', true), '');
  v_now timestamptz := transaction_timestamp();
  v_head omi_memory.listen_formation_delivery_heads%ROWTYPE;
BEGIN
  IF v_account_id IS NULL OR v_worker_id IS NULL
    OR nullif(current_setting('omi.capability', true), '')
      IS DISTINCT FROM 'memories.work.accept' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_delivery_authority_denied';
  END IF;
  PERFORM 1 FROM omi_memory.listen_formation_outbox o
  WHERE o.account_id = v_account_id AND o.outbox_id = p_outbox_id
    AND o.finalization_id = p_finalization_id
    AND o.formation_work_id = p_formation_work_id
    AND o.finalization_digest = p_finalization_digest
    AND o.payload_digest = p_payload_digest AND o.state = 'pending'
  FOR UPDATE;
  IF NOT FOUND OR p_state_revision <= 0 OR p_attempt <= 0
    OR p_lease_expires_at <= v_now THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_delivery_ineligible';
  END IF;
  SELECT * INTO v_head FROM omi_memory.listen_formation_delivery_heads h
  WHERE h.account_id = v_account_id AND h.outbox_id = p_outbox_id
  FOR UPDATE;
  IF p_previous_state_revision IS NULL THEN
    IF FOUND OR p_previous_state_digest IS NOT NULL
      OR p_state_revision <> 1 OR p_attempt <> 1 THEN
      RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_delivery_stale';
    END IF;
  ELSE
    IF NOT FOUND OR v_head.state_revision <> p_previous_state_revision
      OR v_head.state_digest <> p_previous_state_digest
      OR p_state_revision <> p_previous_state_revision + 1 THEN
      RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_delivery_stale';
    END IF;
    PERFORM 1 FROM omi_memory.listen_formation_delivery_revisions r
    WHERE r.account_id = v_account_id AND r.outbox_id = p_outbox_id
      AND r.state_revision = p_previous_state_revision
      AND r.state_digest = p_previous_state_digest
      AND r.attempt + 1 = p_attempt
      AND (
        (r.state = 'retryable_failed' AND r.next_eligible_at <= v_now)
        OR (r.state = 'leased' AND r.lease_expires_at <= v_now)
      );
    IF NOT FOUND THEN
      RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_delivery_stale';
    END IF;
  END IF;
  INSERT INTO omi_memory.listen_formation_delivery_revisions
    (account_id, outbox_id, state_revision, state_digest, state, attempt,
     lease_fence, worker_id, leased_at, lease_expires_at, content_hash)
  VALUES (v_account_id, p_outbox_id, p_state_revision, p_state_digest, 'leased',
          p_attempt, p_attempt, v_worker_id, v_now, p_lease_expires_at, p_content_hash);
  IF p_previous_state_revision IS NULL THEN
    INSERT INTO omi_memory.listen_formation_delivery_heads
      (account_id, outbox_id, state_revision, state_digest)
    VALUES (v_account_id, p_outbox_id, p_state_revision, p_state_digest);
  ELSE
    UPDATE omi_memory.listen_formation_delivery_heads
    SET state_revision = p_state_revision, state_digest = p_state_digest,
        updated_at = v_now
    WHERE account_id = v_account_id AND outbox_id = p_outbox_id
      AND state_revision = p_previous_state_revision
      AND state_digest = p_previous_state_digest;
    IF NOT FOUND THEN
      RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_delivery_stale';
    END IF;
  END IF;
  RETURN QUERY SELECT 'claimed'::text, v_worker_id, v_now,
    p_lease_expires_at, p_attempt::bigint;
END
$function$;

CREATE FUNCTION omi_memory.read_listen_formation_delivery_payload(
  p_outbox_id text,
  p_lease_fence bigint
)
RETURNS TABLE(
  outbox_id text, finalization_id text, formation_work_id text,
  outbox_finalization_digest text, payload_digest text,
  outbox_created_at timestamptz, outbox_content_hash text,
  session_id text, conversation_id text, client_conversation_id text,
  terminal_status text, capture_completeness text,
  started_at timestamptz, ended_at timestamptz, source text,
  codec text, sample_rate integer, channels integer,
  session_content_hash text, segment_count bigint,
  transcript_digest text, finalization_digest text, finalization_content_hash text,
  segment_ordinal bigint, segment_id text, text_content text, is_user boolean,
  start_seconds double precision, end_seconds double precision,
  appended_at timestamptz, segment_content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
  v_worker_id text := nullif(current_setting('omi.principal_id', true), '');
BEGIN
  IF v_account_id IS NULL OR v_worker_id IS NULL
    OR nullif(current_setting('omi.capability', true), '')
      IS DISTINCT FROM 'memories.work.accept' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_delivery_authority_denied';
  END IF;
  PERFORM 1
  FROM omi_memory.listen_formation_delivery_heads h
  JOIN omi_memory.listen_formation_delivery_revisions r
    ON r.account_id = h.account_id AND r.outbox_id = h.outbox_id
   AND r.state_revision = h.state_revision AND r.state_digest = h.state_digest
  WHERE h.account_id = v_account_id AND h.outbox_id = p_outbox_id
    AND r.state = 'leased' AND r.lease_fence = p_lease_fence
    AND r.worker_id = v_worker_id AND r.lease_expires_at > transaction_timestamp()
  FOR SHARE OF h, r;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_delivery_stale';
  END IF;
  RETURN QUERY
  SELECT o.outbox_id, o.finalization_id, o.formation_work_id,
         o.finalization_digest, o.payload_digest, o.created_at, o.content_hash,
         f.session_id, f.conversation_id, s.client_conversation_id,
         f.terminal_status, f.capture_completeness,
         f.started_at, f.ended_at, f.source,
         s.codec, s.sample_rate, s.channels, s.content_hash,
         f.segment_count, f.transcript_digest, f.finalization_digest, f.content_hash,
         seg.ordinal AS segment_ordinal, seg.segment_id, seg.text_content, seg.is_user,
         seg.start_seconds, seg.end_seconds, seg.appended_at, seg.content_hash
  FROM omi_memory.listen_formation_outbox o
  JOIN omi_memory.listen_formation_finalizations f
    ON f.account_id = o.account_id AND f.finalization_id = o.finalization_id
  JOIN omi_memory.listen_capture_sessions s
    ON s.account_id = f.account_id AND s.session_id = f.session_id
  JOIN omi_memory.listen_capture_segments seg
    ON seg.account_id = f.account_id AND seg.session_id = f.session_id
  WHERE o.account_id = v_account_id AND o.outbox_id = p_outbox_id
  ORDER BY seg.ordinal;
END
$function$;

CREATE FUNCTION omi_memory.read_listen_formation_delivery_head(
  p_outbox_id text
)
RETURNS TABLE(
  finalization_id text, formation_work_id text,
  finalization_digest text, payload_digest text,
  state_revision bigint, state_digest text, state text, attempt integer,
  lease_fence bigint, worker_id text, lease_expires_at timestamptz,
  failure_code text, failed_at timestamptz, next_eligible_at timestamptz,
  accepted_work_digest text, accepted_at timestamptz, db_now timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
BEGIN
  IF v_account_id IS NULL
    OR nullif(current_setting('omi.principal_id', true), '') IS NULL
    OR nullif(current_setting('omi.capability', true), '')
      IS DISTINCT FROM 'memories.work.accept' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_delivery_authority_denied';
  END IF;
  RETURN QUERY
  SELECT o.finalization_id, o.formation_work_id,
         o.finalization_digest, o.payload_digest,
         r.state_revision, r.state_digest, r.state, r.attempt, r.lease_fence,
         r.worker_id, r.lease_expires_at, r.failure_code, r.failed_at,
         r.next_eligible_at, r.accepted_work_digest, r.accepted_at,
         transaction_timestamp()
  FROM omi_memory.listen_formation_delivery_heads h
  JOIN omi_memory.listen_formation_outbox o
    ON o.account_id = h.account_id AND o.outbox_id = h.outbox_id
  JOIN omi_memory.listen_formation_delivery_revisions r
    ON r.account_id = h.account_id AND r.outbox_id = h.outbox_id
   AND r.state_revision = h.state_revision AND r.state_digest = h.state_digest
  WHERE h.account_id = v_account_id AND h.outbox_id = p_outbox_id
  FOR UPDATE OF h;
END
$function$;

CREATE FUNCTION omi_memory.append_listen_formation_delivery_outcome(
  p_outbox_id text,
  p_expected_state_revision bigint,
  p_expected_state_digest text,
  p_lease_fence bigint,
  p_state text,
  p_failure_code text,
  p_next_eligible_at timestamptz,
  p_accepted_work_digest text,
  p_state_digest text,
  p_content_hash text
)
RETURNS TABLE(result text, state_revision bigint, state_digest text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.account_id', true), '');
  v_worker_id text := nullif(current_setting('omi.principal_id', true), '');
  v_now timestamptz := transaction_timestamp();
  v_next_revision bigint := p_expected_state_revision + 1;
BEGIN
  IF v_account_id IS NULL OR v_worker_id IS NULL
    OR nullif(current_setting('omi.capability', true), '')
      IS DISTINCT FROM 'memories.work.accept' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'listen_delivery_authority_denied';
  END IF;
  PERFORM 1
  FROM omi_memory.listen_formation_delivery_heads h
  JOIN omi_memory.listen_formation_delivery_revisions r
    ON r.account_id = h.account_id AND r.outbox_id = h.outbox_id
   AND r.state_revision = h.state_revision AND r.state_digest = h.state_digest
  WHERE h.account_id = v_account_id AND h.outbox_id = p_outbox_id
    AND h.state_revision = p_expected_state_revision
    AND h.state_digest = p_expected_state_digest
    AND r.state = 'leased' AND r.lease_fence = p_lease_fence
    AND r.worker_id = v_worker_id AND r.lease_expires_at > v_now
  FOR UPDATE OF h, r;
  IF NOT FOUND OR p_state NOT IN ('retryable_failed', 'dead_letter', 'accepted') THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_delivery_stale';
  END IF;
  IF p_state = 'accepted' AND NOT EXISTS (
    SELECT 1 FROM omi_memory.memory_work_acceptances a
    JOIN omi_memory.listen_formation_outbox o
      ON o.account_id = a.account_id AND o.formation_work_id = a.job_id
    WHERE o.account_id = v_account_id AND o.outbox_id = p_outbox_id
      AND a.accepted_work_digest = p_accepted_work_digest
      AND a.work_kind = 'formation'
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'listen_delivery_acceptance_conflict';
  END IF;
  INSERT INTO omi_memory.listen_formation_delivery_revisions
    (account_id, outbox_id, state_revision, state_digest, state, attempt,
     lease_fence, worker_id, failure_code, failed_at, next_eligible_at,
     accepted_work_digest, accepted_at, content_hash)
  VALUES (v_account_id, p_outbox_id, v_next_revision, p_state_digest, p_state,
          p_lease_fence::integer, p_lease_fence, v_worker_id,
          CASE WHEN p_state = 'accepted' THEN NULL ELSE p_failure_code END,
          CASE WHEN p_state = 'accepted' THEN NULL ELSE v_now END,
          CASE WHEN p_state = 'retryable_failed' THEN p_next_eligible_at ELSE NULL END,
          CASE WHEN p_state = 'accepted' THEN p_accepted_work_digest ELSE NULL END,
          CASE WHEN p_state = 'accepted' THEN v_now ELSE NULL END,
          p_content_hash);
  UPDATE omi_memory.listen_formation_delivery_heads AS h
  SET state_revision = v_next_revision, state_digest = p_state_digest,
      updated_at = v_now
  WHERE h.account_id = v_account_id AND h.outbox_id = p_outbox_id
    AND h.state_revision = p_expected_state_revision
    AND h.state_digest = p_expected_state_digest;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'listen_delivery_stale';
  END IF;
  RETURN QUERY SELECT 'recorded'::text, v_next_revision, p_state_digest;
END
$function$;

REVOKE ALL ON FUNCTION omi_memory.select_next_listen_formation_delivery() FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.claim_listen_formation_delivery(
  text, text, text, text, text, bigint, text, bigint, text, integer, timestamptz, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_listen_formation_delivery_payload(text, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_listen_formation_delivery_head(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.append_listen_formation_delivery_outcome(
  text, bigint, text, bigint, text, text, timestamptz, text, text, text
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.select_next_listen_formation_delivery()
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.claim_listen_formation_delivery(
  text, text, text, text, text, bigint, text, bigint, text, integer, timestamptz, text
) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_formation_delivery_payload(text, bigint)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_formation_delivery_head(text)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.append_listen_formation_delivery_outcome(
  text, bigint, text, bigint, text, text, timestamptz, text, text, text
) TO omi_platform_application;

-- Extend the closed account-deletion registry without changing migration 0030.
CREATE OR REPLACE FUNCTION omi_memory.cleanup_surface_tables(p_surface text)
RETURNS TABLE(table_name text)
LANGUAGE sql
IMMUTABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT mapping.table_name
  FROM (VALUES
    ('durable_work', 'memory_work_acceptances'),
    ('durable_work', 'memory_work_execution_policies'),
    ('durable_work', 'memory_work_heads'),
    ('durable_work', 'memory_work_input_manifest'),
    ('durable_work', 'memory_work_outbox_events'),
    ('durable_work', 'memory_work_state_revisions'),
    ('durable_work', 'memory_work_success_results'),
    ('staged_results', 'memory_work_staged_results'),
    ('staged_results', 'memory_formation_work_inputs'),
    ('staged_results', 'memory_predicate_batch_work_inputs'),
    ('staged_results', 'memory_query_evaluation_inputs'),
    ('staged_results', 'memory_candidate_derivation_artifacts'),
    ('staged_results', 'listen_capture_sessions'),
    ('staged_results', 'listen_capture_session_state_revisions'),
    ('staged_results', 'listen_capture_segments'),
    ('staged_results', 'listen_formation_finalizations'),
    ('staged_results', 'listen_conversation_finalization_intents'),
    ('staged_results', 'listen_formation_outbox'),
    ('staged_results', 'listen_formation_delivery_revisions'),
    ('staged_results', 'listen_formation_delivery_heads'),
    ('authoritative_memory', 'memory_claim_evidence_refs'),
    ('authoritative_memory', 'memory_claim_lineages'),
    ('authoritative_memory', 'memory_claim_liveness_fences'),
    ('authoritative_memory', 'memory_claim_predicate_refs'),
    ('authoritative_memory', 'memory_claim_revisions'),
    ('authoritative_memory', 'memory_claim_source_provisionals'),
    ('authoritative_memory', 'memory_claim_supersessions'),
    ('authoritative_memory', 'memory_consumed_markers'),
    ('authoritative_memory', 'memory_coreference_support_evidence_refs'),
    ('authoritative_memory', 'memory_coreference_support_revisions'),
    ('authoritative_memory', 'memory_derivation_attempts'),
    ('authoritative_memory', 'memory_derivation_commits'),
    ('authoritative_memory', 'memory_derivation_inputs'),
    ('authoritative_memory', 'memory_entity_identities'),
    ('authoritative_memory', 'memory_entity_revisions'),
    ('authoritative_memory', 'memory_event_identities'),
    ('authoritative_memory', 'memory_event_revisions'),
    ('authoritative_memory', 'memory_evidence_identities'),
    ('authoritative_memory', 'memory_evidence_revisions'),
    ('authoritative_memory', 'memory_formation_extraction_evidence'),
    ('authoritative_memory', 'memory_formation_extraction_outcomes'),
    ('authoritative_memory', 'memory_formation_outcomes'),
    ('authoritative_memory', 'memory_formation_placement_outcomes'),
    ('authoritative_memory', 'memory_generated_adjacency'),
    ('authoritative_memory', 'memory_graph_heads'),
    ('authoritative_memory', 'memory_idempotency_receipts'),
    ('authoritative_memory', 'memory_identity_authorization_identities'),
    ('authoritative_memory', 'memory_identity_authorization_entity_endpoints'),
    ('authoritative_memory', 'memory_identity_authorization_revisions'),
    ('authoritative_memory', 'memory_identity_authorization_support'),
    ('authoritative_memory', 'memory_identity_constraint_entity_endpoints'),
    ('authoritative_memory', 'memory_identity_revisions'),
    ('authoritative_memory', 'memory_identity_support'),
    ('authoritative_memory', 'memory_mention_revisions'),
    ('authoritative_memory', 'memory_placement_artifacts'),
    ('authoritative_memory', 'memory_predicate_assertion_revisions'),
    ('authoritative_memory', 'memory_predicate_identities'),
    ('authoritative_memory', 'memory_predicate_revisions'),
    ('authoritative_memory', 'memory_revisions'),
    ('authoritative_memory', 'memory_source_local_claim_roles'),
    ('account_access', 'application_credential_heads'),
    ('account_access', 'application_credential_revisions'),
    ('account_access', 'application_grant_heads'),
    ('account_access', 'application_grant_revisions'),
    ('account_access', 'firebase_application_credential_bindings'),
    ('account_access', 'firebase_identity_bindings'),
    ('experiment_results', 'memory_strategy_assignment_bundles'),
    ('experiment_results', 'memory_strategy_assignment_policies'),
    ('experiment_results', 'memory_strategy_baseline_read_groundings'),
    ('experiment_results', 'memory_strategy_candidate_read_groundings'),
    ('experiment_results', 'memory_strategy_definitions'),
    ('experiment_results', 'memory_strategy_evaluation_baselines'),
    ('experiment_results', 'memory_strategy_evaluation_pairs'),
    ('experiment_results', 'memory_strategy_policy_shadows'),
    ('experiment_results', 'memory_strategy_shadow_assignments'),
    ('experiment_results', 'memory_strategy_shadow_results'),
    ('product_projections', 'memory_product_membership_claim_lineages'),
    ('product_projections', 'memory_product_membership_revisions'),
    ('product_projections', 'memory_product_operation_receipts'),
    ('product_projections', 'memory_product_projection_citation_evidence_refs'),
    ('product_projections', 'memory_product_projection_citations'),
    ('product_projections', 'memory_product_projection_payloads'),
    ('product_projections', 'memory_product_projection_revisions'),
    ('product_projections', 'memory_product_propositions'),
    ('product_projections', 'memory_product_redirect_successors'),
    ('product_projections', 'memory_product_redirects'),
    ('rebuildable_groups_indexes', 'memory_product_group_members'),
    ('rebuildable_groups_indexes', 'memory_product_group_projections'),
    ('migration_state', 'memory_legacy_proposition_mappings'),
    ('migration_state', 'memory_migration_item_tombstones')
  ) AS mapping(surface, table_name)
  WHERE mapping.surface = p_surface
  ORDER BY mapping.table_name
$function$;

REVOKE ALL ON FUNCTION omi_memory.cleanup_surface_tables(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.cleanup_surface_tables(text)
  TO omi_platform_cleanup;
