-- P7 inert PostgreSQL restore TARGET. `omi_platform_restore` is provisioned by
-- deployment/test infrastructure as a distinct NOLOGIN role. The target never
-- attests source completeness or opens traffic; it only installs a monotone
-- account fence and an immutable per-restore application receipt.

CREATE TABLE omi_memory.account_restored_terminal_fences (
  account_id text NOT NULL,
  deletion_epoch bigint NOT NULL CHECK (deletion_epoch >= 0),
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  terminal_record_digest text NOT NULL CHECK (terminal_record_digest ~ '^[0-9a-f]{64}$'),
  source_restore_id text NOT NULL CHECK (source_restore_id <> ''),
  restored_snapshot_digest text NOT NULL CHECK (restored_snapshot_digest ~ '^[0-9a-f]{64}$'),
  installed_at timestamptz NOT NULL,
  PRIMARY KEY (account_id, deletion_epoch),
  UNIQUE (account_id, control_revision, deletion_epoch)
);

CREATE TABLE omi_memory.account_restore_terminal_application_receipts (
  account_id text NOT NULL,
  restore_id text NOT NULL CHECK (restore_id <> ''),
  restore_scope text NOT NULL CHECK (restore_scope = 'postgresql'),
  restored_snapshot_digest text NOT NULL CHECK (restored_snapshot_digest ~ '^[0-9a-f]{64}$'),
  restore_completed_at_epoch_seconds bigint NOT NULL CHECK (restore_completed_at_epoch_seconds >= 0),
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  deletion_epoch bigint NOT NULL CHECK (deletion_epoch >= 0),
  applied_fence_deletion_epoch bigint NOT NULL CHECK (applied_fence_deletion_epoch >= 0),
  terminal_record_digest text NOT NULL CHECK (terminal_record_digest ~ '^[0-9a-f]{64}$'),
  result text NOT NULL CHECK (result IN ('applied', 'already_absent')),
  applied_at timestamptz NOT NULL,
  PRIMARY KEY (account_id, restore_id),
  FOREIGN KEY (account_id, applied_fence_deletion_epoch)
    REFERENCES omi_memory.account_restored_terminal_fences (account_id, deletion_epoch)
);

CREATE FUNCTION omi_memory.hold_postgres_restore_target(
  p_restore_id text,
  p_restore_scope text,
  p_restored_snapshot_digest text,
  p_restore_completed_at_epoch_seconds bigint
)
RETURNS TABLE(backend_pid integer, database_now timestamptz)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
BEGIN
  IF p_restore_id IS NULL OR p_restore_id !~ '^[!-~]+$' OR length(p_restore_id) > 256
    OR p_restore_scope IS DISTINCT FROM 'postgresql'
    OR p_restored_snapshot_digest IS NULL
    OR p_restored_snapshot_digest !~ '^[0-9a-f]{64}$'
    OR p_restore_completed_at_epoch_seconds IS NULL
    OR p_restore_completed_at_epoch_seconds < 0
    OR p_restore_completed_at_epoch_seconds > 9007199254740991 THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'restore_target_coordinate_invalid';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_restore_id, 731026));
  PERFORM set_config('omi.restore_id', p_restore_id, true);
  PERFORM set_config('omi.restore_scope', p_restore_scope, true);
  PERFORM set_config('omi.restored_snapshot_digest', p_restored_snapshot_digest, true);
  PERFORM set_config(
    'omi.restore_completed_at_epoch_seconds', p_restore_completed_at_epoch_seconds::text, true
  );
  RETURN QUERY SELECT pg_backend_pid(), transaction_timestamp();
END
$function$;

