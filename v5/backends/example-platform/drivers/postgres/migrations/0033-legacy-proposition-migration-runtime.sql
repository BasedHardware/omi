-- P4 route-free legacy proposition migration resume. The application role may
-- invoke only these fixed functions; mapping and tombstone tables remain
-- inaccessible directly.

CREATE FUNCTION omi_memory.resume_legacy_proposition_mapping(
  p_account_id text,
  p_legacy_source_id text,
  p_proposed_proposition_id text,
  p_mapping_content_hash text
)
RETURNS TABLE (
  result_kind text,
  mapping_version text,
  owner_account_id text,
  legacy_source_id text,
  proposition_id text,
  content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
DECLARE
  v_mapping omi_memory.memory_legacy_proposition_mappings%ROWTYPE;
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM p_account_id
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.project' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'legacy migration authority denied';
  END IF;
  IF p_account_id IS NULL OR length(p_account_id) NOT BETWEEN 1 AND 256
     OR p_legacy_source_id IS NULL OR length(p_legacy_source_id) NOT BETWEEN 1 AND 256
     OR (p_proposed_proposition_id IS NULL) <> (p_mapping_content_hash IS NULL)
     OR (p_mapping_content_hash IS NOT NULL AND p_mapping_content_hash !~ '^[0-9a-f]{64}$')
     OR (p_proposed_proposition_id IS NOT NULL AND (
       length(p_proposed_proposition_id) NOT BETWEEN 1 AND 256
       OR p_proposed_proposition_id ~ '^grp1_[0-9a-f]{64}$'
       OR position(lower(p_legacy_source_id) in lower(p_proposed_proposition_id)) > 0
     )) THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'legacy migration request invalid';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(
    length(p_account_id)::text || ':' || p_account_id || p_legacy_source_id,
    7331
  ));

  IF EXISTS (
    SELECT 1 FROM omi_memory.memory_migration_item_tombstones AS t
    WHERE t.account_id = p_account_id AND t.legacy_source_id = p_legacy_source_id
  ) THEN
    RETURN QUERY SELECT 'tombstoned'::text, NULL::text, NULL::text, NULL::text, NULL::text, NULL::text;
    RETURN;
  END IF;

  SELECT * INTO v_mapping
  FROM omi_memory.memory_legacy_proposition_mappings AS m
  WHERE m.account_id = p_account_id AND m.legacy_source_id = p_legacy_source_id;
  IF FOUND THEN
    RETURN QUERY SELECT
      'reused'::text, 'product-projection-v1'::text, v_mapping.account_id,
      v_mapping.legacy_source_id, v_mapping.proposition_id, v_mapping.content_hash;
    RETURN;
  END IF;

  IF p_proposed_proposition_id IS NULL THEN
    RETURN QUERY SELECT 'allocation_required'::text, NULL::text, NULL::text, NULL::text, NULL::text, NULL::text;
    RETURN;
  END IF;

  BEGIN
    INSERT INTO omi_memory.memory_legacy_proposition_mappings
      (account_id, legacy_source_id, proposition_id, allocation_contract, content_hash)
    VALUES
      (p_account_id, p_legacy_source_id, p_proposed_proposition_id, 'random_opaque_v1', p_mapping_content_hash)
    RETURNING * INTO v_mapping;
  EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'legacy migration mapping conflict';
  END;

  RETURN QUERY SELECT
    'inserted'::text, 'product-projection-v1'::text, v_mapping.account_id,
    v_mapping.legacy_source_id, v_mapping.proposition_id, v_mapping.content_hash;
END;
$$;

CREATE FUNCTION omi_memory.record_legacy_migration_item_tombstone(
  p_account_id text,
  p_legacy_source_id text,
  p_tombstone_sequence bigint,
  p_tombstone_operation_id text,
  p_tombstoned_at_event_time bigint,
  p_request_digest text
)
RETURNS TABLE (result_kind text, request_digest text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
DECLARE
  v_existing omi_memory.memory_migration_item_tombstones%ROWTYPE;
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM p_account_id
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.project' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1005', MESSAGE = 'legacy migration authority denied';
  END IF;
  IF p_account_id IS NULL OR length(p_account_id) NOT BETWEEN 1 AND 256
     OR p_legacy_source_id IS NULL OR length(p_legacy_source_id) NOT BETWEEN 1 AND 256
     OR p_tombstone_sequence IS NULL OR p_tombstone_sequence < 1
     OR p_tombstone_operation_id IS NULL OR length(p_tombstone_operation_id) NOT BETWEEN 1 AND 256
     OR p_tombstoned_at_event_time IS NULL OR p_tombstoned_at_event_time < 0
     OR p_request_digest IS NULL OR p_request_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = 'P1002', MESSAGE = 'legacy migration tombstone invalid';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(
    length(p_account_id)::text || ':' || p_account_id || p_legacy_source_id,
    7331
  ));

  SELECT * INTO v_existing
  FROM omi_memory.memory_migration_item_tombstones AS t
  WHERE t.account_id = p_account_id AND t.legacy_source_id = p_legacy_source_id;
  IF FOUND THEN
    IF v_existing.tombstone_sequence IS DISTINCT FROM p_tombstone_sequence
       OR v_existing.tombstone_operation_id IS DISTINCT FROM p_tombstone_operation_id
       OR v_existing.tombstoned_at_event_time IS DISTINCT FROM p_tombstoned_at_event_time
       OR v_existing.content_hash IS DISTINCT FROM p_request_digest THEN
      RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'legacy migration tombstone conflict';
    END IF;
    RETURN QUERY SELECT 'replayed'::text, v_existing.content_hash;
    RETURN;
  END IF;

  BEGIN
    INSERT INTO omi_memory.memory_migration_item_tombstones
      (account_id, legacy_source_id, tombstone_sequence, tombstone_operation_id,
       tombstoned_at_event_time, content_hash)
    VALUES
      (p_account_id, p_legacy_source_id, p_tombstone_sequence, p_tombstone_operation_id,
       p_tombstoned_at_event_time, p_request_digest);
  EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION USING ERRCODE = 'P1001', MESSAGE = 'legacy migration tombstone conflict';
  END;
  RETURN QUERY SELECT 'recorded'::text, p_request_digest;
END;
$$;

REVOKE ALL ON FUNCTION omi_memory.resume_legacy_proposition_mapping(text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.record_legacy_migration_item_tombstone(text, text, bigint, text, bigint, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.resume_legacy_proposition_mapping(text, text, text, text) TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.record_legacy_migration_item_tombstone(text, text, bigint, text, bigint, text) TO omi_platform_application;

REVOKE ALL ON omi_memory.memory_legacy_proposition_mappings FROM omi_platform_application;
REVOKE ALL ON omi_memory.memory_migration_item_tombstones FROM omi_platform_application;
