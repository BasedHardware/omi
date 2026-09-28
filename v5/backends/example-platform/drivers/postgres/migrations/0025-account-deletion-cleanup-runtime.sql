-- P7 inert account cleanup participant. `omi_platform_cleanup` is provisioned
-- by deployment/test infrastructure as a distinct NOLOGIN role. It receives
-- named functions only: no table SELECT/DELETE/UPDATE/INSERT authority.

CREATE TABLE omi_memory.account_deletion_surface_receipts (
  account_id text NOT NULL,
  deletion_epoch bigint NOT NULL CHECK (deletion_epoch >= 0),
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  operation_ref text NOT NULL CHECK (operation_ref ~ '^opref1_[0-9a-f]{64}$'),
  eligibility_digest text NOT NULL CHECK (eligibility_digest ~ '^[0-9a-f]{64}$'),
  surface text NOT NULL CHECK (surface IN (
    'durable_work', 'staged_results', 'authoritative_memory', 'account_access',
    'experiment_results', 'product_projections', 'rebuildable_groups_indexes',
    'migration_state'
  )),
  result text NOT NULL CHECK (result IN ('disposed', 'already_absent')),
  affected_count bigint NOT NULL CHECK (affected_count >= 0),
  completed_at timestamptz NOT NULL,
  PRIMARY KEY (account_id, deletion_epoch, operation_ref, surface),
  FOREIGN KEY (account_id, deletion_epoch)
    REFERENCES omi_memory.account_terminal_deletion_exports (account_id, deletion_epoch)
);

CREATE FUNCTION omi_memory.cleanup_surface_tables(p_surface text)
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

CREATE FUNCTION omi_memory.lock_deleted_account_cleanup(
  p_account_id text,
  p_control_revision bigint,
  p_deletion_epoch bigint,
  p_eligibility_digest text
)
RETURNS TABLE(
  terminal_content_hash text,
  export_content_hash text,
  backend_pid integer,
  database_now timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
BEGIN
  IF p_eligibility_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'cleanup_eligibility_invalid';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_account_id, 731025));
  RETURN QUERY
    SELECT cr.content_hash, te.content_hash, pg_backend_pid(), transaction_timestamp()
    FROM omi_memory.platform_accounts a
    JOIN omi_memory.account_control_heads h ON h.account_id = a.account_id
    JOIN omi_memory.account_control_revisions cr
      ON cr.account_id = h.account_id AND cr.control_revision = h.control_revision
    JOIN omi_memory.account_terminal_deletion_exports te
      ON te.account_id = cr.account_id AND te.deletion_epoch = cr.deletion_epoch
    WHERE a.account_id = p_account_id
      AND h.control_revision = p_control_revision
      AND h.conflict_reason IS NULL
      AND cr.lifecycle_state = 'deleted'
      AND cr.deletion_epoch = p_deletion_epoch
      AND te.control_revision = p_control_revision
    FOR SHARE OF a, h, cr, te;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'cleanup_terminal_coordinate_denied';
  END IF;
  PERFORM set_config('omi.cleanup_account_id', p_account_id, true);
  PERFORM set_config('omi.cleanup_control_revision', p_control_revision::text, true);
  PERFORM set_config('omi.cleanup_deletion_epoch', p_deletion_epoch::text, true);
  PERFORM set_config('omi.cleanup_eligibility_digest', p_eligibility_digest, true);
END
$function$;

