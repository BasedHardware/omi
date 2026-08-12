import { describe, expect, test } from "bun:test";

import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseAuthorizedGraphSnapshotRuntime } from
  "./firebase-authorized-graph-snapshot-runtime";

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => { throw new Error("authorization must not reach postgres"); },
});

describe("PostgreSQL Firebase-authorized graph snapshot runtime", () => {
  test("constructs route-free and rejects an invalid token before PostgreSQL", async () => {
    const runtime = createPostgresFirebaseAuthorizedGraphSnapshotRuntime({
      pool: unusedPool,
      project_id: "omi-project",
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async () => { throw new Error("raw provider token detail"); },
      },
      application_id: "app:memory",
      context_ttl_seconds: 60,
    });
    await expect(runtime.load("invalid.token.value", 100)).resolves.toEqual({
      kind: "denied", outcome: "authentication",
    });
    expect(Object.keys(runtime)).toEqual(["load"]);
  });

  test("shares the exact runtime option boundary and deployed emulator refusal", () => {
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
    };
    expect(() => createPostgresFirebaseAuthorizedGraphSnapshotRuntime({
      ...base, extra: true,
    } as never)).toThrow("invalid PostgreSQL Firebase runtime options");
    expect(() => createPostgresFirebaseAuthorizedGraphSnapshotRuntime({
      ...base,
      id_token_adapter: {
        verification_source: "firebase_auth_emulator",
        verifyIdToken: async () => ({}),
      },
    })).toThrow("deployed Firebase identity forbids the Auth emulator");
  });
});
