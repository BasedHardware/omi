-- P7 retained, content-free receipts for terminal deletion of the account-owned legacy Firestore generation.
-- Firestore document paths, revisions, owner keys, credentials, and content never enter PostgreSQL.

CREATE FUNCTION omi_memory.is_firestore_legacy_generation_collection(
  p_resource_role text,
  p_collection_id text
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog, omi_memory
RETURN (p_resource_role, p_collection_id) IN (
  ('legacy_user_tree', 'users')
);

CREATE TABLE omi_memory.account_firestore_legacy_generation_deletion_receipts (
  account_id text NOT NULL,
  deletion_epoch bigint NOT NULL CHECK (deletion_epoch >= 0),
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  operation_ref text NOT NULL CHECK (operation_ref ~ '^opref1_[0-9a-f]{64}$'),
  eligibility_digest text NOT NULL CHECK (eligibility_digest ~ '^[0-9a-f]{64}$'),
  registry_digest text NOT NULL CHECK (registry_digest ~ '^[0-9a-f]{64}$'),
  policy_digest text NOT NULL CHECK (policy_digest ~ '^[0-9a-f]{64}$'),
  owner_mapping_digest text NOT NULL CHECK (owner_mapping_digest ~ '^[0-9a-f]{64}$'),
  project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9-]{4,28}[a-z0-9]$'),
  database_id text NOT NULL CHECK (
    database_id = '(default)' OR database_id ~ '^[a-z][a-z0-9_-]{0,62}$'
  ),
  resource_role text NOT NULL,
  collection_id text NOT NULL,
  CHECK (omi_memory.is_firestore_legacy_generation_collection(resource_role, collection_id)),
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
  PRIMARY KEY (account_id, deletion_epoch, operation_ref, resource_role),
  FOREIGN KEY (account_id, deletion_epoch)
    REFERENCES omi_memory.account_terminal_deletion_exports (account_id, deletion_epoch)
);

CREATE FUNCTION omi_memory.load_firestore_legacy_generation_deletion_receipt(
  p_account_id text,
  p_control_revision bigint,
  p_deletion_epoch bigint,
  p_operation_ref text,
  p_eligibility_digest text,
  p_registry_digest text,
  p_policy_digest text,
  p_owner_mapping_digest text,
  p_project_id text,
  p_database_id text,
  p_resource_role text,
  p_collection_id text
)
RETURNS SETOF omi_memory.account_firestore_legacy_generation_deletion_receipts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_receipt omi_memory.account_firestore_legacy_generation_deletion_receipts%ROWTYPE;
BEGIN
  IF p_operation_ref !~ '^opref1_[0-9a-f]{64}$'
    OR p_eligibility_digest !~ '^[0-9a-f]{64}$'
    OR p_registry_digest !~ '^[0-9a-f]{64}$'
    OR p_policy_digest !~ '^[0-9a-f]{64}$'
    OR p_owner_mapping_digest !~ '^[0-9a-f]{64}$'
    OR p_project_id !~ '^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
    OR (p_database_id <> '(default)' AND p_database_id !~ '^[a-z][a-z0-9_-]{0,62}$')
    OR NOT omi_memory.is_firestore_legacy_generation_collection(
      p_resource_role, p_collection_id
    ) THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'firestore_legacy_generation_receipt_input_invalid';
  END IF;

  PERFORM 1
  FROM omi_memory.account_terminal_deletion_exports te
  WHERE te.account_id = p_account_id
    AND te.deletion_epoch = p_deletion_epoch
    AND te.control_revision = p_control_revision
  FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'firestore_legacy_generation_receipt_coordinate_denied';
  END IF;

  SELECT * INTO v_receipt
  FROM omi_memory.account_firestore_legacy_generation_deletion_receipts r
  WHERE r.account_id = p_account_id
    AND r.deletion_epoch = p_deletion_epoch
    AND r.operation_ref = p_operation_ref
    AND r.resource_role = p_resource_role;
  IF NOT FOUND THEN RETURN; END IF;

  IF v_receipt.control_revision <> p_control_revision
    OR v_receipt.eligibility_digest <> p_eligibility_digest
    OR v_receipt.registry_digest <> p_registry_digest
    OR v_receipt.policy_digest <> p_policy_digest
    OR v_receipt.owner_mapping_digest <> p_owner_mapping_digest
    OR v_receipt.project_id <> p_project_id
    OR v_receipt.database_id <> p_database_id
    OR v_receipt.collection_id <> p_collection_id THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'firestore_legacy_generation_receipt_conflict';
  END IF;

  RETURN NEXT v_receipt;
END
$function$;

