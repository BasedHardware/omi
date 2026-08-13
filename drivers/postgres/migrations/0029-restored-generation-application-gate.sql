-- P7 restored-database generation admission.
--
-- These global, append-only revisions live outside tenant memory authority.
-- No application or restore role can create or advance them. A future
-- operator/infrastructure adapter must authenticate approval receipts and
-- advance the head; until then an absent released head denies all canonical
-- Firebase PostgreSQL traffic for a configured restored generation.

CREATE TABLE omi_memory.postgres_restore_admission_revisions (
  database_generation_digest text NOT NULL
    CHECK (database_generation_digest ~ '^[0-9a-f]{64}$'),
  release_revision bigint NOT NULL CHECK (release_revision >= 0),
  state text NOT NULL CHECK (state IN ('pending', 'checkpointed', 'released')),
  restore_id text NOT NULL
    CHECK (length(restore_id) BETWEEN 1 AND 256)
    CHECK (restore_id ~ '^[!-~]+$'),
  restored_snapshot_digest text NOT NULL
    CHECK (restored_snapshot_digest ~ '^[0-9a-f]{64}$'),
  checkpoint_candidate_digest text,
  checkpoint_evidence_digest text,
  first_approval_subject_digest text,
  first_approval_receipt_digest text,
  second_approval_subject_digest text,
  second_approval_receipt_digest text,
  manual_release_receipt_digest text,
  previous_release_revision bigint,
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (database_generation_digest, release_revision),
  UNIQUE (database_generation_digest, content_hash),
  FOREIGN KEY (database_generation_digest, previous_release_revision)
    REFERENCES omi_memory.postgres_restore_admission_revisions
      (database_generation_digest, release_revision),
  CHECK (previous_release_revision IS NULL OR previous_release_revision < release_revision),
  CHECK (checkpoint_candidate_digest IS NULL OR checkpoint_candidate_digest ~ '^[0-9a-f]{64}$'),
  CHECK (checkpoint_evidence_digest IS NULL OR checkpoint_evidence_digest ~ '^[0-9a-f]{64}$'),
  CHECK (first_approval_subject_digest IS NULL OR first_approval_subject_digest ~ '^[0-9a-f]{64}$'),
  CHECK (first_approval_receipt_digest IS NULL OR first_approval_receipt_digest ~ '^[0-9a-f]{64}$'),
  CHECK (second_approval_subject_digest IS NULL OR second_approval_subject_digest ~ '^[0-9a-f]{64}$'),
  CHECK (second_approval_receipt_digest IS NULL OR second_approval_receipt_digest ~ '^[0-9a-f]{64}$'),
  CHECK (manual_release_receipt_digest IS NULL OR manual_release_receipt_digest ~ '^[0-9a-f]{64}$'),
  CHECK (
    (state = 'pending'
      AND checkpoint_candidate_digest IS NULL
      AND checkpoint_evidence_digest IS NULL
      AND first_approval_subject_digest IS NULL
      AND first_approval_receipt_digest IS NULL
      AND second_approval_subject_digest IS NULL
      AND second_approval_receipt_digest IS NULL
      AND manual_release_receipt_digest IS NULL)
    OR
    (state = 'checkpointed'
      AND checkpoint_candidate_digest IS NOT NULL
      AND checkpoint_evidence_digest IS NOT NULL
      AND first_approval_subject_digest IS NULL
      AND first_approval_receipt_digest IS NULL
      AND second_approval_subject_digest IS NULL
      AND second_approval_receipt_digest IS NULL
      AND manual_release_receipt_digest IS NULL)
    OR
    (state = 'released'
      AND checkpoint_candidate_digest IS NOT NULL
      AND checkpoint_evidence_digest IS NOT NULL
      AND first_approval_subject_digest IS NOT NULL
      AND first_approval_receipt_digest IS NOT NULL
      AND second_approval_subject_digest IS NOT NULL
      AND second_approval_receipt_digest IS NOT NULL
      AND first_approval_subject_digest <> second_approval_subject_digest
      AND first_approval_receipt_digest <> second_approval_receipt_digest
      AND manual_release_receipt_digest IS NOT NULL)
  )
);

CREATE TABLE omi_memory.postgres_restore_admission_heads (
  database_generation_digest text PRIMARY KEY,
  release_revision bigint NOT NULL CHECK (release_revision >= 0),
  updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  FOREIGN KEY (database_generation_digest, release_revision)
    REFERENCES omi_memory.postgres_restore_admission_revisions
      (database_generation_digest, release_revision)
);

CREATE FUNCTION omi_memory.lookup_released_unfenced_firebase_application_authorization(
  requested_firebase_project_id text,
  requested_firebase_uid text,
  requested_application_id text,
  requested_capability text,
  requested_database_generation_digest text
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
  grant_content_hash text,
  database_generation_digest text,
  restore_release_revision bigint,
  restore_release_content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
BEGIN
  RETURN QUERY
  SELECT base.*, release.database_generation_digest, release.release_revision, release.content_hash
  FROM omi_memory.lookup_unfenced_firebase_application_authorization(
    requested_firebase_project_id,
    requested_firebase_uid,
    requested_application_id,
    requested_capability
  ) AS base
  JOIN omi_memory.postgres_restore_admission_heads AS head
    ON head.database_generation_digest = requested_database_generation_digest
  JOIN omi_memory.postgres_restore_admission_revisions AS release
    ON release.database_generation_digest = head.database_generation_digest
   AND release.release_revision = head.release_revision
   AND release.state = 'released';
END;
$function$;

CREATE FUNCTION omi_memory.lock_released_unfenced_authority_state(
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
  FROM omi_memory.lock_unfenced_authority_state(
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

REVOKE ALL ON omi_memory.postgres_restore_admission_revisions FROM PUBLIC;
REVOKE ALL ON omi_memory.postgres_restore_admission_heads FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.lookup_released_unfenced_firebase_application_authorization(
  text, text, text, text, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.lock_released_unfenced_authority_state(
  text, text, text, text, bigint, text, text, text, bigint, text
) FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION omi_memory.lookup_unfenced_firebase_application_authorization(
  text, text, text, text
) FROM omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.lookup_released_unfenced_firebase_application_authorization(
  text, text, text, text, text
) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.lock_released_unfenced_authority_state(
  text, text, text, text, bigint, text, text, text, bigint, text
) TO omi_platform_application;
