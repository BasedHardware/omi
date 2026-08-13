import { describe, expect, test } from "bun:test";

import type { PostgresTransactionPool } from "./connection";
import {
  createPostgresFirebaseAuthorizedGraphSnapshotRuntime,
  createPostgresFirebaseAuthorizedGraphSnapshotRuntimeForCapability,
  projectFirebaseAuthorizedGraphSnapshotLoad,
} from
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
      database_generation_digest: "d".repeat(64),
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
      database_generation_digest: "d".repeat(64),
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
    expect(() => createPostgresFirebaseAuthorizedGraphSnapshotRuntimeForCapability(
      base,
      "memories.write" as never,
    )).toThrow("invalid Firebase-authorized graph capability");
  });

  test("rejects a structural loaded-outcome lookalike without sealed authority", () => {
    expect(() => projectFirebaseAuthorizedGraphSnapshotLoad({
      kind: "loaded",
      authorization_generation_digest: "a".repeat(64),
      db_now_epoch_seconds: 100,
      snapshot: {} as never,
    }, "UTC")).toThrow("invalid Firebase-authorized graph projection input");
  });
});