CREATE FUNCTION omi_memory.record_firestore_legacy_generation_deletion_receipt(
  p_account_id text,
  p_control_revision bigint,
  p_deletion_epoch bigint,
  p_operation_ref text,
  p_eligibility_digest text,
  p_registry_digest text,
  p_policy_digest text,
  p_owner_mapping_digest text,
  p_project_id text,
  p_database_id text,
  p_resource_role text,
  p_collection_id text,
  p_result text,
  p_pre_delete_count bigint,
  p_pre_delete_set_digest text,
  p_provider_receipt_digest text,
  p_receipt_digest text
)
RETURNS SETOF omi_memory.account_firestore_legacy_generation_deletion_receipts
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_receipt omi_memory.account_firestore_legacy_generation_deletion_receipts%ROWTYPE;
BEGIN
  IF p_operation_ref !~ '^opref1_[0-9a-f]{64}$'
    OR p_eligibility_digest !~ '^[0-9a-f]{64}$'
    OR p_registry_digest !~ '^[0-9a-f]{64}$'
    OR p_policy_digest !~ '^[0-9a-f]{64}$'
    OR p_owner_mapping_digest !~ '^[0-9a-f]{64}$'
    OR p_project_id !~ '^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
    OR (p_database_id <> '(default)' AND p_database_id !~ '^[a-z][a-z0-9_-]{0,62}$')
    OR NOT omi_memory.is_firestore_legacy_generation_collection(
      p_resource_role, p_collection_id
    )
    OR p_result NOT IN ('disposed', 'already_absent')
    OR p_pre_delete_count NOT BETWEEN 0 AND 100000
    OR (p_result = 'disposed' AND p_pre_delete_count = 0)
    OR (p_result = 'already_absent' AND p_pre_delete_count <> 0)
    OR p_pre_delete_set_digest !~ '^[0-9a-f]{64}$'
    OR p_provider_receipt_digest !~ '^[0-9a-f]{64}$'
    OR p_receipt_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'firestore_legacy_generation_receipt_input_invalid';
  END IF;

  PERFORM 1
  FROM omi_memory.account_terminal_deletion_exports te
  WHERE te.account_id = p_account_id
    AND te.deletion_epoch = p_deletion_epoch
    AND te.control_revision = p_control_revision
  FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'firestore_legacy_generation_receipt_coordinate_denied';
  END IF;

  INSERT INTO omi_memory.account_firestore_legacy_generation_deletion_receipts (
    account_id, deletion_epoch, control_revision, operation_ref, eligibility_digest,
    registry_digest, policy_digest, owner_mapping_digest, project_id, database_id,
    resource_role, collection_id, result, pre_delete_count, pre_delete_set_digest,
    provider_receipt_digest, receipt_digest
  ) VALUES (
    p_account_id, p_deletion_epoch, p_control_revision, p_operation_ref, p_eligibility_digest,
    p_registry_digest, p_policy_digest, p_owner_mapping_digest, p_project_id, p_database_id,
    p_resource_role, p_collection_id, p_result, p_pre_delete_count, p_pre_delete_set_digest,
    p_provider_receipt_digest, p_receipt_digest
  ) ON CONFLICT DO NOTHING;

  SELECT * INTO STRICT v_receipt
  FROM omi_memory.account_firestore_legacy_generation_deletion_receipts r
  WHERE r.account_id = p_account_id
    AND r.deletion_epoch = p_deletion_epoch
    AND r.operation_ref = p_operation_ref
    AND r.resource_role = p_resource_role;

  IF v_receipt.control_revision <> p_control_revision
    OR v_receipt.eligibility_digest <> p_eligibility_digest
    OR v_receipt.registry_digest <> p_registry_digest
    OR v_receipt.policy_digest <> p_policy_digest
    OR v_receipt.owner_mapping_digest <> p_owner_mapping_digest
    OR v_receipt.project_id <> p_project_id
    OR v_receipt.database_id <> p_database_id
    OR v_receipt.collection_id <> p_collection_id
    OR v_receipt.result <> p_result
    OR v_receipt.pre_delete_count <> p_pre_delete_count
    OR v_receipt.pre_delete_set_digest <> p_pre_delete_set_digest
    OR v_receipt.provider_receipt_digest <> p_provider_receipt_digest
    OR v_receipt.receipt_digest <> p_receipt_digest THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'firestore_legacy_generation_receipt_conflict';
  END IF;

  RETURN NEXT v_receipt;
END
$function$;

REVOKE ALL ON FUNCTION omi_memory.is_firestore_legacy_generation_collection(text, text)
  FROM PUBLIC, omi_platform_application, omi_platform_cleanup;
REVOKE ALL ON TABLE omi_memory.account_firestore_legacy_generation_deletion_receipts
  FROM PUBLIC, omi_platform_application, omi_platform_cleanup;
REVOKE ALL ON FUNCTION omi_memory.load_firestore_legacy_generation_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, text, text, text
) FROM PUBLIC, omi_platform_application;
REVOKE ALL ON FUNCTION omi_memory.record_firestore_legacy_generation_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, text, text, text,
  text, bigint, text, text, text
) FROM PUBLIC, omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.load_firestore_legacy_generation_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, text, text, text
) TO omi_platform_cleanup;
GRANT EXECUTE ON FUNCTION omi_memory.record_firestore_legacy_generation_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, text, text, text,
  text, bigint, text, text, text
) TO omi_platform_cleanup;
