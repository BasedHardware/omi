-- P7 restored-tombstone application gate.
--
-- A retained terminal fence is a monotone per-account denial coordinate. The
-- pre-authorization lookup filters it, while the transaction-time function
-- takes the same account advisory lock as restore application before checking
-- again. This closes the auth-to-operation race without making a replay
-- checkpoint, restore receipt, or tombstone into positive authority.

CREATE FUNCTION omi_memory.lookup_unfenced_firebase_application_authorization(
  requested_firebase_project_id text,
  requested_firebase_uid text,
  requested_application_id text,
  requested_capability text
)
RETURNS TABLE (
  firebase_project_id text,
  firebase_uid text,
  principal_id text,
  account_id text,
  application_id text,
  credential_id text,
  credential_generation bigint,
  credential_lifecycle text,
  authentication_strength text,
  credential_expires_at_epoch_seconds bigint,
  capability text,
  grant_id text,
  grant_version bigint,
  grant_lifecycle text,
  grant_enabled boolean,
  control_revision bigint,
  account_epoch bigint,
  destination_activation_revision bigint,
  destination_activation_epoch bigint,
  control_conflict_reason text,
  control_conflict_at_revision bigint,
  lifecycle_state text,
  deletion_epoch bigint,
  account_generation text,
  control_content_hash text,
  credential_content_hash text,
  grant_content_hash text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT base.*
  FROM omi_memory.lookup_firebase_application_authorization(
    requested_firebase_project_id,
    requested_firebase_uid,
    requested_application_id,
    requested_capability
  ) AS base
  WHERE NOT EXISTS (
    SELECT 1
    FROM omi_memory.account_restored_terminal_fences AS restored_fence
    WHERE restored_fence.account_id = base.account_id
  )
$function$;

CREATE FUNCTION omi_memory.lock_unfenced_authority_state(
  requested_account_id text,
  requested_principal_id text,
  requested_application_id text,
  requested_credential_id text,
  requested_credential_generation bigint,
  requested_capability text,
  requested_grant_id text
)
RETURNS TABLE (
  account_id text,
  principal_id text,
  application_id text,
  credential_id text,
  credential_generation bigint,
  capability text,
  grant_id text,
  grant_version bigint,
  account_epoch bigint,
  control_conflict_reason text,
  control_conflict_at_revision bigint,
  destination_activation_epoch bigint,
  destination_activation_revision bigint,
  lifecycle_state text,
  deletion_epoch bigint,
  account_generation text,
  credential_lifecycle text,
  grant_lifecycle text,
  grant_enabled boolean,
  authentication_strength text,
  credential_expires_at_epoch_seconds bigint,
  control_revision bigint,
  control_content_hash text,
  credential_content_hash text,
  grant_content_hash text,
  db_now_epoch_seconds bigint
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
BEGIN
  IF requested_account_id IS NULL
    OR requested_account_id !~ '^[!-~]+$'
    OR length(requested_account_id) > 128 THEN
    RETURN;
  END IF;

  -- Must match apply_postgres_restore_terminal_fence. Whichever transaction
  -- obtains this lock first establishes the serial order for application work
  -- versus a newly replayed deletion.
  PERFORM pg_advisory_xact_lock(hashtextextended(requested_account_id, 731027));

  IF EXISTS (
    SELECT 1
    FROM omi_memory.account_restored_terminal_fences AS restored_fence
    WHERE restored_fence.account_id = requested_account_id
  ) THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT base.*
  FROM omi_memory.lock_authority_state(
    requested_account_id,
    requested_principal_id,
    requested_application_id,
    requested_credential_id,
    requested_credential_generation,
    requested_capability,
    requested_grant_id
  ) AS base;
END
$function$;

REVOKE ALL ON FUNCTION omi_memory.lookup_unfenced_firebase_application_authorization(
  text, text, text, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.lock_unfenced_authority_state(
  text, text, text, text, bigint, text, text
) FROM PUBLIC;

-- The original entrypoints remain private implementation details for these
-- wrappers and restore/owner tooling. Canonical application code can execute
-- only the deletion-aware forms after this migration.
REVOKE EXECUTE ON FUNCTION omi_memory.lookup_firebase_application_authorization(
  text, text, text, text
) FROM omi_platform_application;
REVOKE EXECUTE ON FUNCTION omi_memory.lock_authority_state(
  text, text, text, text, bigint, text, text
) FROM omi_platform_application;

GRANT EXECUTE ON FUNCTION omi_memory.lookup_unfenced_firebase_application_authorization(
  text, text, text, text
) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.lock_unfenced_authority_state(
  text, text, text, text, bigint, text, text
) TO omi_platform_application;
