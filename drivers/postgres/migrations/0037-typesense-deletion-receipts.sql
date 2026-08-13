-- P7 retained, content-free receipts for account-filtered Typesense cleanup.
-- The dedicated cleanup role receives named functions only; the table is not
-- application-readable and can never authorize traffic or provider access.

CREATE TABLE omi_memory.account_typesense_deletion_receipts (
  account_id text NOT NULL,
  deletion_epoch bigint NOT NULL CHECK (deletion_epoch >= 0),
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  operation_ref text NOT NULL CHECK (operation_ref ~ '^opref1_[0-9a-f]{64}$'),
  eligibility_digest text NOT NULL CHECK (eligibility_digest ~ '^[0-9a-f]{64}$'),
  registry_digest text NOT NULL CHECK (registry_digest ~ '^[0-9a-f]{64}$'),
  resource_role text NOT NULL CHECK (resource_role IN (
    'legacy_conversations', 'canonical_memory_atoms'
  )),
  collection_name text NOT NULL CHECK (collection_name ~ '^[A-Za-z0-9_-]{1,128}$'),
  result text NOT NULL CHECK (result IN ('disposed', 'already_absent')),
  affected_count bigint NOT NULL CHECK (affected_count BETWEEN 0 AND 100000),
  CHECK (
    (result = 'disposed' AND affected_count > 0)
    OR (result = 'already_absent' AND affected_count = 0)
  ),
  provider_receipt_digest text NOT NULL CHECK (provider_receipt_digest ~ '^[0-9a-f]{64}$'),
  receipt_digest text NOT NULL CHECK (receipt_digest ~ '^[0-9a-f]{64}$'),
  recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, deletion_epoch, operation_ref, resource_role),
  FOREIGN KEY (account_id, deletion_epoch)
    REFERENCES omi_memory.account_terminal_deletion_exports (account_id, deletion_epoch)
);

