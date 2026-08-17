-- P7 inert restore-replay checkpoint candidate persistence. A candidate is
-- evidence only: it cannot release a generation, open traffic, or mint account
-- authority. `omi_platform_restore` is provisioned externally as NOLOGIN.

CREATE TABLE omi_memory.postgres_restore_replay_checkpoint_candidates (
  restore_id text PRIMARY KEY CHECK (restore_id ~ '^[!-~]+$' AND length(restore_id) <= 256),
  restored_generation_digest text NOT NULL
    CHECK (restored_generation_digest ~ '^[0-9a-f]{64}$'),
  restore_scope text NOT NULL CHECK (restore_scope = 'postgresql'),
  restored_snapshot_digest text NOT NULL CHECK (restored_snapshot_digest ~ '^[0-9a-f]{64}$'),
  restore_completed_at_epoch_seconds bigint NOT NULL
    CHECK (restore_completed_at_epoch_seconds BETWEEN 0 AND 9007199254740991),
  source_snapshot_digest text NOT NULL CHECK (source_snapshot_digest ~ '^[0-9a-f]{64}$'),
  source_feed_generation_digest text NOT NULL
    CHECK (source_feed_generation_digest ~ '^[0-9a-f]{64}$'),
  partition_topology_digest text NOT NULL
    CHECK (partition_topology_digest ~ '^[0-9a-f]{64}$'),
  source_high_watermark bigint NOT NULL
    CHECK (source_high_watermark BETWEEN 0 AND 9007199254740991),
  manifest_digest text NOT NULL CHECK (manifest_digest ~ '^[0-9a-f]{64}$'),
  record_count bigint NOT NULL CHECK (record_count BETWEEN 0 AND 10000),
  terminal_source_receipt_binding_digest text NOT NULL
    CHECK (terminal_source_receipt_binding_digest ~ '^[0-9a-f]{64}$'),
  application_set_digest text NOT NULL CHECK (application_set_digest ~ '^[0-9a-f]{64}$'),
  terminal_feed_fence_receipt_digest text NOT NULL
    CHECK (terminal_feed_fence_receipt_digest ~ '^[0-9a-f]{64}$'),
  checkpoint_digest text NOT NULL CHECK (checkpoint_digest ~ '^[0-9a-f]{64}$'),
  candidate_digest text NOT NULL CHECK (candidate_digest ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz NOT NULL,
  UNIQUE (restored_generation_digest, restore_id),
  UNIQUE (restored_generation_digest, candidate_digest)
);

CREATE FUNCTION omi_memory.record_postgres_restore_replay_checkpoint_candidate(
  p_restored_generation_digest text,
  p_restore_id text,
  p_restored_snapshot_digest text,
  p_restore_completed_at_epoch_seconds bigint,
  p_source_snapshot_digest text,
  p_source_feed_generation_digest text,
  p_partition_topology_digest text,
  p_source_high_watermark bigint,
  p_manifest_digest text,
  p_record_count bigint,
  p_terminal_source_receipt_binding_digest text,
  p_application_set_digest text,
  p_terminal_feed_fence_receipt_digest text,
  p_checkpoint_digest text,
  p_candidate_digest text
)
RETURNS TABLE(result text, recorded_at_epoch_micros text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_recorded_at timestamptz := clock_timestamp();
  v_existing omi_memory.postgres_restore_replay_checkpoint_candidates%ROWTYPE;
BEGIN
  IF p_restored_generation_digest IS NULL
    OR p_restored_generation_digest !~ '^[0-9a-f]{64}$'
    OR p_restore_id IS NULL OR p_restore_id !~ '^[!-~]+$' OR length(p_restore_id) > 256
    OR p_restored_snapshot_digest IS NULL OR p_restored_snapshot_digest !~ '^[0-9a-f]{64}$'
    OR p_restore_completed_at_epoch_seconds IS NULL
    OR p_restore_completed_at_epoch_seconds < 0
    OR p_restore_completed_at_epoch_seconds > 9007199254740991
    OR p_source_snapshot_digest IS NULL OR p_source_snapshot_digest !~ '^[0-9a-f]{64}$'
    OR p_source_feed_generation_digest IS NULL
    OR p_source_feed_generation_digest !~ '^[0-9a-f]{64}$'
    OR p_partition_topology_digest IS NULL OR p_partition_topology_digest !~ '^[0-9a-f]{64}$'
    OR p_source_high_watermark IS NULL OR p_source_high_watermark < 0
    OR p_source_high_watermark > 9007199254740991
    OR p_manifest_digest IS NULL OR p_manifest_digest !~ '^[0-9a-f]{64}$'
    OR p_record_count IS NULL OR p_record_count < 0 OR p_record_count > 10000
    OR p_terminal_source_receipt_binding_digest IS NULL
    OR p_terminal_source_receipt_binding_digest !~ '^[0-9a-f]{64}$'
    OR p_application_set_digest IS NULL OR p_application_set_digest !~ '^[0-9a-f]{64}$'
    OR p_terminal_feed_fence_receipt_digest IS NULL
    OR p_terminal_feed_fence_receipt_digest !~ '^[0-9a-f]{64}$'
    OR p_checkpoint_digest IS NULL OR p_checkpoint_digest !~ '^[0-9a-f]{64}$'
    OR p_candidate_digest IS NULL OR p_candidate_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'restore_checkpoint_candidate_invalid';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_restore_id, 731028));
  SELECT * INTO v_existing
  FROM omi_memory.postgres_restore_replay_checkpoint_candidates c
  WHERE c.restore_id = p_restore_id;
  IF FOUND THEN
    IF v_existing.restored_generation_digest <> p_restored_generation_digest
      OR v_existing.restored_snapshot_digest <> p_restored_snapshot_digest
      OR v_existing.restore_completed_at_epoch_seconds <> p_restore_completed_at_epoch_seconds
      OR v_existing.source_snapshot_digest <> p_source_snapshot_digest
      OR v_existing.source_feed_generation_digest <> p_source_feed_generation_digest
      OR v_existing.partition_topology_digest <> p_partition_topology_digest
      OR v_existing.source_high_watermark <> p_source_high_watermark
      OR v_existing.manifest_digest <> p_manifest_digest
      OR v_existing.record_count <> p_record_count
      OR v_existing.terminal_source_receipt_binding_digest
        <> p_terminal_source_receipt_binding_digest
      OR v_existing.application_set_digest <> p_application_set_digest
      OR v_existing.terminal_feed_fence_receipt_digest
        <> p_terminal_feed_fence_receipt_digest
      OR v_existing.checkpoint_digest <> p_checkpoint_digest
      OR v_existing.candidate_digest <> p_candidate_digest THEN
      RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'restore_checkpoint_candidate_conflict';
    END IF;
    RETURN QUERY SELECT 'replayed'::text,
      (floor(extract(epoch FROM v_existing.recorded_at) * 1000000)::bigint)::text;
    RETURN;
  END IF;

  INSERT INTO omi_memory.postgres_restore_replay_checkpoint_candidates (
    restored_generation_digest, restore_id, restore_scope, restored_snapshot_digest,
    restore_completed_at_epoch_seconds, source_snapshot_digest, source_high_watermark,
    source_feed_generation_digest, partition_topology_digest,
    manifest_digest, record_count, terminal_source_receipt_binding_digest,
    application_set_digest, terminal_feed_fence_receipt_digest, checkpoint_digest,
    candidate_digest, recorded_at
  ) VALUES (
    p_restored_generation_digest, p_restore_id, 'postgresql', p_restored_snapshot_digest,
    p_restore_completed_at_epoch_seconds, p_source_snapshot_digest, p_source_high_watermark,
    p_source_feed_generation_digest, p_partition_topology_digest,
    p_manifest_digest, p_record_count, p_terminal_source_receipt_binding_digest,
    p_application_set_digest, p_terminal_feed_fence_receipt_digest, p_checkpoint_digest,
    p_candidate_digest, v_recorded_at
  );
  RETURN QUERY SELECT 'recorded'::text,
    (floor(extract(epoch FROM v_recorded_at) * 1000000)::bigint)::text;