CREATE FUNCTION omi_memory.apply_postgres_restore_terminal_fence(
  p_account_id text,
  p_control_revision bigint,
  p_deletion_epoch bigint,
  p_terminal_record_digest text
)
RETURNS TABLE(result text, applied_at_epoch_micros text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_restore_id text := nullif(current_setting('omi.restore_id', true), '');
  v_restore_scope text := nullif(current_setting('omi.restore_scope', true), '');
  v_snapshot_digest text := nullif(current_setting('omi.restored_snapshot_digest', true), '');
  v_restore_completed_at bigint := nullif(
    current_setting('omi.restore_completed_at_epoch_seconds', true), ''
  )::bigint;
  v_applied_at timestamptz := clock_timestamp();
  v_result text;
  v_existing omi_memory.account_restore_terminal_application_receipts%ROWTYPE;
  v_latest omi_memory.account_restored_terminal_fences%ROWTYPE;
  v_current_lifecycle text;
  v_current_deletion_epoch bigint;
  v_had_dominating_fence boolean := false;
  v_applied_fence_deletion_epoch bigint;
BEGIN
  IF v_restore_id IS NULL OR v_restore_scope <> 'postgresql'
    OR v_snapshot_digest !~ '^[0-9a-f]{64}$'
    OR v_restore_completed_at IS NULL OR v_restore_completed_at < 0
    OR p_account_id IS NULL OR p_account_id !~ '^[!-~]+$' OR length(p_account_id) > 128
    OR p_control_revision IS NULL OR p_control_revision < 0
    OR p_control_revision > 9007199254740991
    OR p_deletion_epoch IS NULL OR p_deletion_epoch < 0
    OR p_deletion_epoch > 9007199254740991
    OR p_terminal_record_digest IS NULL
    OR p_terminal_record_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'restore_target_session_denied';
  END IF;

  -- Reacquire the restore-wide lock here so even a direct call cannot bypass
  -- serialization by fabricating custom transaction-local settings.
  PERFORM pg_advisory_xact_lock(hashtextextended(v_restore_id, 731026));
  PERFORM pg_advisory_xact_lock(hashtextextended(p_account_id, 731027));
  SELECT * INTO v_existing
  FROM omi_memory.account_restore_terminal_application_receipts r
  WHERE r.account_id = p_account_id AND r.restore_id = v_restore_id;
  IF FOUND THEN
    IF v_existing.restore_scope <> v_restore_scope
      OR v_existing.restored_snapshot_digest <> v_snapshot_digest
      OR v_existing.restore_completed_at_epoch_seconds <> v_restore_completed_at
      OR v_existing.control_revision <> p_control_revision
      OR v_existing.deletion_epoch <> p_deletion_epoch
      OR v_existing.terminal_record_digest <> p_terminal_record_digest THEN
      RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'restore_target_receipt_conflict';
    END IF;
    RETURN QUERY SELECT v_existing.result,
      (floor(extract(epoch FROM v_existing.applied_at) * 1000000)::bigint)::text;
    RETURN;
  END IF;

  SELECT * INTO v_latest
  FROM omi_memory.account_restored_terminal_fences f
  WHERE f.account_id = p_account_id
  ORDER BY f.deletion_epoch DESC
  LIMIT 1;
  IF FOUND AND v_latest.deletion_epoch = p_deletion_epoch
    AND (v_latest.control_revision <> p_control_revision
      OR v_latest.terminal_record_digest <> p_terminal_record_digest) THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'restore_target_terminal_conflict';
  END IF;

  IF NOT FOUND OR v_latest.deletion_epoch < p_deletion_epoch THEN
    INSERT INTO omi_memory.account_restored_terminal_fences (
      account_id, deletion_epoch, control_revision, terminal_record_digest,
      source_restore_id, restored_snapshot_digest, installed_at
    ) VALUES (
      p_account_id, p_deletion_epoch, p_control_revision, p_terminal_record_digest,
      v_restore_id, v_snapshot_digest, v_applied_at
    );
    v_applied_fence_deletion_epoch := p_deletion_epoch;
  ELSIF v_latest.deletion_epoch > p_deletion_epoch THEN
    -- A higher retained epoch already dominates this terminal record. Preserve
    -- the single monotone fence and bind this restore receipt to that witness.
    v_had_dominating_fence := true;
    v_applied_fence_deletion_epoch := v_latest.deletion_epoch;
  ELSE
    v_applied_fence_deletion_epoch := v_latest.deletion_epoch;
  END IF;

  SELECT cr.lifecycle_state, cr.deletion_epoch
    INTO v_current_lifecycle, v_current_deletion_epoch
  FROM omi_memory.account_control_heads h
  JOIN omi_memory.account_control_revisions cr
    ON cr.account_id = h.account_id AND cr.control_revision = h.control_revision
  WHERE h.account_id = p_account_id AND h.conflict_reason IS NULL
  FOR SHARE OF h, cr;
  v_result := CASE
    WHEN v_had_dominating_fence THEN 'already_absent'
    WHEN NOT FOUND THEN 'already_absent'
    WHEN v_current_lifecycle = 'deleted'
      AND v_current_deletion_epoch IS NOT NULL
      AND v_current_deletion_epoch >= p_deletion_epoch THEN 'already_absent'
    ELSE 'applied'
  END;

  INSERT INTO omi_memory.account_restore_terminal_application_receipts (
    account_id, restore_id, restore_scope, restored_snapshot_digest,
    restore_completed_at_epoch_seconds, control_revision, deletion_epoch,
    applied_fence_deletion_epoch, terminal_record_digest, result, applied_at
  ) VALUES (
    p_account_id, v_restore_id, v_restore_scope, v_snapshot_digest,
    v_restore_completed_at, p_control_revision, p_deletion_epoch,
    v_applied_fence_deletion_epoch, p_terminal_record_digest, v_result, v_applied_at
  );

  RETURN QUERY SELECT v_result,
    (floor(extract(epoch FROM v_applied_at) * 1000000)::bigint)::text;
END
$function$;

REVOKE ALL ON FUNCTION omi_memory.hold_postgres_restore_target(text, text, text, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.apply_postgres_restore_terminal_fence(text, bigint, bigint, text)
  FROM PUBLIC;
REVOKE ALL ON omi_memory.account_restored_terminal_fences FROM PUBLIC;
REVOKE ALL ON omi_memory.account_restore_terminal_application_receipts FROM PUBLIC;

GRANT USAGE ON SCHEMA omi_memory TO omi_platform_restore;
GRANT EXECUTE ON FUNCTION omi_memory.hold_postgres_restore_target(text, text, text, bigint)
  TO omi_platform_restore;
GRANT EXECUTE ON FUNCTION omi_memory.apply_postgres_restore_terminal_fence(text, bigint, bigint, text)
  TO omi_platform_restore;
