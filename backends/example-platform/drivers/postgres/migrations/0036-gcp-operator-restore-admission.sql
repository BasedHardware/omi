-- Replace the inert two-person restore-release shape with David's ratified
-- one-operator GCP IAM boundary. Migration 29 remains immutable. Historical
-- released rows stay readable; every new release created here uses gcp_iam and
-- carries no application-level approval or manual-release receipt.

ALTER TABLE omi_memory.postgres_restore_admission_revisions
  ADD COLUMN release_authority text
  CHECK (release_authority IS NULL OR release_authority = 'gcp_iam');

DO $block$
DECLARE
  prior_shape_constraint name;
BEGIN
  SELECT constraint_row.conname
    INTO prior_shape_constraint
  FROM pg_catalog.pg_constraint AS constraint_row
  WHERE constraint_row.conrelid =
      'omi_memory.postgres_restore_admission_revisions'::regclass
    AND constraint_row.contype = 'c'
    AND pg_catalog.pg_get_constraintdef(constraint_row.oid)
      LIKE '%first_approval_subject_digest <> second_approval_subject_digest%';

  IF prior_shape_constraint IS NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P3600', MESSAGE = 'restore admission prior shape unavailable';
  END IF;

  EXECUTE pg_catalog.format(
    'ALTER TABLE omi_memory.postgres_restore_admission_revisions DROP CONSTRAINT %I',
    prior_shape_constraint
  );
END;
$block$;

ALTER TABLE omi_memory.postgres_restore_admission_revisions
  ADD CONSTRAINT postgres_restore_admission_state_shape_v2 CHECK (
    (state = 'pending'
      AND checkpoint_candidate_digest IS NULL
      AND checkpoint_evidence_digest IS NULL
      AND first_approval_subject_digest IS NULL
      AND first_approval_receipt_digest IS NULL
      AND second_approval_subject_digest IS NULL
      AND second_approval_receipt_digest IS NULL
      AND manual_release_receipt_digest IS NULL
      AND release_authority IS NULL)
    OR
    (state = 'checkpointed'
      AND checkpoint_candidate_digest IS NOT NULL
      AND checkpoint_evidence_digest IS NOT NULL
      AND first_approval_subject_digest IS NULL
      AND first_approval_receipt_digest IS NULL
      AND second_approval_subject_digest IS NULL
      AND second_approval_receipt_digest IS NULL
      AND manual_release_receipt_digest IS NULL
      AND release_authority IS NULL)
    OR
    -- Historical migration-29 release rows remain valid and immutable.
    (state = 'released'
      AND checkpoint_candidate_digest IS NOT NULL
      AND checkpoint_evidence_digest IS NOT NULL
      AND first_approval_subject_digest IS NOT NULL
      AND first_approval_receipt_digest IS NOT NULL
      AND second_approval_subject_digest IS NOT NULL
      AND second_approval_receipt_digest IS NOT NULL
      AND first_approval_subject_digest <> second_approval_subject_digest
      AND first_approval_receipt_digest <> second_approval_receipt_digest
      AND manual_release_receipt_digest IS NOT NULL
      AND release_authority IS NULL)
    OR
    -- New releases rely on the caller's GCP-IAM-backed database role.
    (state = 'released'
      AND checkpoint_candidate_digest IS NOT NULL
      AND checkpoint_evidence_digest IS NOT NULL
      AND first_approval_subject_digest IS NULL
      AND first_approval_receipt_digest IS NULL
      AND second_approval_subject_digest IS NULL
      AND second_approval_receipt_digest IS NULL
      AND manual_release_receipt_digest IS NULL
      AND release_authority = 'gcp_iam')
  );

