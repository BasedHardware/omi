-- P7 retained, content-free receipts for exact-generation Google Cloud Storage cleanup.
-- Object names, generations, provider credentials, and content never enter PostgreSQL.

CREATE TABLE omi_memory.account_gcs_deletion_receipts (
  account_id text NOT NULL,
  deletion_epoch bigint NOT NULL CHECK (deletion_epoch >= 0),
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  operation_ref text NOT NULL CHECK (operation_ref ~ '^opref1_[0-9a-f]{64}$'),
  eligibility_digest text NOT NULL CHECK (eligibility_digest ~ '^[0-9a-f]{64}$'),
  registry_digest text NOT NULL CHECK (registry_digest ~ '^[0-9a-f]{64}$'),
  policy_digest text NOT NULL CHECK (policy_digest ~ '^[0-9a-f]{64}$'),
  owner_mapping_digest text NOT NULL CHECK (owner_mapping_digest ~ '^[0-9a-f]{64}$'),
  resource_role text NOT NULL CHECK (resource_role IN (
    'speech_profiles', 'conversation_recordings', 'private_sync_chunks',
    'private_sync_audio', 'private_sync_merged', 'private_sync_playback',
    'temporal_sync', 'chat_files'
  )),
  bucket_name text NOT NULL CHECK (
    octet_length(bucket_name) BETWEEN 3 AND 222
    AND bucket_name ~ '^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?)*$'
  ),
  prefix_digest text NOT NULL CHECK (prefix_digest ~ '^[0-9a-f]{64}$'),
  result text NOT NULL CHECK (result IN ('disposed', 'already_absent')),
  pre_delete_count bigint NOT NULL CHECK (pre_delete_count BETWEEN 0 AND 100000),
  CHECK (
    (result = 'disposed' AND pre_delete_count > 0)
    OR (result = 'already_absent' AND pre_delete_count = 0)
  ),
  pre_delete_set_digest text NOT NULL CHECK (pre_delete_set_digest ~ '^[0-9a-f]{64}$'),
  provider_receipt_digest text NOT NULL CHECK (provider_receipt_digest ~ '^[0-9a-f]{64}$'),
  receipt_digest text NOT NULL CHECK (receipt_digest ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, deletion_epoch, operation_ref, resource_role, bucket_name),
  FOREIGN KEY (account_id, deletion_epoch)
    REFERENCES omi_memory.account_terminal_deletion_exports (account_id, deletion_epoch)
);

CREATE FUNCTION omi_memory.load_gcs_deletion_receipt(
  p_account_id text,
  p_control_revision bigint,
  p_deletion_epoch bigint,
  p_operation_ref text,
  p_eligibility_digest text,
  p_registry_digest text,
  p_policy_digest text,
  p_owner_mapping_digest text,
  p_resource_role text,
  p_bucket_name text,
  p_prefix_digest text
)
RETURNS SETOF omi_memory.account_gcs_deletion_receipts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_receipt omi_memory.account_gcs_deletion_receipts%ROWTYPE;
BEGIN
  IF p_operation_ref !~ '^opref1_[0-9a-f]{64}$'
    OR p_eligibility_digest !~ '^[0-9a-f]{64}$'
    OR p_registry_digest !~ '^[0-9a-f]{64}$'
    OR p_policy_digest !~ '^[0-9a-f]{64}$'
    OR p_owner_mapping_digest !~ '^[0-9a-f]{64}$'
    OR p_resource_role NOT IN (
      'speech_profiles', 'conversation_recordings', 'private_sync_chunks',
      'private_sync_audio', 'private_sync_merged', 'private_sync_playback',
      'temporal_sync', 'chat_files'
    )
    OR octet_length(p_bucket_name) NOT BETWEEN 3 AND 222
    OR p_bucket_name !~ '^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?)*$'
    OR p_prefix_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'gcs_receipt_input_invalid';
  END IF;

  PERFORM 1
  FROM omi_memory.account_terminal_deletion_exports te
  WHERE te.account_id = p_account_id
    AND te.deletion_epoch = p_deletion_epoch
    AND te.control_revision = p_control_revision
  FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'gcs_receipt_coordinate_denied';
  END IF;

  SELECT * INTO v_receipt
  FROM omi_memory.account_gcs_deletion_receipts r
  WHERE r.account_id = p_account_id
    AND r.deletion_epoch = p_deletion_epoch
    AND r.operation_ref = p_operation_ref
    AND r.resource_role = p_resource_role
    AND r.bucket_name = p_bucket_name;
  IF NOT FOUND THEN RETURN; END IF;

  IF v_receipt.control_revision <> p_control_revision
    OR v_receipt.eligibility_digest <> p_eligibility_digest
    OR v_receipt.registry_digest <> p_registry_digest
    OR v_receipt.policy_digest <> p_policy_digest
    OR v_receipt.owner_mapping_digest <> p_owner_mapping_digest
    OR v_receipt.bucket_name <> p_bucket_name
    OR v_receipt.prefix_digest <> p_prefix_digest THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'gcs_receipt_conflict';
  END IF;

  RETURN NEXT v_receipt;
END
$function$;

