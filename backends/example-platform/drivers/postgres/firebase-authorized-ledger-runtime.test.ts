import { describe, expect, test } from "bun:test";

import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseAuthorizedLedgerRuntime } from
  "./firebase-authorized-ledger-runtime";

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => { throw new Error("authorization must not reach postgres"); },
});

describe("PostgreSQL Firebase-authorized ledger runtime", () => {
  test("constructs inertly and rejects an invalid token before PostgreSQL", async () => {
    const runtime = createPostgresFirebaseAuthorizedLedgerRuntime({
      pool: unusedPool,
      project_id: "omi-project",
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async () => { throw new Error("invalid token raw provider detail"); },
      },
      application_id: "app:memory",
      context_ttl_seconds: 60,
      database_generation_digest: "d".repeat(64),
    });
    await expect(runtime.append("invalid.token.value", 100, {} as never)).resolves.toEqual({
      kind: "denied", outcome: "authentication",
    });
    expect(Object.keys(runtime)).toEqual(["append"]);
  });

  test("configuration is exact and deployed mode refuses emulator identity", () => {
    const base = {
      pool: unusedPool,
      project_id: "omi-project",
      runtime_mode: "deployed" as const,
      id_token_adapter: {
        verification_source: "firebase_production" as const,
        verifyIdToken: async () => ({}),
      },
      application_id: "app:memory",
      context_ttl_seconds: 60,
      database_generation_digest: "d".repeat(64),
    };
    expect(() => createPostgresFirebaseAuthorizedLedgerRuntime({ ...base, extra: true } as never))
      .toThrow("invalid PostgreSQL Firebase runtime options");
    expect(() => createPostgresFirebaseAuthorizedLedgerRuntime(new Proxy(base, {}) as never))
      .toThrow("invalid PostgreSQL Firebase runtime options");
    expect(() => createPostgresFirebaseAuthorizedLedgerRuntime({
      ...base,
      id_token_adapter: {
        verification_source: "firebase_auth_emulator",
        verifyIdToken: async () => ({}),
      },
    })).toThrow("deployed Firebase identity forbids the Auth emulator");
  });

  test("snapshots the transaction capability and uses only the fixed authorization query", async () => {
    let originalCalls = 0;
    let replacementCalls = 0;
    const mutablePool: PostgresTransactionPool = {
      withTransaction: async (_options, callback) => {
        originalCalls += 1;
        return callback(Object.freeze({
          connectionIdentity: Object.freeze({}),
          query: async () => [],
          execute: async () => { throw new Error("execute is not available to authorization"); },
        }));
      },
    };
    const runtime = createPostgresFirebaseAuthorizedLedgerRuntime({
      pool: mutablePool,
      project_id: "omi-project",
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async () => ({
          aud: "omi-project",
          iss: "https://securetoken.google.com/omi-project",
          sub: "firebase-user",
          uid: "firebase-user",
          exp: 1_000,
          iat: 900,
          auth_time: 800,
        }),
      },
      application_id: "app:memory",
      context_ttl_seconds: 60,
      database_generation_digest: "d".repeat(64),
    });
    mutablePool.withTransaction = async () => {
      replacementCalls += 1;
      throw new Error("mutated pool");
    };
    await expect(runtime.append("header.payload.signature", 950, {} as never)).resolves.toEqual({
      kind: "denied", outcome: "authorization",
    });
    expect(originalCalls).toBe(1);
    expect(replacementCalls).toBe(0);
  });
});
