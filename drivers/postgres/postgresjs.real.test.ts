import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { randomUUID } from "node:crypto";
import postgres, { type Sql } from "postgres";

import { createAuthorizedLedgerWriteContextIssuer } from "../../apps/service/auth/authorized-context-internal";
import { authoritativeAppendRequestDigest, type AuthoritativeLedgerAppend } from "../../apps/service/stores/authoritative-ledger-repository";
import { prepareDerivation, type AtomicGraphTransition } from "../../core/ledger";
import { createPostgresSuccessfulEmptyLedgerRepository } from "./authoritative-ledger-repository";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlStatement } from "./connection";
import { POSTGRES_MIGRATIONS } from "./migrations/manifest";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool, type CloseablePostgresTransactionPool } from "./postgresjs";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const explicitTestUrl = process.env["OMI_TEST_POSTGRES_URL"];
const realTest = explicitTestUrl ? describe : describe.skip;

realTest("PostgreSQL 18.4 real adapter qualification scaffold", () => {
  let ownerSql: Sql<Record<string, never>>;
  let pool: CloseablePostgresTransactionPool;

  beforeAll(() => {
    if (!explicitTestUrl) throw new Error("OMI_TEST_POSTGRES_URL is required");
    const parsed = new URL(explicitTestUrl);
    if (parsed.hostname !== "127.0.0.1" || parsed.protocol !== "postgres:") {
      throw new Error("postgres_test_not_loopback_only");
    }
    ownerSql = postgres(explicitTestUrl, { max: 2, prepare: true });
    pool = createPostgresJsTransactionPool({ connectionString: explicitTestUrl, maxConnections: 1 });
  });

  afterAll(async () => {
    await pool?.close();
    await ownerSql?.end({ timeout: 5 });
  });

  test("runs the pinned server, creates only the test role, and reapplies all migrations as no-ops", async () => {
    const version = await ownerSql.unsafe<{ server_version_num: string }[]>("SHOW server_version_num");
    expect(Number(version[0]?.server_version_num)).toBe(180004);
    expect(process.env["OMI_TEST_POSTGRES_IMAGE"]).toBe(
      "postgres:18.4-bookworm@sha256:882236b897e39051d2368c5ccc6cda944904723506b2dfc97f2a8f5bc9afa382",
    );
    await ownerSql.unsafe(`
      DO $role$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omi_platform_application') THEN
          CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
        END IF;
      END
      $role$
    `, [], { prepare: false });

    const first = await runPostgresMigrations(ownerSql);
    const second = await runPostgresMigrations(ownerSql);
    expect([...first.appliedVersions, ...first.skippedVersions]).toEqual(
      POSTGRES_MIGRATIONS.map((entry) => entry.version),
    );
    expect(second.appliedVersions).toEqual([]);
    expect(second.skippedVersions).toEqual(POSTGRES_MIGRATIONS.map((entry) => entry.version));
  }, 120_000);

  test("one reserved connection owns the transaction and SET LOCAL clears after rollback", async () => {
    let firstBackend: number | undefined;
    await expect(pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        const rows = await connection.query<{ backend_pid: number }>({
          name: "qualification.backend_and_local",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        set_config('omi.account_id', $1, true) AS local_account`,
          values: ["account:qualification"],
        });
        firstBackend = rows[0]?.backend_pid;
        throw new Error("force rollback");
      },
    )).rejects.toThrow("force rollback");

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection: CheckedOutPostgresConnection) => {
        const rows = await connection.query<{ backend_pid: number; local_account: string | null }>({
          name: "qualification.local_cleared",
          text: `SELECT pg_backend_pid() AS backend_pid,
                        nullif(current_setting('omi.account_id', true), '') AS local_account`,
          values: [],
        });
        if (firstBackend === undefined) throw new Error("missing qualification backend");
        expect(rows[0]?.backend_pid).toBe(firstBackend);
        expect(rows[0]?.local_account).toBeNull();
      },
    );
  });

  test("application-role successful-empty kernel commits, replays, conflicts, rejects stale parent, and rolls back", async () => {
    const suffix = randomUUID();
    const accountId = `account:pg-kernel:${suffix}`;
    const principalId = `principal:pg-kernel:${suffix}`;
    const applicationId = "app:qualification";
    const credentialId = `credential:${suffix}`;
    const grantId = `grant:${suffix}`;
    const controlHash = "1".repeat(64);
    const credentialHash = "2".repeat(64);
    const grantHash = "3".repeat(64);
    const now = Math.floor(Date.now() / 1_000);

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(
        "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)",
        [accountId],
      );
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 17, 'new', 12, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)`, [accountId, controlHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 17, 12, 17)`, [accountId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 4, 'firebase', 'active', 'firebase-id-token',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)`,
      [accountId, principalId, applicationId, credentialId, now + 7_200, credentialHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 4)`, [accountId, applicationId, credentialId]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, grantId, grantHash]);
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 9)`,
      [accountId, applicationId, credentialId, grantId]);
    });

    const authorityRow: AuthorityStateRow = {
      account_id: accountId,
      principal_id: principalId,
      application_id: applicationId,
      credential_id: credentialId,
      credential_generation: 4,
      capability: "memories.write",
      grant_id: grantId,
      grant_version: 9,
      account_epoch: 12,
      control_conflict_reason: null,
      control_conflict_at_revision: null,
      destination_activation_epoch: 12,
      destination_activation_revision: 17,
      lifecycle_state: "active",
      deletion_epoch: null,
      account_generation: "new",
      credential_lifecycle: "active",
      grant_lifecycle: "active",
      grant_enabled: true,
      authentication_strength: "firebase-id-token",
      credential_expires_at_epoch_seconds: now + 7_200,
      control_revision: 17,
      control_content_hash: controlHash,
      credential_content_hash: credentialHash,
      grant_content_hash: grantHash,
      db_now_epoch_seconds: now,
    };
    const context = createAuthorizedLedgerWriteContextIssuer().issue({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: principalId,
      account_id: accountId,
      application_id: applicationId,
      credential_id: credentialId,
      credential_generation: 4,
      capability: "memories.write",
      grant_id: grantId,
      grant_version: 9,
      account_epoch: 12,
      destination_activation_revision: 17,
      lifecycle_state: "active",
      deletion_epoch: null,
      authentication_strength: "firebase-id-token",
      issued_at_epoch_seconds: now - 60,
      expires_at_epoch_seconds: now + 3_600,
      authorization_state_digest: authorizationStateDigest(authorityRow),
    }, now);

    let lastRepositoryStatement = "none";
    let lastProviderCode = "none";
    let lastProviderConstraint = "none";
    const appRolePool: PostgresTransactionPool = Object.freeze({
      withTransaction: async <Result>(options: Parameters<PostgresTransactionPool["withTransaction"]>[0], callback: (connection: CheckedOutPostgresConnection) => Promise<Result>) =>
        pool.withTransaction(options, async (connection) => {
          await connection.query({
            name: "qualification.set_application_role",
            text: "SET LOCAL ROLE omi_platform_application",
            values: [],
          });
          const roles = await connection.query<{ current_user: string }>({
            name: "qualification.assert_application_role",
            text: "SELECT current_user",
            values: [],
          });
          expect(roles).toEqual([{ current_user: "omi_platform_application" }]);
          const tracked: CheckedOutPostgresConnection = Object.freeze({
            connectionIdentity: connection.connectionIdentity,
            query: async <Row extends Record<string, unknown>>(statement: Parameters<CheckedOutPostgresConnection["query"]>[0]) => {
              lastRepositoryStatement = statement.name;
              return connection.query<Row>(statement);
            },
            execute: async (statement: SqlStatement) => {
              lastRepositoryStatement = statement.name;
              try {
                return await connection.execute(statement);
              } catch (error) {
                const code = error && typeof error === "object" ? Reflect.get(error, "code") : null;
                const constraint = error && typeof error === "object" ? Reflect.get(error, "constraint_name") : null;
                lastProviderCode = typeof code === "string" ? code : "unknown";
                lastProviderConstraint = typeof constraint === "string" ? constraint : "unknown";
                throw error;
              }
            },
          });
          return callback(tracked);
        }),
    });
    const repository = createPostgresSuccessfulEmptyLedgerRepository({ pool: appRolePool });
    const append = (commitId: string, key: string, parent: string | null): AuthoritativeLedgerAppend => {
      const transition: AtomicGraphTransition = {
        placement: { offline_experiment: true, allocations: {}, results: [] },
        derivation: prepareDerivation({
          attempt_id: `attempt:${commitId}`,
          commit_id: commitId,
          owner_account_id: accountId,
          parent_commit: parent,
          idempotency_key: key,
          input_revisions: [],
          output_revisions: [],
          versions: {
            strategy_version: "qualification-v1", model_version: "none", prompt_version: "none",
            policy_version: "qualification-v1", code_version: "qualification-v1",
            schema_version: "qualification-v1", tokenizer_version: "none", tool_version: "qualification-v1",
          },
          success_kind: "successful_empty",
        }),
        revisions: [], adjacency: [], artifacts: [],
      };
      const origin = { kind: "non_formation" as const, reason: "repair" as const };
      return {
        append_attempt: {
          idempotency_key: key,
          expected_parent_commit: parent,
          request_digest: authoritativeAppendRequestDigest(transition, origin),
        },
        origin,
        transition,
      };
    };

    const first = append(`commit:${suffix}:one`, `append:${suffix}:same`, null);
    try {
      expect(await repository.append(context, first)).toEqual({
        kind: "committed", commit_id: first.transition.derivation.commit.commit_id, sequence: 1,
      });
    } catch (error) {
      const code = error && typeof error === "object" && "code" in error
        ? String(Reflect.get(error, "code")) : "assertion_or_unknown";
      throw new Error(`kernel_real_failure_at:${lastRepositoryStatement}:${lastProviderCode}:${lastProviderConstraint}:${code}`);
    }
    await expect(repository.append(context, first)).resolves.toEqual({
      kind: "replayed", commit_id: first.transition.derivation.commit.commit_id, sequence: 1,
    });
    const changed = append(`commit:${suffix}:changed`, first.append_attempt.idempotency_key, null);
    await expect(repository.append(context, changed)).resolves.toEqual({ kind: "idempotency_conflict" });
    const stale = append(`commit:${suffix}:stale`, `append:${suffix}:stale`, null);
    await expect(repository.append(context, stale)).resolves.toEqual({ kind: "stale_parent" });

    const persisted = await ownerSql.unsafe<{
      attempts: number; commits: number; receipts: number; head_sequence: string;
    }[]>(`
      SELECT
        (SELECT count(*)::int FROM omi_memory.memory_derivation_attempts WHERE account_id = $1) AS attempts,
        (SELECT count(*)::int FROM omi_memory.memory_derivation_commits WHERE account_id = $1) AS commits,
        (SELECT count(*)::int FROM omi_memory.memory_idempotency_receipts WHERE account_id = $1) AS receipts,
        (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
    `, [accountId]);
    expect([...persisted]).toEqual([{ attempts: 1, commits: 1, receipts: 1, head_sequence: "1" }]);

    for (const forbiddenSql of [
      "CREATE TABLE omi_memory.qualification_forbidden (id integer)",
      "DELETE FROM omi_memory.memory_derivation_attempts WHERE account_id = $1",
      "UPDATE omi_memory.memory_derivation_attempts SET success_kind = 'success' WHERE account_id = $1",
    ]) {
      await expect(ownerSql.begin(async (transaction) => {
        await transaction.unsafe("SET LOCAL ROLE omi_platform_application");
        await transaction.unsafe(forbiddenSql, forbiddenSql.includes("$1") ? [accountId] : []);
      })).rejects.toMatchObject({ code: "42501" });
    }

    try {
      await ownerSql.unsafe(`
        CREATE OR REPLACE FUNCTION omi_memory.qualification_reject_kernel_commit()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'qualification injected rollback'; END
        $$;
        DROP TRIGGER IF EXISTS reject_kernel_commit ON omi_memory.memory_derivation_commits;
        CREATE TRIGGER reject_kernel_commit
        AFTER INSERT ON omi_memory.memory_derivation_commits
        FOR EACH ROW EXECUTE FUNCTION omi_memory.qualification_reject_kernel_commit()
      `, [], { prepare: false });
      const rollback = append(
        `commit:${suffix}:rollback`,
        `append:${suffix}:rollback`,
        first.transition.derivation.commit.commit_id,
      );
      await expect(repository.append(context, rollback)).rejects.toMatchObject({ code: "persistence_failed" });
      const rolledBack = await ownerSql.unsafe<{ attempts: number; commits: number; receipts: number; head_sequence: string }[]>(`
        SELECT
          (SELECT count(*)::int FROM omi_memory.memory_derivation_attempts WHERE account_id = $1) AS attempts,
          (SELECT count(*)::int FROM omi_memory.memory_derivation_commits WHERE account_id = $1) AS commits,
          (SELECT count(*)::int FROM omi_memory.memory_idempotency_receipts WHERE account_id = $1) AS receipts,
          (SELECT sequence::text FROM omi_memory.memory_graph_heads WHERE account_id = $1) AS head_sequence
      `, [accountId]);
      expect([...rolledBack]).toEqual([{ attempts: 1, commits: 1, receipts: 1, head_sequence: "1" }]);
    } finally {
      await ownerSql.unsafe(`
        DROP TRIGGER IF EXISTS reject_kernel_commit ON omi_memory.memory_derivation_commits;
        DROP FUNCTION IF EXISTS omi_memory.qualification_reject_kernel_commit()
      `, [], { prepare: false }).catch(() => undefined);
    }

    await ownerSql.begin(async (transaction) => {
      await transaction.unsafe(`INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 4, 'memories.write', $4, 10, 'revoked', false,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)`,
      [accountId, applicationId, credentialId, grantId, "4".repeat(64)]);
      await transaction.unsafe(`UPDATE omi_memory.application_grant_heads
        SET grant_version = 10, updated_at = transaction_timestamp()
        WHERE account_id = $1 AND application_id = $2 AND credential_id = $3
          AND credential_generation = 4 AND capability = 'memories.write'`,
      [accountId, applicationId, credentialId]);
    });
    await expect(repository.append(context, first)).resolves.toEqual({
      kind: "authorization_denied", reason: "grant_inactive",
    });
  }, 120_000);
});