CREATE FUNCTION omi_memory.release_postgres_restore_generation_v2(
  p_database_generation_digest text,
  p_expected_checkpoint_revision bigint,
  p_expected_checkpoint_content_hash text,
  p_expected_checkpoint_candidate_digest text,
  p_expected_checkpoint_evidence_digest text,
  p_release_revision bigint,
  p_release_content_hash text
)
RETURNS TABLE (
  result text,
  release_revision bigint,
  release_content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  current_row omi_memory.postgres_restore_admission_revisions%ROWTYPE;
  replay_row omi_memory.postgres_restore_admission_revisions%ROWTYPE;
BEGIN
  IF p_database_generation_digest IS NULL
    OR p_database_generation_digest !~ '^[0-9a-f]{64}$'
    OR p_expected_checkpoint_revision IS NULL OR p_expected_checkpoint_revision < 0
    OR p_release_revision IS NULL OR p_release_revision <= p_expected_checkpoint_revision
    OR p_expected_checkpoint_content_hash IS NULL
    OR p_expected_checkpoint_content_hash !~ '^[0-9a-f]{64}$'
    OR p_expected_checkpoint_candidate_digest IS NULL
    OR p_expected_checkpoint_candidate_digest !~ '^[0-9a-f]{64}$'
    OR p_expected_checkpoint_evidence_digest IS NULL
    OR p_expected_checkpoint_evidence_digest !~ '^[0-9a-f]{64}$'
    OR p_release_content_hash IS NULL OR p_release_content_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = 'P3601', MESSAGE = 'restore release invalid';
  END IF;

  -- The head row is the per-generation serialization point. The GCP-IAM-backed
  -- role grant on this fixed function is the complete approval boundary.
  SELECT revision.*
    INTO current_row
  FROM omi_memory.postgres_restore_admission_heads AS head
  JOIN omi_memory.postgres_restore_admission_revisions AS revision
    ON revision.database_generation_digest = head.database_generation_digest
   AND revision.release_revision = head.release_revision
  WHERE head.database_generation_digest = p_database_generation_digest
  FOR UPDATE OF head, revision;

  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P3602', MESSAGE = 'restore release stale';
  END IF;

  IF current_row.state = 'released' THEN
    SELECT revision.*
      INTO replay_row
    FROM omi_memory.postgres_restore_admission_revisions AS revision
    WHERE revision.database_generation_digest = p_database_generation_digest
      AND revision.release_revision = p_release_revision;
    IF FOUND
      AND replay_row.state = 'released'
      AND replay_row.release_authority = 'gcp_iam'
      AND replay_row.previous_release_revision = p_expected_checkpoint_revision
      AND replay_row.checkpoint_candidate_digest = p_expected_checkpoint_candidate_digest
      AND replay_row.checkpoint_evidence_digest = p_expected_checkpoint_evidence_digest
      AND replay_row.content_hash = p_release_content_hash
      AND current_row.release_revision = replay_row.release_revision
      AND current_row.content_hash = replay_row.content_hash THEN
      RETURN QUERY SELECT 'replayed'::text, replay_row.release_revision, replay_row.content_hash;
      RETURN;
    END IF;
    RAISE EXCEPTION USING ERRCODE = 'P3603', MESSAGE = 'restore release conflict';
  END IF;

  IF current_row.state <> 'checkpointed'
    OR current_row.release_revision <> p_expected_checkpoint_revision
    OR current_row.content_hash <> p_expected_checkpoint_content_hash
    OR current_row.checkpoint_candidate_digest <> p_expected_checkpoint_candidate_digest
    OR current_row.checkpoint_evidence_digest <> p_expected_checkpoint_evidence_digest THEN
    RAISE EXCEPTION USING ERRCODE = 'P3602', MESSAGE = 'restore release stale';
  END IF;

  INSERT INTO omi_memory.postgres_restore_admission_revisions (
    database_generation_digest, release_revision, state, restore_id,
    restored_snapshot_digest, checkpoint_candidate_digest,
    checkpoint_evidence_digest, first_approval_subject_digest,
    first_approval_receipt_digest, second_approval_subject_digest,
    second_approval_receipt_digest, manual_release_receipt_digest,
    previous_release_revision, content_hash, release_authority
  ) VALUES (
    p_database_generation_digest, p_release_revision, 'released', current_row.restore_id,
    current_row.restored_snapshot_digest, current_row.checkpoint_candidate_digest,
    current_row.checkpoint_evidence_digest, NULL, NULL, NULL, NULL, NULL,
    current_row.release_revision, p_release_content_hash, 'gcp_iam'
  );

  UPDATE omi_memory.postgres_restore_admission_heads AS head
  SET release_revision = p_release_revision,
      updated_at = transaction_timestamp()
  WHERE head.database_generation_digest = p_database_generation_digest
    AND head.release_revision = p_expected_checkpoint_revision;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P3602', MESSAGE = 'restore release stale';
  END IF;

  RETURN QUERY SELECT 'released'::text, p_release_revision, p_release_content_hash;
END;
$function$;

REVOKE ALL ON FUNCTION omi_memory.release_postgres_restore_generation_v2(
  text, bigint, text, text, text, bigint, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.release_postgres_restore_generation_v2(
  text, bigint, text, text, text, bigint, text
) FROM omi_platform_application;
REVOKE ALL ON FUNCTION omi_memory.release_postgres_restore_generation_v2(
  text, bigint, text, text, text, bigint, text
) FROM omi_platform_cleanup;
REVOKE ALL ON FUNCTION omi_memory.release_postgres_restore_generation_v2(
  text, bigint, text, text, text, bigint, text
) FROM omi_platform_restore;
GRANT USAGE ON SCHEMA omi_memory TO omi_platform_restore_operator;
GRANT EXECUTE ON FUNCTION omi_memory.release_postgres_restore_generation_v2(
  text, bigint, text, text, text, bigint, text
) TO omi_platform_restore_operator;