END
$function$;

CREATE FUNCTION omi_memory.read_postgres_restore_replay_checkpoint_candidate(
  p_restored_generation_digest text,
  p_restore_id text
)
RETURNS TABLE(
  restore_id text,
  restored_generation_digest text,
  restore_scope text,
  restored_snapshot_digest text,
  restore_completed_at_epoch_seconds bigint,
  source_snapshot_digest text,
  source_feed_generation_digest text,
  partition_topology_digest text,
  source_high_watermark bigint,
  manifest_digest text,
  record_count bigint,
  terminal_source_receipt_binding_digest text,
  application_set_digest text,
  terminal_feed_fence_receipt_digest text,
  checkpoint_digest text,
  candidate_digest text,
  recorded_at_epoch_micros text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT
    c.restore_id,
    c.restored_generation_digest,
    c.restore_scope,
    c.restored_snapshot_digest,
    c.restore_completed_at_epoch_seconds,
    c.source_snapshot_digest,
    c.source_feed_generation_digest,
    c.partition_topology_digest,
    c.source_high_watermark,
    c.manifest_digest,
    c.record_count,
    c.terminal_source_receipt_binding_digest,
    c.application_set_digest,
    c.terminal_feed_fence_receipt_digest,
    c.checkpoint_digest,
    c.candidate_digest,
    (floor(extract(epoch FROM c.recorded_at) * 1000000)::bigint)::text
  FROM omi_memory.postgres_restore_replay_checkpoint_candidates c
  WHERE c.restored_generation_digest = p_restored_generation_digest
    AND c.restore_id = p_restore_id
$function$;

REVOKE ALL ON omi_memory.postgres_restore_replay_checkpoint_candidates FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.record_postgres_restore_replay_checkpoint_candidate(
  text, text, text, bigint, text, text, text, bigint, text, bigint, text, text, text, text, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_postgres_restore_replay_checkpoint_candidate(text, text)
  FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.record_postgres_restore_replay_checkpoint_candidate(
  text, text, text, bigint, text, text, text, bigint, text, bigint, text, text, text, text, text
) TO omi_platform_restore;
GRANT EXECUTE ON FUNCTION omi_memory.read_postgres_restore_replay_checkpoint_candidate(text, text)
  TO omi_platform_restore;