CREATE FUNCTION omi_memory.load_typesense_deletion_receipt(
  p_account_id text,
  p_control_revision bigint,
  p_deletion_epoch bigint,
  p_operation_ref text,
  p_eligibility_digest text,
  p_registry_digest text,
  p_resource_role text,
  p_collection_name text
)
RETURNS TABLE(
  account_id text,
  deletion_epoch bigint,
  control_revision bigint,
  operation_ref text,
  eligibility_digest text,
  registry_digest text,
  resource_role text,
  collection_name text,
  result text,
  affected_count bigint,
  provider_receipt_digest text,
  receipt_digest text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_receipt omi_memory.account_typesense_deletion_receipts%ROWTYPE;
BEGIN
  IF p_operation_ref !~ '^opref1_[0-9a-f]{64}$'
    OR p_eligibility_digest !~ '^[0-9a-f]{64}$'
    OR p_registry_digest !~ '^[0-9a-f]{64}$'
    OR p_resource_role NOT IN ('legacy_conversations', 'canonical_memory_atoms')
    OR p_collection_name !~ '^[A-Za-z0-9_-]{1,128}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'typesense_receipt_input_invalid';
  END IF;

  PERFORM 1
  FROM omi_memory.account_terminal_deletion_exports te
  WHERE te.account_id = p_account_id
    AND te.deletion_epoch = p_deletion_epoch
    AND te.control_revision = p_control_revision
  FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'typesense_receipt_coordinate_denied';
  END IF;

  SELECT * INTO v_receipt
  FROM omi_memory.account_typesense_deletion_receipts r
  WHERE r.account_id = p_account_id
    AND r.deletion_epoch = p_deletion_epoch
    AND r.operation_ref = p_operation_ref
    AND r.resource_role = p_resource_role;
  IF NOT FOUND THEN RETURN; END IF;

  IF v_receipt.control_revision <> p_control_revision
    OR v_receipt.eligibility_digest <> p_eligibility_digest
    OR v_receipt.registry_digest <> p_registry_digest
    OR v_receipt.collection_name <> p_collection_name THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'typesense_receipt_conflict';
  END IF;

  RETURN QUERY SELECT
    v_receipt.account_id, v_receipt.deletion_epoch, v_receipt.control_revision,
    v_receipt.operation_ref, v_receipt.eligibility_digest, v_receipt.registry_digest,
    v_receipt.resource_role, v_receipt.collection_name, v_receipt.result,
    v_receipt.affected_count, v_receipt.provider_receipt_digest,
    v_receipt.receipt_digest;
END
$function$;

CREATE FUNCTION omi_memory.record_typesense_deletion_receipt(
  p_account_id text,
  p_control_revision bigint,
  p_deletion_epoch bigint,
  p_operation_ref text,
  p_eligibility_digest text,
  p_registry_digest text,
  p_resource_role text,
  p_collection_name text,
  p_result text,
  p_affected_count bigint,
  p_provider_receipt_digest text,
  p_receipt_digest text
)
RETURNS TABLE(
  account_id text,
  deletion_epoch bigint,
  control_revision bigint,
  operation_ref text,
  eligibility_digest text,
  registry_digest text,
  resource_role text,
  collection_name text,
  result text,
  affected_count bigint,
  provider_receipt_digest text,
  receipt_digest text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
DECLARE
  v_receipt omi_memory.account_typesense_deletion_receipts%ROWTYPE;
BEGIN
  IF p_operation_ref !~ '^opref1_[0-9a-f]{64}$'
    OR p_eligibility_digest !~ '^[0-9a-f]{64}$'
    OR p_registry_digest !~ '^[0-9a-f]{64}$'
    OR p_resource_role NOT IN ('legacy_conversations', 'canonical_memory_atoms')
    OR p_collection_name !~ '^[A-Za-z0-9_-]{1,128}$'
    OR p_result NOT IN ('disposed', 'already_absent')
    OR p_affected_count NOT BETWEEN 0 AND 100000
    OR (p_result = 'disposed' AND p_affected_count = 0)
    OR (p_result = 'already_absent' AND p_affected_count <> 0)
    OR p_provider_receipt_digest !~ '^[0-9a-f]{64}$'
    OR p_receipt_digest !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'typesense_receipt_input_invalid';
  END IF;

  PERFORM 1
  FROM omi_memory.account_terminal_deletion_exports te
  WHERE te.account_id = p_account_id
    AND te.deletion_epoch = p_deletion_epoch
    AND te.control_revision = p_control_revision
  FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'typesense_receipt_coordinate_denied';
  END IF;

  INSERT INTO omi_memory.account_typesense_deletion_receipts (
    account_id, deletion_epoch, control_revision, operation_ref,
    eligibility_digest, registry_digest, resource_role, collection_name,
    result, affected_count, provider_receipt_digest, receipt_digest
  ) VALUES (
    p_account_id, p_deletion_epoch, p_control_revision, p_operation_ref,
    p_eligibility_digest, p_registry_digest, p_resource_role, p_collection_name,
    p_result, p_affected_count, p_provider_receipt_digest, p_receipt_digest
  ) ON CONFLICT DO NOTHING;

  SELECT * INTO STRICT v_receipt
  FROM omi_memory.account_typesense_deletion_receipts r
  WHERE r.account_id = p_account_id
    AND r.deletion_epoch = p_deletion_epoch
    AND r.operation_ref = p_operation_ref
    AND r.resource_role = p_resource_role;

  IF v_receipt.control_revision <> p_control_revision
    OR v_receipt.eligibility_digest <> p_eligibility_digest
    OR v_receipt.registry_digest <> p_registry_digest
    OR v_receipt.collection_name <> p_collection_name
    OR v_receipt.result <> p_result
    OR v_receipt.affected_count <> p_affected_count
    OR v_receipt.provider_receipt_digest <> p_provider_receipt_digest
    OR v_receipt.receipt_digest <> p_receipt_digest THEN
    RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'typesense_receipt_conflict';
  END IF;

  RETURN QUERY SELECT
    v_receipt.account_id, v_receipt.deletion_epoch, v_receipt.control_revision,
    v_receipt.operation_ref, v_receipt.eligibility_digest, v_receipt.registry_digest,
    v_receipt.resource_role, v_receipt.collection_name, v_receipt.result,
    v_receipt.affected_count, v_receipt.provider_receipt_digest,
    v_receipt.receipt_digest;
END
$function$;

REVOKE ALL ON TABLE omi_memory.account_typesense_deletion_receipts
  FROM PUBLIC, omi_platform_application, omi_platform_cleanup;
REVOKE ALL ON FUNCTION omi_memory.load_typesense_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text
) FROM PUBLIC, omi_platform_application;
REVOKE ALL ON FUNCTION omi_memory.record_typesense_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, bigint, text, text
) FROM PUBLIC, omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.load_typesense_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text
) TO omi_platform_cleanup;
GRANT EXECUTE ON FUNCTION omi_memory.record_typesense_deletion_receipt(
  text, bigint, bigint, text, text, text, text, text, text, bigint, text, text
) TO omi_platform_cleanup;
