import postgres from "postgres";
import { runPostgresMigrations } from "./migrations/runner";
import { expect, test } from "bun:test";
import { randomUUID } from "node:crypto";
import {
  bindFirebaseIdentity,
  type BindingManifest,
} from "../../scripts/bind-firebase-identity";
import { seedProdLocalFirebaseAuthorizationSql } from "../../scripts/prod-local-identity-seed";
import { createPostgresJsTransactionPool } from "./postgresjs";

const url = process.env.OMI_TEST_POSTGRES_URL;
const realTest = url ? test : test.skip;
realTest(
  "binding SQL locks existing authority, preserves replay, and rejects cross-account identity reuse",
  async () => {
    const endpoint = new URL(url!);
    if (endpoint.hostname !== "127.0.0.1" || endpoint.protocol !== "postgres:")
      throw Error("postgres_test_not_loopback_only");
    const owner = postgres(url!, { max: 1 });
    try {
      await owner.unsafe(`DO $roles$ BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='omi_platform_application') THEN CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='omi_platform_cleanup') THEN CREATE ROLE omi_platform_cleanup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='omi_platform_restore') THEN CREATE ROLE omi_platform_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='omi_platform_restore_operator') THEN CREATE ROLE omi_platform_restore_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
    END $roles$;`);
      await runPostgresMigrations(owner);
    } finally {
      await owner.end({ timeout: 5 });
    }
    const pool = createPostgresJsTransactionPool({
      connectionString: url!,
      maxConnections: 1,
    });
    const rollback = new Error("rollback synthetic binding fixture");
    try {
      await expect(
        pool.withTransaction(
          { isolationLevel: "serializable", accessMode: "read write" },
          async (connection) => {
            const uid = `binding-test-${randomUUID()}`;
            const now = () => Math.floor(Date.now() / 1000);
            const m: BindingManifest = {
              projectId: "synthetic-binding-test",
              uid,
              accountId: `account:${uid}`,
              principalId: `principal:${uid}`,
              applicationId: "binding-test-app",
              credentialId: `credential:${uid}`,
              controlRevision: 1,
              controlHash: "1".repeat(64),
              credentialHash: "2".repeat(64),
              grantHash: "3".repeat(64),
              expiresAt: now() + 600,
              reasonRef: "synthetic-real-postgres-test",
            };
            for (const accountId of [m.accountId, `other:${uid}`]) {
              const statements = seedProdLocalFirebaseAuthorizationSql(
                {
                  firebase_project_id: m.projectId,
                  firebase_uid: uid,
                  application_id: m.applicationId,
                  account_id: accountId,
                  principal_id: m.principalId,
                  credential_id: m.credentialId,
                  grant_id: `grant:${uid}`,
                },
                now()
              );
              for (const statement of statements.filter(
                (item) => !item.name.endsWith("_binding")
              ))
                await connection.execute(statement);
            }
            const options = {
              manifest: m,
              token: "synthetic-token",
              now,
              pool: {
                withTransaction: async <T>(
                  _options: unknown,
                  callback: (value: typeof connection) => Promise<T>
                ) => callback(connection),
              },
              verifier: {
                async resolve() {
                  return {
                    firebase_project_id: m.projectId,
                    firebase_uid: uid,
                    authentication_strength: "firebase-id-token" as const,
                    expires_at_epoch_seconds: now() + 900,
                  };
                },
              },
              audit: async () => {},
            };
            expect(await bindFirebaseIdentity(options)).toBe("bound");
            expect(await bindFirebaseIdentity(options)).toBe("unchanged");
            await expect(
              bindFirebaseIdentity({
                ...options,
                manifest: { ...m, accountId: `other:${uid}` },
              })
            ).rejects.toThrow("binding_unavailable_or_conflicting");
            await expect(
              bindFirebaseIdentity({
                ...options,
                manifest: { ...m, grantHash: "f".repeat(64) },
              })
            ).rejects.toThrow("binding_unavailable_or_conflicting");
            const rows = await connection.query({
              name: "binding_test.final",
              text: "SELECT account_id FROM omi_memory.firebase_identity_bindings WHERE firebase_project_id=$1 AND firebase_uid=$2",
              values: [m.projectId, uid],
            });
            expect(rows).toEqual([{ account_id: m.accountId }]);
            throw rollback;
          }
        )
      ).rejects.toBe(rollback);
    } finally {
      await pool.close();
    }
  }
);
