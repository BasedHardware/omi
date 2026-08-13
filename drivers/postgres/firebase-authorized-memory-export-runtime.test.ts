import { describe, expect, test } from "bun:test";

import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseAuthorizedMemoryExportRuntime } from
  "./firebase-authorized-memory-export-runtime";

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => { throw new Error("invalid identity must not reach PostgreSQL"); },
});

describe("route-free PostgreSQL Firebase memory export runtime", () => {
  test("denies invalid identity before graph or renderer work", async () => {
    let renders = 0;
    const runtime = createPostgresFirebaseAuthorizedMemoryExportRuntime({
      authorization: {
        pool: unusedPool,
        project_id: "omi-project",
        runtime_mode: "deployed",
        id_token_adapter: {
          verification_source: "firebase_production",
          verifyIdToken: async () => { throw new Error("raw token detail"); },
        },
        application_id: "app:memory",
        context_ttl_seconds: 60,
      },
      product: {
        account_timezone: "UTC",
        codec_root_secret: new Uint8Array(32).fill(0x31),
        produce_renders: async () => { renders += 1; return []; },
        chunk_max_bytes: 64 * 1024,
      },
    });
    await expect(runtime.export("invalid.token.value", 100)).resolves.toEqual({
      kind: "denied", outcome: "authentication",
    });
    expect(renders).toBe(0);
    expect(Object.keys(runtime)).toEqual(["export"]);
  });

  test("rejects hostile or unbounded composition options", () => {
    expect(() => createPostgresFirebaseAuthorizedMemoryExportRuntime({
      authorization: {} as never,
      product: {} as never,
      extra: true,
    } as never)).toThrow("invalid Firebase-authorized memory export runtime options");
    expect(() => createPostgresFirebaseAuthorizedMemoryExportRuntime({
      authorization: {
        pool: unusedPool,
        project_id: "omi-project",
        runtime_mode: "deployed",
        id_token_adapter: {
          verification_source: "firebase_production",
          verifyIdToken: async () => ({}),
        },
        application_id: "app:memory",
        context_ttl_seconds: 60,
      },
      product: {
        account_timezone: "UTC",
        codec_root_secret: new Uint8Array(32).fill(0x31),
        produce_renders: async () => [],
        chunk_max_bytes: 1,
      },
    })).toThrow("invalid Firebase-authorized memory export runtime options");
  });
});
