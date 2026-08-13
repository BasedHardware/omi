-- P7 restored-generation gate for internal service-worker contexts.
--
-- A context without an exact restore-release binding is a legacy pre-restore
-- capability. It remains usable only until this database records its first
-- restore-admission head. The table SHARE lock linearizes that final legacy
-- transaction against concurrent restore registration. Released contexts use
-- the private deletion-aware helper after locking their exact release row.

CREATE FUNCTION omi_memory.lock_terminal_unfenced_authority_state(
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

CREATE OR REPLACE FUNCTION omi_memory.lock_unfenced_authority_state(
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
  -- SHARE conflicts with the RowExclusive lock taken by INSERT/UPDATE. The
  -- first restore-head write therefore cannot slip behind a successful legacy
  -- worker transaction, and no legacy worker can begin after registration.
  LOCK TABLE omi_memory.postgres_restore_admission_heads IN SHARE MODE;

  IF EXISTS (
    SELECT 1
    FROM omi_memory.postgres_restore_admission_heads
  ) THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT base.*
  FROM omi_memory.lock_terminal_unfenced_authority_state(
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

CREATE OR REPLACE FUNCTION omi_memory.lock_released_unfenced_authority_state(
  requested_account_id text,
  requested_principal_id text,
  requested_application_id text,
  requested_credential_id text,
  requested_credential_generation bigint,
  requested_capability text,
  requested_grant_id text,
  requested_database_generation_digest text,
  requested_restore_release_revision bigint,
  requested_restore_release_content_hash text
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
DECLARE
  current_release_revision bigint;
  current_release_state text;
  current_release_content_hash text;
BEGIN
  IF requested_database_generation_digest IS NULL
    OR requested_database_generation_digest !~ '^[0-9a-f]{64}$'
    OR requested_restore_release_revision IS NULL
    OR requested_restore_release_revision < 0
    OR requested_restore_release_content_hash IS NULL
    OR requested_restore_release_content_hash !~ '^[0-9a-f]{64}$' THEN
    RETURN;
  END IF;

  SELECT release.release_revision, release.state, release.content_hash
    INTO current_release_revision, current_release_state, current_release_content_hash
  FROM omi_memory.postgres_restore_admission_heads AS head
  JOIN omi_memory.postgres_restore_admission_revisions AS release
    ON release.database_generation_digest = head.database_generation_digest
   AND release.release_revision = head.release_revision
  WHERE head.database_generation_digest = requested_database_generation_digest
  FOR SHARE OF head, release;

  IF NOT FOUND
    OR current_release_revision <> requested_restore_release_revision
    OR current_release_state <> 'released'
    OR current_release_content_hash <> requested_restore_release_content_hash THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT base.*
  FROM omi_memory.lock_terminal_unfenced_authority_state(
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

REVOKE ALL ON FUNCTION omi_memory.lock_terminal_unfenced_authority_state(
  text, text, text, text, bigint, text, text
) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION omi_memory.lock_terminal_unfenced_authority_state(
  text, text, text, text, bigint, text, text
) FROM omi_platform_application;
REVOKE EXECUTE ON FUNCTION omi_memory.lock_authority_state(
  text, text, text, text, bigint, text, text
) FROM omi_platform_application;

GRANT EXECUTE ON FUNCTION omi_memory.lock_unfenced_authority_state(
  text, text, text, text, bigint, text, text
) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.lock_released_unfenced_authority_state(
  text, text, text, text, bigint, text, text, text, bigint, text
) TO omi_platform_application;
