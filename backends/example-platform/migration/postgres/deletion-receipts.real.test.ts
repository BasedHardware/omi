import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { createHash, randomUUID } from "node:crypto";
import postgres, { type Sql } from "postgres";

import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import { createPostgresJsTransactionPool, type CloseablePostgresTransactionPool } from
  "../../drivers/postgres/postgresjs";
import { runPostgresMigrations } from "../../drivers/postgres/migrations/runner";
import { createPostgresDeletionCleanupParticipant } from
  "./account-deletion-cleanup-participant";
import { createPostgresFirestoreLegacyGenerationReceiptRepository } from
  "./firestore-legacy-generation-receipt-repository";
import { createPostgresGcsDeletionReceiptRepository } from
  "./gcs-deletion-receipt-repository";
import { createPostgresPineconeDeletionReceiptRepository } from
  "./pinecone-deletion-receipt-repository";
import { createPostgresTypesenseDeletionReceiptRepository } from
  "./typesense-deletion-receipt-repository";

const explicitTestUrl = process.env["OMI_TEST_POSTGRES_URL"];
const realTest = explicitTestUrl ? describe : describe.skip;

realTest("PostgreSQL deletion-receipt and cleanup-participant qualification", () => {
  let ownerSql: Sql<Record<string, never>>;
  let pool: CloseablePostgresTransactionPool;

  beforeAll(async () => {
    if (!explicitTestUrl) throw new Error("OMI_TEST_POSTGRES_URL is required");
    const parsed = new URL(explicitTestUrl);
    if (parsed.hostname !== "127.0.0.1" || parsed.protocol !== "postgres:") {
      throw new Error("postgres_test_not_loopback_only");
    }
    ownerSql = postgres(explicitTestUrl, { max: 2, prepare: true });
    pool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 1 });
    await ownerSql.unsafe(`
      DO $role$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_application') THEN
          CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_cleanup') THEN
          CREATE ROLE omi_platform_cleanup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_restore') THEN
          CREATE ROLE omi_platform_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_restore_operator') THEN
          CREATE ROLE omi_platform_restore_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
      END
      $role$
    `, [], { prepare: false });
    await runPostgresMigrations(ownerSql);
  });

  afterAll(async () => {
    await pool?.close();
    await ownerSql?.end({ timeout: 5 });
  });

  test("cleanup role scans, atomically disposes, receipts, rolls back, and retains tombstones", async () => {
    const suffix = randomUUID();
    const accountId = `account:cleanup:${suffix}`;
    const inputId = `fwi1_${sha256CanonicalContent({ suffix, input: true })}`;
    const jobId = `cleanup-job:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: true })}`;
    const eligibility = sha256CanonicalContent({ suffix, eligibility: true });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe("INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 7, 'new', 3, 'deleted', 11, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "a".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 7, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 11, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 7, $2)`,
      [accountId, "b".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.memory_formation_work_inputs
        (account_id, staged_input_id, job_id, input_version, account_epoch,
         accepted_work_digest, input_frontier, input_digest, execution_contract_digest,
         snapshot_digest, snapshot_version, snapshot_json, stage_request_digest, content_hash)
        VALUES ($1, $2, $3, 'formation-work-staged-input-v1', 3, $4, '0', $5, $6,
                $7, 'formation-input-snapshot-v1', '{}'::jsonb, $8, $9)`, [
        accountId, inputId, jobId, "c".repeat(64), "d".repeat(64), "e".repeat(64),
        "f".repeat(64), "1".repeat(64), "2".repeat(64),
      ]);
    });

    const cleanup = createPostgresDeletionCleanupParticipant(pool);
    await expect(cleanup.withHeldDatabaseFence(
      { account_id: accountId, control_revision: 7, deletion_epoch: 11 },
      operationRef,
      eligibility,
      async (session) => {
        const before = await session.scanOwned();
        expect(before.find((row) => row.surface === "staged_results")?.remaining_count).toBe(1);
        const disposed = await session.dispose(["durable_work", "staged_results"]);
        expect(disposed.map((row) => [row.surface, row.result])).toEqual([
          ["durable_work", "already_absent"], ["staged_results", "disposed"],
        ]);
        const replay = await session.dispose(["durable_work", "staged_results"]);
        expect(replay).toEqual(disposed);
        const after = await session.scanOwned();
        expect(after.find((row) => row.surface === "staged_results")?.remaining_count).toBe(0);
        throw new Error("qualification rollback after cleanup");
      },
    )).rejects.toMatchObject({ code: "persistence_failed" });

    let counts = await ownerSql.unsafe<{ inputs: number; receipts: number }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.memory_formation_work_inputs WHERE account_id = $1) inputs,
      (SELECT count(*)::int FROM omi_memory.account_deletion_surface_receipts WHERE account_id = $1) receipts`,
    [accountId]);
    expect([...counts]).toEqual([{ inputs: 1, receipts: 0 }]);

    await cleanup.withHeldDatabaseFence(
      { account_id: accountId, control_revision: 7, deletion_epoch: 11 },
      operationRef,
      eligibility,
      async (session) => {
        await session.dispose(["durable_work", "staged_results"]);
      },
    );
    counts = await ownerSql.unsafe<{ inputs: number; receipts: number }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.memory_formation_work_inputs WHERE account_id = $1) inputs,
      (SELECT count(*)::int FROM omi_memory.account_deletion_surface_receipts WHERE account_id = $1) receipts`,
    [accountId]);
    expect([...counts]).toEqual([{ inputs: 0, receipts: 2 }]);
    const safety = await ownerSql.unsafe<{ controls: number; exports: number }[]>(`SELECT
      (SELECT count(*)::int FROM omi_memory.account_control_revisions WHERE account_id = $1) controls,
      (SELECT count(*)::int FROM omi_memory.account_terminal_deletion_exports WHERE account_id = $1) exports`,
    [accountId]);
    expect([...safety]).toEqual([{ controls: 1, exports: 1 }]);

    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe("SELECT * FROM omi_memory.scan_deleted_account_surface('staged_results')");
    })).rejects.toMatchObject({ code: "42501" });
    await expect(cleanup.withHeldDatabaseFence(
      { account_id: accountId, control_revision: 6, deletion_epoch: 11 },
      `opref1_${"9".repeat(64)}`,
      eligibility,
      async () => undefined,
    )).rejects.toMatchObject({ code: "terminal_coordinate_denied" });
  }, 120_000);

  test("Typesense cleanup receipts are retained, exact, replayable, and cleanup-role only", async () => {
    const suffix = randomUUID();
    const accountId = `account:typesense-receipt:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: true })}`;
    const eligibilityDigest = sha256CanonicalContent({ suffix, eligibility: true });
    const registryDigest = sha256CanonicalContent({ suffix, registry: true });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 7, 'new', 3, 'deleted', 11, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "a".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 7, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 11, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 7, $2)`,
      [accountId, "b".repeat(64)]);
    });

    const receiptCore = Object.freeze({
      version: "typesense-deletion-receipt-key-v1" as const,
      account_id: accountId,
      control_revision: 7,
      deletion_epoch: 11,
      operation_ref: operationRef,
      eligibility_digest: eligibilityDigest,
      registry_digest: registryDigest,
      role: "legacy_conversations" as const,
      collection_name: "conversations",
      result: "disposed" as const,
      affected_count: 2,
      provider_receipt_digest: "c".repeat(64),
    });
    const storedReceipt = Object.freeze({
      ...receiptCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "typesense-deletion-stored-receipt-v1",
        receipt: receiptCore,
      })).digest("hex"),
    });
    const repository = createPostgresTypesenseDeletionReceiptRepository(pool);
    const key = Object.freeze({
      version: storedReceipt.version,
      account_id: storedReceipt.account_id,
      control_revision: storedReceipt.control_revision,
      deletion_epoch: storedReceipt.deletion_epoch,
      operation_ref: storedReceipt.operation_ref,
      eligibility_digest: storedReceipt.eligibility_digest,
      registry_digest: storedReceipt.registry_digest,
      role: storedReceipt.role,
      collection_name: storedReceipt.collection_name,
    });
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: storedReceipt });

    const changedCore = Object.freeze({
      ...receiptCore,
      provider_receipt_digest: "d".repeat(64),
    });
    const changed = Object.freeze({
      ...changedCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "typesense-deletion-stored-receipt-v1",
        receipt: changedCore,
      })).digest("hex"),
    });
    await expect(repository.record(changed)).rejects.toMatchObject({ code: "receipt_conflict" });

    const counts = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count
      FROM omi_memory.account_typesense_deletion_receipts
      WHERE account_id = $1`, [accountId]);
    expect([...counts]).toEqual([{ count: 1 }]);
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_typesense_deletion_receipts WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.load_typesense_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8)",
        [
          accountId, 7, 11, operationRef, eligibilityDigest, registryDigest,
          "legacy_conversations", "conversations",
        ],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 120_000);

  test("Pinecone cleanup receipts bind all vector coordinates and remain cleanup-role only", async () => {
    const suffix = randomUUID();
    const accountId = `account:pinecone-receipt:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: "pinecone" })}`;
    const eligibilityDigest = sha256CanonicalContent({ suffix, eligibility: "pinecone" });
    const registryDigest = sha256CanonicalContent({ suffix, registry: "pinecone" });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 8, 'new', 4, 'deleted', 12, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "1".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 8, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 12, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 8, $2)`,
      [accountId, "2".repeat(64)]);
    });

    const receiptCore = Object.freeze({
      version: "pinecone-deletion-receipt-key-v1" as const,
      account_id: accountId,
      control_revision: 8,
      deletion_epoch: 12,
      operation_ref: operationRef,
      eligibility_digest: eligibilityDigest,
      registry_digest: registryDigest,
      role: "memory_vectors" as const,
      index_name: "memories-backend" as const,
      namespace_name: "ns2" as const,
      result: "disposed" as const,
      pre_delete_count: 3,
      pre_delete_content_hash: "3".repeat(64),
      provider_receipt_digest: "4".repeat(64),
    });
    const storedReceipt = Object.freeze({
      ...receiptCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "pinecone-deletion-stored-receipt-v1",
        receipt: receiptCore,
      })).digest("hex"),
    });
    const repository = createPostgresPineconeDeletionReceiptRepository(pool);
    const key = Object.freeze({
      version: storedReceipt.version,
      account_id: storedReceipt.account_id,
      control_revision: storedReceipt.control_revision,
      deletion_epoch: storedReceipt.deletion_epoch,
      operation_ref: storedReceipt.operation_ref,
      eligibility_digest: storedReceipt.eligibility_digest,
      registry_digest: storedReceipt.registry_digest,
      role: storedReceipt.role,
      index_name: storedReceipt.index_name,
      namespace_name: storedReceipt.namespace_name,
    });
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: storedReceipt });

    const changedCore = Object.freeze({ ...receiptCore, provider_receipt_digest: "5".repeat(64) });
    const changed = Object.freeze({
      ...changedCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "pinecone-deletion-stored-receipt-v1", receipt: changedCore,
      })).digest("hex"),
    });
    await expect(repository.record(changed)).rejects.toMatchObject({ code: "receipt_conflict" });

    const counts = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count FROM omi_memory.account_pinecone_deletion_receipts
      WHERE account_id = $1`, [accountId]);
    expect([...counts]).toEqual([{ count: 1 }]);
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_pinecone_deletion_receipts WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.load_pinecone_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        [
          accountId, 8, 12, operationRef, eligibilityDigest, registryDigest,
          "memory_vectors", "memories-backend", "ns2",
        ],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 120_000);

  test("GCS cleanup receipts bind policy and prefix coordinates and remain cleanup-role only", async () => {
    const suffix = randomUUID();
    const accountId = `account:gcs-receipt:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: "gcs" })}`;
    const eligibilityDigest = sha256CanonicalContent({ suffix, eligibility: "gcs" });
    const registryDigest = sha256CanonicalContent({ suffix, registry: "gcs" });
    const policyDigest = sha256CanonicalContent({ suffix, policy: "gcs" });
    const prefixDigest = sha256CanonicalContent({ suffix, prefix: "gcs" });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 9, 'new', 5, 'deleted', 13, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "1".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 9, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 13, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 9, $2)`,
      [accountId, "2".repeat(64)]);
    });

    const receiptCore = Object.freeze({
      version: "gcs-deletion-receipt-key-v1" as const,
      account_id: accountId,
      control_revision: 9,
      deletion_epoch: 13,
      operation_ref: operationRef,
      eligibility_digest: eligibilityDigest,
      registry_digest: registryDigest,
      policy_digest: policyDigest,
      owner_mapping_digest: sha256CanonicalContent({ suffix, owner_mapping: "gcs" }),
      role: "private_sync_chunks" as const,
      bucket_name: "omi-private-cloud-sync",
      prefix_digest: prefixDigest,
      result: "disposed" as const,
      pre_delete_count: 3,
      pre_delete_set_digest: "3".repeat(64),
      provider_receipt_digest: "4".repeat(64),
    });
    const storedReceipt = Object.freeze({
      ...receiptCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "gcs-deletion-stored-receipt-v1",
        receipt: receiptCore,
      })).digest("hex"),
    });
    const repository = createPostgresGcsDeletionReceiptRepository(pool);
    const key = Object.freeze({
      version: storedReceipt.version,
      account_id: storedReceipt.account_id,
      control_revision: storedReceipt.control_revision,
      deletion_epoch: storedReceipt.deletion_epoch,
      operation_ref: storedReceipt.operation_ref,
      eligibility_digest: storedReceipt.eligibility_digest,
      registry_digest: storedReceipt.registry_digest,
      policy_digest: storedReceipt.policy_digest,
      owner_mapping_digest: storedReceipt.owner_mapping_digest,
      role: storedReceipt.role,
      bucket_name: storedReceipt.bucket_name,
      prefix_digest: storedReceipt.prefix_digest,
    });
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: storedReceipt });

    const changedCore = Object.freeze({ ...receiptCore, provider_receipt_digest: "5".repeat(64) });
    const changed = Object.freeze({
      ...changedCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "gcs-deletion-stored-receipt-v1", receipt: changedCore,
      })).digest("hex"),
    });
    await expect(repository.record(changed)).rejects.toMatchObject({ code: "receipt_conflict" });

    const counts = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count FROM omi_memory.account_gcs_deletion_receipts
      WHERE account_id = $1`, [accountId]);
    expect([...counts]).toEqual([{ count: 1 }]);
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_gcs_deletion_receipts WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.load_gcs_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
        [
          accountId, 9, 13, operationRef, eligibilityDigest, registryDigest,
          policyDigest, storedReceipt.owner_mapping_digest, "private_sync_chunks",
          "omi-private-cloud-sync", prefixDigest,
        ],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 120_000);

  test("Firestore legacy-generation receipts bind source registry and remain cleanup-role only", async () => {
    const suffix = randomUUID();
    const accountId = `account:firestore-legacy-generation-receipt:${suffix}`;
    const operationRef = `opref1_${sha256CanonicalContent({ suffix, operation: "firestore" })}`;
    const eligibilityDigest = sha256CanonicalContent({ suffix, eligibility: "firestore" });
    const registryDigest = sha256CanonicalContent({ suffix, registry: "firestore" });
    const policyDigest = sha256CanonicalContent({ suffix, policy: "firestore" });
    const ownerMappingDigest = sha256CanonicalContent({ suffix, owner_mapping: "firestore" });
    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)", [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
        (account_id, control_revision, account_generation, account_epoch, lifecycle_state,
         deletion_epoch, observed_at, record_schema_version, record_json, content_hash)
        VALUES ($1, 10, 'new', 6, 'deleted', 14, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, "1".repeat(64)]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
        (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 10, NULL, NULL)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_terminal_deletion_exports
        (account_id, deletion_epoch, export_contract_version, transitioned_at,
         account_generation, terminal_lifecycle_state, stranded_data_present,
         control_revision, content_hash)
        VALUES ($1, 14, 'terminal-v1', transaction_timestamp(), 'new', 'deleted', false, 10, $2)`,
      [accountId, "2".repeat(64)]);
    });

    const receiptCore = Object.freeze({
      version: "firestore-legacy-generation-receipt-key-v1" as const,
      account_id: accountId,
      control_revision: 10,
      deletion_epoch: 14,
      operation_ref: operationRef,
      eligibility_digest: eligibilityDigest,
      registry_digest: registryDigest,
      policy_digest: policyDigest,
      owner_mapping_digest: ownerMappingDigest,
      project_id: "based-hardware",
      database_id: "(default)",
      role: "legacy_user_tree" as const,
      collection_id: "users",
      result: "disposed" as const,
      pre_delete_count: 3,
      pre_delete_set_digest: "3".repeat(64),
      provider_receipt_digest: "4".repeat(64),
    });
    const storedReceipt = Object.freeze({
      ...receiptCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "firestore-legacy-generation-stored-receipt-v1",
        receipt: receiptCore,
      })).digest("hex"),
    });
    const repository = createPostgresFirestoreLegacyGenerationReceiptRepository(pool);
    const key = Object.freeze({
      version: storedReceipt.version,
      account_id: storedReceipt.account_id,
      control_revision: storedReceipt.control_revision,
      deletion_epoch: storedReceipt.deletion_epoch,
      operation_ref: storedReceipt.operation_ref,
      eligibility_digest: storedReceipt.eligibility_digest,
      registry_digest: storedReceipt.registry_digest,
      policy_digest: storedReceipt.policy_digest,
      owner_mapping_digest: storedReceipt.owner_mapping_digest,
      project_id: storedReceipt.project_id,
      database_id: storedReceipt.database_id,
      role: storedReceipt.role,
      collection_id: storedReceipt.collection_id,
    });
    await expect(repository.load(key)).resolves.toEqual({ kind: "missing" });
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.record(storedReceipt)).resolves.toEqual(storedReceipt);
    await expect(repository.load(key)).resolves.toEqual({ kind: "found", receipt: storedReceipt });

    const changedCore = Object.freeze({ ...receiptCore, provider_receipt_digest: "5".repeat(64) });
    const changed = Object.freeze({
      ...changedCore,
      receipt_digest: createHash("sha256").update(JSON.stringify({
        contract_version: "firestore-legacy-generation-stored-receipt-v1",
        receipt: changedCore,
      })).digest("hex"),
    });
    await expect(repository.record(changed)).rejects.toMatchObject({ code: "receipt_conflict" });

    const counts = await ownerSql.unsafe<{ count: number }[]>(`
      SELECT count(*)::int AS count
      FROM omi_memory.account_firestore_legacy_generation_deletion_receipts
      WHERE account_id = $1`, [accountId]);
    expect([...counts]).toEqual([{ count: 1 }]);
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.account_firestore_legacy_generation_deletion_receipts WHERE account_id = $1",
        [accountId],
      );
    })).rejects.toMatchObject({ code: "42501" });
    await expect(ownerSql.begin(async (transaction) => {
      await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
      await transaction.unsafe(
        "SELECT * FROM omi_memory.load_firestore_legacy_generation_deletion_receipt($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
        [
          accountId, 10, 14, operationRef, eligibilityDigest, registryDigest,
          policyDigest, ownerMappingDigest, "based-hardware", "(default)",
          "legacy_user_tree", "users",
        ],
      );
    })).rejects.toMatchObject({ code: "42501" });
  }, 120_000);

});