CREATE FUNCTION omi_memory.record_gcs_deletion_receipt(
  p_account_id text,
  p_control_revision bigint,
  p_deletion_epoch bigint,
  p_operation_ref text,
  p_eligibility_digest text,
  p_registry_digest text,
  p_policy_digest text,
  p_owner_mapping_digest text,
  p_resource_role text,
  p_bucket_name text,
  p_prefix_digest text,
  p_result text,
  p_pre_delete_count bigint,
  p_pre_delete_set_digest text,
  p_provider_receipt_digest text,
  p_receipt_digest text
)
RETURNS SETOF omi_memory.account_gcs_deletion_receipts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_receipt omi_memory.account_gcs_deletion_receipts%ROWTYPE;
BEGIN
  IF p_operation_ref !~ '^opref1_[0-9a-f]{64}$'
    OR p_eligibility_digest !~ '^[0-9a-f]{64}$'
    OR p_registry_digest !~ '^[0-9a-f]{64}$'
    OR p_policy_digest !~ '^[0-9a-f]{64}$'
    OR p_owner_mapping_digest !~ '^[0-9a-f]{64}$'
    OR p_resource_role NOT IN (
      'speech_profiles', 'conversation_recordings', 'private_sync_chunks',
      'private_sync_audio', 'private_sync_merged', 'private_sync_playback',
      'temporal_sync', 'chat_files'
    )
    OR octet_length(p_bucket_name) NOT BETWEEN 3 AND 222
    OR p_bucket_name !~ '^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?)*$'
    OR p_prefix_digest !~ '^[0-9a-f]{64}$'
    OR p_result NOT IN ('disposed', 'already_absent')
    OR p_pre_delete_count NOT BETWEEN 0 AND 100000
    OR (p_result = 'disposed' AND p_pre_delete_count = 0)
    OR (p_result = 'already_absent' AND p_pre_delete_count <> 0)
    OR p_pre_delete_set_digest !~ '^[0-9a-f]{64}$'
    OR p_provider_receipt_digest !~ '^[0-9a-f]{64}$'
    OR p_receipt_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'gcs_receipt_input_invalid';
  END IF;

  PERFORM 1
  FROM omi_memory.account_terminal_deletion_exports te
  WHERE te.account_id = p_account_id
    AND te.deletion_epoch = p_deletion_epoch
    AND te.control_revision = p_control_revision
  FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'gcs_receipt_coordinate_denied';
  END IF;

  INSERT INTO omi_memory.account_gcs_deletion_receipts (
    account_id, deletion_epoch, control_revision, operation_ref,
    eligibility_digest, registry_digest, policy_digest, owner_mapping_digest, resource_role,
    bucket_name, prefix_digest, result, pre_delete_count, pre_delete_set_digest,
    provider_receipt_digest, receipt_digest
  ) VALUES (
    p_account_id, p_deletion_epoch, p_control_revision, p_operation_ref,
    p_eligibility_digest, p_registry_digest, p_policy_digest, p_owner_mapping_digest, p_resource_role,
    p_bucket_name, p_prefix_digest, p_result, p_pre_delete_count, p_pre_delete_set_digest,
    p_provider_receipt_digest, p_receipt_digest
  ) ON CONFLICT DO NOTHING;

  SELECT * INTO STRICT v_receipt
  FROM omi_memory.account_gcs_deletion_receipts r
  WHERE r.account_id = p_account_id
    AND r.deletion_epoch = p_deletion_epoch
    AND r.operation_ref = p_operation_ref
    AND r.resource_role = p_resource_role
    AND r.bucket_name = p_bucket_name;

  IF v_receipt.control_revision <> p_control_revision
    OR v_receipt.eligibility_digest <> p_eligibility_digest
    OR v_receipt.registry_digest <> p_registry_digest
    OR v_receipt.policy_digest <> p_policy_digest
    OR v_receipt.owner_mapping_digest <> p_owner_mapping_digest
    OR v_receipt.bucket_name <> p_bucket_name
    OR v_receipt.prefix_digest <> p_prefix_digest
    OR v_receipt.result <> p_result
    OR v_receipt.pre_delete_count <> p_pre_delete_count
    OR v_receipt.pre_delete_set_digest <> p_pre_delete_set_digest
    OR v_receipt.provider_receipt_digest <> p_provider_receipt_digest
    OR v_receipt.receipt_digest <> p_receipt_digest THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'gcs_receipt_conflict';
  END IF;

  RETURN NEXT v_receipt;
END
$function$;

REVOKE ALL ON TABLE omi_memory.account_gcs_deletion_receipts
  FROM PUBLIC, omi_platform_application, omi_platform_cleanup;
REVOKE ALL ON FUNCTION omi_memory.load_gcs_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, text, text
) FROM PUBLIC, omi_platform_application;
REVOKE ALL ON FUNCTION omi_memory.record_gcs_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, text, text,
  text, bigint, text, text, text
) FROM PUBLIC, omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.load_gcs_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, text, text
) TO omi_platform_cleanup;
GRANT EXECUTE ON FUNCTION omi_memory.record_gcs_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, text, text,
  text, bigint, text, text, text
) TO omi_platform_cleanup;
