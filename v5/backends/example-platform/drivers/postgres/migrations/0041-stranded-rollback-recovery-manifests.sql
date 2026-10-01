-- P7 content-free, GCP-operator-owned manifest for the ratified 30-day
-- recovery window after a lossy whole-account rollback. This is evidence over
-- existing destination surfaces, not a second product-data store or grant.

CREATE FUNCTION omi_memory.is_stranded_rollback_recovery_surface(p_surface text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog, omi_memory
RETURN p_surface IN (
  'durable_work',
  'staged_results',
  'authoritative_memory',
  'account_access',
  'experiment_results',
  'product_projections',
  'search_documents',
  'vector_embeddings',
  'rebuildable_groups_indexes',
  'migration_state',
  'external_objects'
);

ALTER TABLE omi_memory.account_terminal_deletion_exports
  ADD CONSTRAINT account_terminal_deletion_exports_stranded_generation_ck
  CHECK (stranded_data_present = (account_generation = 'rolled_back_stranded'));

CREATE TABLE omi_memory.account_stranded_rollback_recovery_manifests (
  account_id text NOT NULL,
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  database_generation_digest text NOT NULL
    CHECK (database_generation_digest ~ '^[0-9a-f]{64}$'),
  cutover_frontier_digest text NOT NULL
    CHECK (cutover_frontier_digest ~ '^[0-9a-f]{64}$'),
  rollback_frontier_digest text NOT NULL
    CHECK (rollback_frontier_digest ~ '^[0-9a-f]{64}$'),
  cutover_at timestamptz NOT NULL,
  rolled_back_at timestamptz NOT NULL,
  recovery_deadline_at timestamptz NOT NULL,
  surface_count bigint NOT NULL CHECK (surface_count = 11),
  total_record_count bigint NOT NULL CHECK (total_record_count BETWEEN 0 AND 11000000000),
  manifest_digest text NOT NULL CHECK (manifest_digest ~ '^[0-9a-f]{64}$'),
  persistence_receipt_digest text NOT NULL
    CHECK (persistence_receipt_digest ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, account_epoch),
  UNIQUE (account_id, manifest_digest),
  FOREIGN KEY (account_id, control_revision, account_epoch)
    REFERENCES omi_memory.account_control_revisions
      (account_id, control_revision, account_epoch),
  CHECK (cutover_at <= rolled_back_at),
  CHECK (recovery_deadline_at = rolled_back_at + interval '30 days')
);

CREATE TABLE omi_memory.account_stranded_rollback_recovery_surface_receipts (
  account_id text NOT NULL,
  account_epoch bigint NOT NULL CHECK (account_epoch >= 0),
  surface text NOT NULL CHECK (omi_memory.is_stranded_rollback_recovery_surface(surface)),
  scanner_contract_version text NOT NULL
    CHECK (scanner_contract_version ~ '^[a-z0-9][a-z0-9._:-]{0,127}$'),
  source_frontier_digest text NOT NULL CHECK (source_frontier_digest ~ '^[0-9a-f]{64}$'),
  source_fence_receipt_digest text NOT NULL
    CHECK (source_fence_receipt_digest ~ '^[0-9a-f]{64}$'),
  record_count bigint NOT NULL CHECK (record_count BETWEEN 0 AND 1000000000),
  record_set_digest text NOT NULL CHECK (record_set_digest ~ '^[0-9a-f]{64}$'),
  receipt_digest text NOT NULL CHECK (receipt_digest ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, account_epoch, surface),
  FOREIGN KEY (account_id, account_epoch)
    REFERENCES omi_memory.account_stranded_rollback_recovery_manifests
      (account_id, account_epoch)
    ON DELETE RESTRICT
);

CREATE FUNCTION omi_memory.lock_stranded_rollback_recovery_control(
  p_account_id text,
  p_control_revision bigint,
  p_account_epoch bigint
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
BEGIN
  PERFORM 1
  FROM omi_memory.account_control_heads h
  JOIN omi_memory.account_control_revisions c
    ON c.account_id = h.account_id
   AND c.control_revision = h.control_revision
  WHERE h.account_id = p_account_id
    AND h.control_revision = p_control_revision
    AND h.activated_epoch IS NULL
    AND h.conflict_reason IS NULL
    AND c.account_epoch = p_account_epoch
    AND c.account_generation = 'rolled_back_stranded'
    AND c.lifecycle_state = 'active'
    AND c.deletion_epoch IS NULL
  FOR SHARE OF h, c;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stranded_rollback_control_denied';
  END IF;
END
$function$;

CREATE FUNCTION omi_memory.record_stranded_rollback_recovery_manifest(
  p_account_id text,
  p_control_revision bigint,
  p_account_epoch bigint,
  p_database_generation_digest text,
  p_cutover_frontier_digest text,
  p_rollback_frontier_digest text,
  p_cutover_at_epoch_seconds bigint,
  p_rolled_back_at_epoch_seconds bigint,
  p_recovery_deadline_epoch_seconds bigint,
  p_manifest_digest text,
  p_persistence_receipt_digest text,
  p_surface_receipts jsonb
)
RETURNS TABLE (
  classification text,
  account_id text,
  control_revision bigint,
  account_epoch bigint,
  database_generation_digest text,
  cutover_frontier_digest text,
  rollback_frontier_digest text,
  cutover_at_epoch_seconds bigint,
  rolled_back_at_epoch_seconds bigint,
  recovery_deadline_epoch_seconds bigint,
  surface_count bigint,
  total_record_count bigint,
  manifest_digest text,
  persistence_receipt_digest text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_item jsonb;
  v_surface text;
  v_count bigint;
  v_total bigint := 0;
  v_inserted bigint;
  v_manifest omi_memory.account_stranded_rollback_recovery_manifests%ROWTYPE;
  v_receipt omi_memory.account_stranded_rollback_recovery_surface_receipts%ROWTYPE;
BEGIN
  IF p_database_generation_digest !~ '^[0-9a-f]{64}$'
    OR p_cutover_frontier_digest !~ '^[0-9a-f]{64}$'
    OR p_rollback_frontier_digest !~ '^[0-9a-f]{64}$'
    OR p_manifest_digest !~ '^[0-9a-f]{64}$'
    OR p_persistence_receipt_digest !~ '^[0-9a-f]{64}$'
    OR p_cutover_at_epoch_seconds < 0
    OR p_rolled_back_at_epoch_seconds < p_cutover_at_epoch_seconds
    OR p_recovery_deadline_epoch_seconds <> p_rolled_back_at_epoch_seconds + 2592000
    OR jsonb_typeof(p_surface_receipts) <> 'array'
    OR jsonb_array_length(p_surface_receipts) <> 11 THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'stranded_rollback_manifest_input_invalid';
  END IF;

  PERFORM omi_memory.lock_stranded_rollback_recovery_control(
    p_account_id, p_control_revision, p_account_epoch
  );

  FOR v_item IN SELECT value FROM jsonb_array_elements(p_surface_receipts)
  LOOP
    IF jsonb_typeof(v_item) <> 'object'
      OR (SELECT count(*) FROM jsonb_object_keys(v_item)) <> 7
      OR NOT (v_item ?& ARRAY[
        'surface', 'scanner_contract_version', 'source_frontier_digest',
        'source_fence_receipt_digest', 'record_count', 'record_set_digest', 'receipt_digest'
      ])
      OR NOT omi_memory.is_stranded_rollback_recovery_surface(v_item->>'surface')
      OR (v_item->>'scanner_contract_version') !~ '^[a-z0-9][a-z0-9._:-]{0,127}$'
      OR (v_item->>'source_frontier_digest') !~ '^[0-9a-f]{64}$'
      OR (v_item->>'source_fence_receipt_digest') !~ '^[0-9a-f]{64}$'
      OR (v_item->>'record_count') !~ '^(0|[1-9][0-9]{0,9})$'
      OR (v_item->>'record_set_digest') !~ '^[0-9a-f]{64}$'
      OR (v_item->>'receipt_digest') !~ '^[0-9a-f]{64}$' THEN
      RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'stranded_rollback_surface_receipt_invalid';
    END IF;
    v_count := (v_item->>'record_count')::bigint;
    IF v_count > 1000000000 THEN
      RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'stranded_rollback_surface_receipt_invalid';
    END IF;
    v_total := v_total + v_count;
  END LOOP;

  INSERT INTO omi_memory.account_stranded_rollback_recovery_manifests (
    account_id, account_epoch, control_revision, database_generation_digest,
    cutover_frontier_digest, rollback_frontier_digest, cutover_at, rolled_back_at,
    recovery_deadline_at, surface_count, total_record_count, manifest_digest,
    persistence_receipt_digest
  ) VALUES (
    p_account_id, p_account_epoch, p_control_revision, p_database_generation_digest,
    p_cutover_frontier_digest, p_rollback_frontier_digest,
    to_timestamp(p_cutover_at_epoch_seconds), to_timestamp(p_rolled_back_at_epoch_seconds),
    to_timestamp(p_recovery_deadline_epoch_seconds), 11, v_total, p_manifest_digest,
    p_persistence_receipt_digest
  ) ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS v_inserted = ROW_COUNT;

  SELECT * INTO STRICT v_manifest
  FROM omi_memory.account_stranded_rollback_recovery_manifests m
  WHERE m.account_id = p_account_id AND m.account_epoch = p_account_epoch
  FOR SHARE;
  IF v_manifest.control_revision <> p_control_revision
    OR v_manifest.database_generation_digest <> p_database_generation_digest
    OR v_manifest.cutover_frontier_digest <> p_cutover_frontier_digest
    OR v_manifest.rollback_frontier_digest <> p_rollback_frontier_digest
    OR extract(epoch FROM v_manifest.cutover_at)::bigint <> p_cutover_at_epoch_seconds
    OR extract(epoch FROM v_manifest.rolled_back_at)::bigint <> p_rolled_back_at_epoch_seconds
    OR extract(epoch FROM v_manifest.recovery_deadline_at)::bigint <> p_recovery_deadline_epoch_seconds
    OR v_manifest.total_record_count <> v_total
    OR v_manifest.manifest_digest <> p_manifest_digest
    OR v_manifest.persistence_receipt_digest <> p_persistence_receipt_digest THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'stranded_rollback_manifest_conflict';
  END IF;

  FOR v_item IN SELECT value FROM jsonb_array_elements(p_surface_receipts)
  LOOP
    v_surface := v_item->>'surface';
    INSERT INTO omi_memory.account_stranded_rollback_recovery_surface_receipts (
      account_id, account_epoch, surface, scanner_contract_version,
      source_frontier_digest, source_fence_receipt_digest, record_count,
      record_set_digest, receipt_digest
    ) VALUES (
      p_account_id, p_account_epoch, v_surface, v_item->>'scanner_contract_version',
      v_item->>'source_frontier_digest', v_item->>'source_fence_receipt_digest',
      (v_item->>'record_count')::bigint, v_item->>'record_set_digest',
      v_item->>'receipt_digest'
    ) ON CONFLICT DO NOTHING;
    SELECT * INTO STRICT v_receipt
    FROM omi_memory.account_stranded_rollback_recovery_surface_receipts r
    WHERE r.account_id = p_account_id
      AND r.account_epoch = p_account_epoch
      AND r.surface = v_surface;
    IF v_receipt.scanner_contract_version <> v_item->>'scanner_contract_version'
      OR v_receipt.source_frontier_digest <> v_item->>'source_frontier_digest'
      OR v_receipt.source_fence_receipt_digest <> v_item->>'source_fence_receipt_digest'
      OR v_receipt.record_count <> (v_item->>'record_count')::bigint
      OR v_receipt.record_set_digest <> v_item->>'record_set_digest'
      OR v_receipt.receipt_digest <> v_item->>'receipt_digest' THEN
      RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'stranded_rollback_manifest_conflict';
    END IF;
  END LOOP;

  IF (SELECT count(*) FROM omi_memory.account_stranded_rollback_recovery_surface_receipts r
      WHERE r.account_id = p_account_id AND r.account_epoch = p_account_epoch) <> 11 THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'stranded_rollback_manifest_conflict';
  END IF;

  RETURN QUERY SELECT
    CASE WHEN v_inserted = 1 THEN 'stored' ELSE 'replayed' END,
    v_manifest.account_id, v_manifest.control_revision, v_manifest.account_epoch,
    v_manifest.database_generation_digest, v_manifest.cutover_frontier_digest,
    v_manifest.rollback_frontier_digest,
    extract(epoch FROM v_manifest.cutover_at)::bigint,
    extract(epoch FROM v_manifest.rolled_back_at)::bigint,
    extract(epoch FROM v_manifest.recovery_deadline_at)::bigint,
    v_manifest.surface_count, v_manifest.total_record_count,
    v_manifest.manifest_digest, v_manifest.persistence_receipt_digest;
END
$function$;

CREATE FUNCTION omi_memory.load_stranded_rollback_recovery_manifest(
  p_account_id text,
  p_control_revision bigint,
  p_account_epoch bigint,
  p_database_generation_digest text,
  p_manifest_digest text
)
RETURNS TABLE (
  account_id text,
  control_revision bigint,
  account_epoch bigint,
  database_generation_digest text,
  cutover_frontier_digest text,
  rollback_frontier_digest text,
  cutover_at_epoch_seconds bigint,
  rolled_back_at_epoch_seconds bigint,
  recovery_deadline_epoch_seconds bigint,
  surface_count bigint,
  total_record_count bigint,
  manifest_digest text,
  persistence_receipt_digest text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_manifest omi_memory.account_stranded_rollback_recovery_manifests%ROWTYPE;
BEGIN
  PERFORM omi_memory.lock_stranded_rollback_recovery_control(
    p_account_id, p_control_revision, p_account_epoch
  );
  SELECT * INTO v_manifest
  FROM omi_memory.account_stranded_rollback_recovery_manifests m
  WHERE m.account_id = p_account_id AND m.account_epoch = p_account_epoch
  FOR SHARE;
  IF NOT FOUND THEN RETURN; END IF;
  IF v_manifest.control_revision <> p_control_revision
    OR v_manifest.database_generation_digest <> p_database_generation_digest
    OR v_manifest.manifest_digest <> p_manifest_digest THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'stranded_rollback_manifest_conflict';
  END IF;
  RETURN QUERY SELECT
    v_manifest.account_id, v_manifest.control_revision, v_manifest.account_epoch,
    v_manifest.database_generation_digest, v_manifest.cutover_frontier_digest,
    v_manifest.rollback_frontier_digest,
    extract(epoch FROM v_manifest.cutover_at)::bigint,
    extract(epoch FROM v_manifest.rolled_back_at)::bigint,
    extract(epoch FROM v_manifest.recovery_deadline_at)::bigint,
    v_manifest.surface_count, v_manifest.total_record_count,
    v_manifest.manifest_digest, v_manifest.persistence_receipt_digest;
END
$function$;

REVOKE ALL ON TABLE omi_memory.account_stranded_rollback_recovery_manifests FROM PUBLIC;
REVOKE ALL ON TABLE omi_memory.account_stranded_rollback_recovery_manifests FROM omi_platform_application;
REVOKE ALL ON TABLE omi_memory.account_stranded_rollback_recovery_surface_receipts FROM PUBLIC;
REVOKE ALL ON TABLE omi_memory.account_stranded_rollback_recovery_surface_receipts FROM omi_platform_application;
REVOKE ALL ON FUNCTION omi_memory.is_stranded_rollback_recovery_surface(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.lock_stranded_rollback_recovery_control(text,bigint,bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.record_stranded_rollback_recovery_manifest(
  text,bigint,bigint,text,text,text,bigint,bigint,bigint,text,text,jsonb
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.load_stranded_rollback_recovery_manifest(
  text,bigint,bigint,text,text
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.record_stranded_rollback_recovery_manifest(
  text,bigint,bigint,text,text,text,bigint,bigint,bigint,text,text,jsonb
) TO omi_platform_restore;
GRANT EXECUTE ON FUNCTION omi_memory.load_stranded_rollback_recovery_manifest(
  text,bigint,bigint,text,text
) TO omi_platform_restore;