CREATE FUNCTION omi_memory.scan_deleted_account_surface(p_surface text)
RETURNS TABLE(table_name text, row_count bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.cleanup_account_id', true), '');
  v_table text;
  v_count bigint;
BEGIN
  IF v_account_id IS NULL OR NOT EXISTS (
    SELECT 1 FROM omi_memory.cleanup_surface_tables(p_surface)
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'cleanup_session_denied';
  END IF;
  FOR v_table IN SELECT c.table_name FROM omi_memory.cleanup_surface_tables(p_surface) c LOOP
    EXECUTE format('SELECT count(*) FROM omi_memory.%I WHERE account_id = $1', v_table)
      INTO v_count USING v_account_id;
    table_name := v_table;
    row_count := v_count;
    RETURN NEXT;
  END LOOP;
END
$function$;

CREATE FUNCTION omi_memory.dispose_deleted_account_surfaces(
  p_surfaces_json text,
  p_operation_ref text,
  p_eligibility_digest text
)
RETURNS TABLE(
  surface text,
  result text,
  affected_count bigint,
  completed_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_account_id text := nullif(current_setting('omi.cleanup_account_id', true), '');
  v_control_revision bigint := nullif(current_setting('omi.cleanup_control_revision', true), '')::bigint;
  v_deletion_epoch bigint := nullif(current_setting('omi.cleanup_deletion_epoch', true), '')::bigint;
  v_surface text;
  v_table text;
  v_candidate text;
  v_remaining text[];
  v_count bigint;
  v_total bigint;
  v_completed timestamptz := clock_timestamp();
  v_existing integer;
  v_surfaces text[];
BEGIN
  BEGIN
    SELECT array_agg(item.value ORDER BY item.ordinality) INTO v_surfaces
    FROM jsonb_array_elements_text(p_surfaces_json::jsonb)
      WITH ORDINALITY AS item(value, ordinality);
  EXCEPTION WHEN others THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'cleanup_surface_group_invalid';
  END;
  IF v_account_id IS NULL OR p_operation_ref !~ '^opref1_[0-9a-f]{64}$'
    OR p_eligibility_digest !~ '^[0-9a-f]{64}$'
    OR p_eligibility_digest <> nullif(current_setting('omi.cleanup_eligibility_digest', true), '')
    OR NOT (
      (cardinality(v_surfaces) = 1 AND v_surfaces[1] IN (
        'authoritative_memory', 'account_access', 'experiment_results',
        'product_projections', 'rebuildable_groups_indexes', 'migration_state'
      ))
      OR v_surfaces = ARRAY['durable_work', 'staged_results']::text[]
    ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'cleanup_session_denied';
  END IF;

  SELECT count(*)::integer INTO v_existing
  FROM omi_memory.account_deletion_surface_receipts r
  WHERE r.account_id = v_account_id AND r.deletion_epoch = v_deletion_epoch
    AND r.operation_ref = p_operation_ref AND r.surface = ANY(v_surfaces);
  IF v_existing > 0 THEN
    IF v_existing <> cardinality(v_surfaces) OR EXISTS (
      SELECT 1 FROM omi_memory.account_deletion_surface_receipts r
      WHERE r.account_id = v_account_id AND r.deletion_epoch = v_deletion_epoch
        AND r.operation_ref = p_operation_ref AND r.surface = ANY(v_surfaces)
        AND r.eligibility_digest <> p_eligibility_digest
    ) THEN
      RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'cleanup_receipt_conflict';
    END IF;
    RETURN QUERY SELECT r.surface, r.result, r.affected_count, r.completed_at
      FROM omi_memory.account_deletion_surface_receipts r
      WHERE r.account_id = v_account_id AND r.deletion_epoch = v_deletion_epoch
        AND r.operation_ref = p_operation_ref AND r.surface = ANY(v_surfaces)
      ORDER BY array_position(v_surfaces, r.surface);
    RETURN;
  END IF;

  CREATE TEMP TABLE IF NOT EXISTS pg_temp.cleanup_surface_counts (
    surface text PRIMARY KEY,
    affected_count bigint NOT NULL
  ) ON COMMIT DROP;
  TRUNCATE pg_temp.cleanup_surface_counts;
  FOREACH v_surface IN ARRAY v_surfaces LOOP
    SELECT coalesce(sum(s.row_count), 0) INTO v_total
      FROM omi_memory.scan_deleted_account_surface(v_surface) s;
    INSERT INTO pg_temp.cleanup_surface_counts VALUES (v_surface, v_total);
  END LOOP;

  SELECT array_agg(t.table_name ORDER BY t.table_name) INTO v_remaining
  FROM (
    SELECT DISTINCT c.table_name
    FROM unnest(v_surfaces) requested(surface)
    CROSS JOIN LATERAL omi_memory.cleanup_surface_tables(requested.surface) c
  ) t;
  SET CONSTRAINTS ALL DEFERRED;
  WHILE cardinality(v_remaining) > 0 LOOP
    SELECT candidate INTO v_candidate
    FROM unnest(v_remaining) candidate
    WHERE NOT EXISTS (
      SELECT 1
      FROM pg_constraint fk
      WHERE fk.contype = 'f'
        AND fk.connamespace = 'omi_memory'::regnamespace
        AND fk.confrelid = format('omi_memory.%I', candidate)::regclass
        AND fk.conrelid <> fk.confrelid
        AND NOT fk.condeferrable
        AND fk.conrelid = ANY(ARRAY(
          SELECT format('omi_memory.%I', child)::regclass FROM unnest(v_remaining) child
        ))
    )
    ORDER BY candidate
    LIMIT 1;
    IF v_candidate IS NULL THEN
      RAISE EXCEPTION USING ERRCODE = '2BP01', MESSAGE = 'cleanup_dependency_cycle';
    END IF;
    EXECUTE format('DELETE FROM omi_memory.%I WHERE account_id = $1', v_candidate)
      USING v_account_id;
    v_remaining := array_remove(v_remaining, v_candidate);
  END LOOP;

  INSERT INTO omi_memory.account_deletion_surface_receipts (
    account_id, deletion_epoch, control_revision, operation_ref,
    eligibility_digest, surface, result, affected_count, completed_at
  )
  SELECT v_account_id, v_deletion_epoch, v_control_revision, p_operation_ref,
    p_eligibility_digest, counts.surface,
    CASE WHEN counts.affected_count > 0 THEN 'disposed' ELSE 'already_absent' END,
    counts.affected_count, v_completed
  FROM pg_temp.cleanup_surface_counts counts;

  RETURN QUERY SELECT r.surface, r.result, r.affected_count, r.completed_at
    FROM omi_memory.account_deletion_surface_receipts r
    WHERE r.account_id = v_account_id AND r.deletion_epoch = v_deletion_epoch
      AND r.operation_ref = p_operation_ref AND r.surface = ANY(v_surfaces)
    ORDER BY array_position(v_surfaces, r.surface);
END
$function$;

REVOKE ALL ON FUNCTION omi_memory.cleanup_surface_tables(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.lock_deleted_account_cleanup(text, bigint, bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.scan_deleted_account_surface(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.dispose_deleted_account_surfaces(text, text, text) FROM PUBLIC;
REVOKE ALL ON omi_memory.account_deletion_surface_receipts FROM PUBLIC;

GRANT USAGE ON SCHEMA omi_memory TO omi_platform_cleanup;
GRANT EXECUTE ON FUNCTION omi_memory.lock_deleted_account_cleanup(text, bigint, bigint, text)
  TO omi_platform_cleanup;
GRANT EXECUTE ON FUNCTION omi_memory.scan_deleted_account_surface(text)
  TO omi_platform_cleanup;
GRANT EXECUTE ON FUNCTION omi_memory.dispose_deleted_account_surfaces(text, text, text)
  TO omi_platform_cleanup;
GRANT SELECT ON omi_memory.account_deletion_surface_receipts TO omi_platform_cleanup;
