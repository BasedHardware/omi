import { expect, test } from "bun:test";
import postgres from "postgres";
import { createHash, randomUUID } from "node:crypto";
import { runPostgresMigrations } from "./migrations/runner";
import { createPostgresJsTransactionPool } from "./postgresjs";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseTasksRuntime } from "./firebase-tasks-runtime";
import { seedProdLocalFirebaseAuthorizationSql } from "../../scripts/prod-local-identity-seed";

const url = process.env.OMI_TEST_POSTGRES_URL;
const realTest = url ? test : test.skip;
realTest(
  "real task routes persist revisions/receipts and enforce grant, owner, cursor and epoch fences",
  async () => {
    const endpoint = new URL(url!);
    if (endpoint.hostname !== "127.0.0.1" || endpoint.protocol !== "postgres:")
      throw Error("postgres_test_not_loopback_only");
    const owner = postgres(url!, { max: 1 });
    const pool = createPostgresJsTransactionPool({
      connectionString: url!,
      maxConnections: 2,
    });
    const suffix = randomUUID(),
      generation = createHash("sha256").update(suffix).digest("hex"),
      now = () => Math.floor(Date.now() / 1000);
    const project = "synthetic-task-project",
      app = "synthetic-task-app",
      uid = `uid-${suffix}`,
      account = `account-${suffix}`,
      principal = `principal-${suffix}`,
      credential = `credential-${suffix}`;
    try {
      await owner.unsafe(`DO $roles$ BEGIN
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_application') THEN CREATE ROLE omi_platform_application NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_cleanup') THEN CREATE ROLE omi_platform_cleanup NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore') THEN CREATE ROLE omi_platform_restore NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
      IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='omi_platform_restore_operator') THEN CREATE ROLE omi_platform_restore_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF;
    END $roles$;`);
      await runPostgresMigrations(owner);
      for (const target of [account, `other-${suffix}`]) {
        for (const statement of seedProdLocalFirebaseAuthorizationSql(
          {
            firebase_project_id: project,
            firebase_uid: target === account ? uid : `other-${uid}`,
            application_id: app,
            account_id: target,
            principal_id: principal,
            credential_id: credential,
            grant_id: `memory-${suffix}`,
          },
          now()
        ))
          await owner.unsafe(statement.text, [...statement.values]);
        for (const capability of ["tasks.read", "tasks.write"]) {
          await owner.unsafe(
            `INSERT INTO omi_memory.application_grant_revisions(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version,lifecycle,enabled,scopes,record_schema_version,record_json,content_hash) VALUES($1,$2,$3,1,$4,$5,1,'active',true,'[]','grant-v1','{}',$6)`,
            [
              target,
              app,
              credential,
              capability,
              `${capability}-${suffix}`,
              "3".repeat(64),
            ]
          );
          await owner.unsafe(
            `INSERT INTO omi_memory.application_grant_heads(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version) VALUES($1,$2,$3,1,$4,$5,1)`,
            [target, app, credential, capability, `${capability}-${suffix}`]
          );
        }
      }
      await owner.unsafe(
        `INSERT INTO omi_memory.postgres_restore_admission_revisions(database_generation_digest,release_revision,state,restore_id,restored_snapshot_digest,checkpoint_candidate_digest,checkpoint_evidence_digest,first_approval_subject_digest,first_approval_receipt_digest,second_approval_subject_digest,second_approval_receipt_digest,manual_release_receipt_digest,previous_release_revision,content_hash) VALUES($1,1,'released',$2,$3,$3,$3,$4,$5,$6,$7,$3,NULL,$3)`,
        [
          generation,
          `synthetic-${suffix}`,
          "9".repeat(64),
          "4".repeat(64),
          "5".repeat(64),
          "6".repeat(64),
          "7".repeat(64),
        ]
      );
      await owner.unsafe(
        "INSERT INTO omi_memory.postgres_restore_admission_heads(database_generation_digest,release_revision) VALUES($1,1)",
        [generation]
      );
      let failReceipt = false;
      const failures: string[] = [];
      const appPool: PostgresTransactionPool = {
        withTransaction: (options, callback) =>
          pool
            .withTransaction(options, async (connection) => {
              await connection.query({
                name: "tasks_test.role",
                text: "SET LOCAL ROLE omi_platform_application",
                values: [],
              });
              return callback({
                connectionIdentity: connection.connectionIdentity,
                query: async (statement) => {
                  try {
                    return (await connection.query(statement)) as never;
                  } catch (error) {
                    failures.push(
                      `${statement.name}:${
                        (error as { code?: string }).code ?? "unknown"
                      }`
                    );
                    throw error;
                  }
                },
                execute: async (statement) => {
                  if (failReceipt && statement.name === "tasks.record_receipt")
                    throw Error("synthetic_receipt_failure");
                  try {
                    return await connection.execute(statement);
                  } catch (error) {
                    failures.push(
                      `${statement.name}:${
                        (error as { code?: string }).code ?? "unknown"
                      }`
                    );
                    throw error;
                  }
                },
              });
            })
            .catch((error) => {
              failures.push(
                `transaction:${
                  (error as { code?: string }).code ??
                  (error instanceof Error ? error.message : "unknown")
                }`
              );
              throw error;
            }),
      };
      let expired = false;
      const runtime = createPostgresFirebaseTasksRuntime({
        authorization: {
          pool: appPool,
          project_id: project,
          application_id: app,
          runtime_mode: "deployed",
          context_ttl_seconds: 60,
          database_generation_digest: generation,
          id_token_adapter: {
            verification_source: "firebase_production",
            async verifyIdToken(token) {
              const selected = token.startsWith("other") ? `other-${uid}` : uid;
              return {
                aud: project,
                iss: `https://securetoken.google.com/${project}`,
                sub: selected,
                uid: selected,
                iat: now() - 10,
                auth_time: now() - 10,
                exp: expired ? now() - 1 : now() + 600,
              };
            },
          },
        },
        codecRootSecret: new Uint8Array(32).fill(7),
        cursorSigningKeyset: {
          active_key_id: "test",
          keys: [{ key_id: "test", secret: new Uint8Array(32).fill(8) }],
        },
      });
      const call = (
        path: string,
        body?: string,
        token = "header.payload.signature"
      ) =>
        runtime.executeRequest(
          new Request(`https://tasks.example${path}`, {
            method: body === undefined ? "GET" : "POST",
            headers: {
              authorization: `Bearer ${token}`,
              "content-type": "application/json",
            },
            ...(body === undefined ? {} : { body }),
          })
        );
      const content = {
        description: "Real task",
        completed: false,
        completedAt: null,
        dueAt: null,
        owner: null,
        source: "manual",
        provenance: [],
        sortOrder: 0,
        indentLevel: 0,
        createdAt: 1,
        updatedAt: 1,
      };
      const envelope = (key: string, op: object, epoch = 1) =>
        JSON.stringify({
          write_id: key.repeat(64),
          account_epoch: epoch,
          domain: "tasks",
          op,
        });
      failReceipt = true;
      expect(
        (
          await call(
            "/v1/tasks/ops",
            envelope("9", { op: "create", record_id: "must-rollback", content })
          )
        ).status
      ).toBe(503);
      failReceipt = false;
      expect(
        await owner.unsafe(
          "SELECT record_id FROM omi_memory.task_records WHERE account_id=$1 AND record_id='must-rollback'",
          [account]
        )
      ).toHaveLength(0);
      const create = envelope("a", {
        op: "create",
        record_id: "task-one",
        content,
      });
      failures.length = 0;
      const first = await call("/v1/tasks/ops", create);
      expect({ status: first.status, failures }).toEqual({
        status: 200,
        failures: [],
      });
      const applied = (await first.json()) as {
        applied: { revision: string };
        idempotent: boolean;
      };
      expect(applied.idempotent).toBe(false);
      expect(await (await call("/v1/tasks/ops", create)).json()).toEqual({
        ...applied,
        idempotent: true,
      });
      expect(
        (
          await call(
            "/v1/tasks/ops",
            envelope("a", { op: "create", record_id: "different", content })
          )
        ).status
      ).toBe(409);
      const read = await call("/v1/tasks");
      expect(read.status).toBe(200);
      const page = (await read.json()) as {
        items: { id: string; description: string; revision: string }[];
        accountEpoch: number;
      };
      expect(page.accountEpoch).toBe(1);
      expect(page.items[0]!.description).toBe("Real task");
      expect(page.items[0]!.id).not.toBe("task-one");
      const patch = envelope("b", {
        op: "patch",
        record_id: page.items[0]!.id,
        patch: { description: "Edited" },
        base_revision: page.items[0]!.revision,
      });
      expect((await call("/v1/tasks/ops", patch)).status).toBe(200);
      expect(
        (
          await call(
            "/v1/tasks/ops",
            envelope("c", {
              op: "patch",
              record_id: page.items[0]!.id,
              patch: { description: "Stale" },
              base_revision: page.items[0]!.revision,
            })
          )
        ).status
      ).toBe(409);
      expect(
        (
          (await (
            await call("/v1/tasks", undefined, "other.payload.signature")
          ).json()) as { items: unknown[] }
        ).items
      ).toEqual([]);
      const deletion = envelope("1", {
        op: "delete",
        record_id: page.items[0]!.id,
      });
      expect((await call("/v1/tasks/ops", deletion)).status).toBe(200);
      expect(
        (
          (await (await call("/v1/tasks/ops", deletion)).json()) as {
            idempotent: boolean;
          }
        ).idempotent
      ).toBe(true);
      const recreated = (await (
        await call(
          "/v1/tasks/ops",
          envelope("2", { op: "create", record_id: "task-one", content })
        )
      ).json()) as { applied: { revision: string } };
      expect(recreated.applied.revision).not.toBe(applied.applied.revision);
      await call(
        "/v1/tasks/ops",
        envelope("d", { op: "create", record_id: "task-two", content })
      );
      const paged = (await (await call("/v1/tasks?limit=1")).json()) as Record<
        string,
        unknown
      >;
      expect(paged.window).toBeDefined();
      const cursor = (paged.window as { nextCursor?: string } | undefined)
        ?.nextCursor;
      expect(typeof cursor).toBe("string");
      expect(
        (
          await call(
            "/v1/tasks/ops",
            envelope("3", {
              op: "create",
              record_id: "x".repeat(256),
              content,
            })
          )
        ).status
      ).toBe(200);
      expect(
        (
          await call(
            "/v1/tasks/ops",
            envelope("4", {
              op: "create",
              record_id: "x".repeat(257),
              content,
            })
          )
        ).status
      ).toBe(422);
      await owner.unsafe(
        `UPDATE omi_memory.application_grant_revisions SET lifecycle='revoked' WHERE account_id=$1 AND capability='tasks.write'`,
        [account]
      );
      expect(
        (
          await call(
            "/v1/tasks/ops",
            envelope("e", { op: "delete", record_id: "task-one" })
          )
        ).status
      ).toBe(403);
      await owner.unsafe(
        `UPDATE omi_memory.application_grant_revisions SET lifecycle='active' WHERE account_id=$1 AND capability='tasks.write'`,
        [account]
      );
      await owner.unsafe(
        `INSERT INTO omi_memory.application_grant_revisions(account_id,application_id,credential_id,credential_generation,capability,grant_id,grant_version,lifecycle,enabled,scopes,record_schema_version,record_json,content_hash) SELECT account_id,application_id,credential_id,credential_generation,capability,grant_id,2,lifecycle,enabled,scopes,record_schema_version,record_json,$2 FROM omi_memory.application_grant_revisions WHERE account_id=$1 AND capability='tasks.read' AND grant_version=1`,
        [account, "4".repeat(64)]
      );
      await owner.unsafe(
        `UPDATE omi_memory.application_grant_heads SET grant_version=2 WHERE account_id=$1 AND capability='tasks.read'`,
        [account]
      );
      expect(
        (
          await call(
            `/v1/tasks?limit=1&cursor=${encodeURIComponent(String(cursor))}`
          )
        ).status
      ).toBe(400);
      const stale = envelope(
        "f",
        {
          op: "patch",
          record_id: "task-one",
          patch: { description: "Retain this" },
        },
        0
      );
      expect((await call("/v1/tasks/ops", stale)).status).toBe(409);
      const retained = await owner.unsafe(
        "SELECT envelope_json FROM omi_memory.task_stragglers WHERE account_id=$1",
        [account]
      );
      expect(retained[0]!.envelope_json).toBe(stale);
      expired = true;
      expect((await call("/v1/tasks")).status).toBe(401);
      const tables = await owner.unsafe(
        "SELECT table_name FROM omi_memory.cleanup_surface_tables('product_projections')"
      );
      expect(tables.map((row) => row.table_name)).toContain("task_stragglers");
    } finally {
      await pool.close();
      await owner.end({ timeout: 5 });
    }
  },
  120000
);
