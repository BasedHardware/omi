import { describe, expect, test } from "bun:test";

import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseAuthorizedMemoryReadRuntime } from
  "./firebase-authorized-memory-read-runtime";

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => { throw new Error("invalid identity must not reach PostgreSQL"); },
});

describe("route-free PostgreSQL Firebase memory product runtime", () => {
  test("denies invalid identity before graph, renderer, cursor, or trace work", async () => {
    let renders = 0;
    let traces = 0;
    const runtime = createPostgresFirebaseAuthorizedMemoryReadRuntime({
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
        database_generation_digest: "d".repeat(64),
      },
      product: {
        account_timezone: "UTC",
        codec_root_secret: new Uint8Array(32).fill(0x31),
        produce_renders: async () => { renders += 1; return []; },
        verify_cursor: () => { throw new Error("cursor verification must not run"); },
        issue_cursor: () => { throw new Error("cursor issue must not run"); },
        trace_sink: () => { traces += 1; },
        accepted_coverage_state: "bypassed",
        stm_coverage_state: "bypassed",
      },
    });
    await expect(runtime.read(
      "invalid.token.value",
      100,
      { limit: 25, cursor: null },
    )).resolves.toEqual({ kind: "denied", outcome: "authentication" });
    await expect(runtime.readForAccount(
      "invalid.token.value",
      100,
      "account:alice",
      { limit: 25, cursor: null },
    )).resolves.toEqual({ kind: "denied", outcome: "authentication" });
    await expect(runtime.readForAccount(
      "header.payload.signature",
      100,
      "bad account",
      { limit: 25, cursor: null },
    )).resolves.toEqual({ kind: "denied", outcome: "authorization" });
    expect(renders).toBe(0);
    expect(traces).toBe(0);
    expect(Object.keys(runtime)).toEqual(["authenticate", "read", "readForAccount"]);
  });

  test("rejects extra composition options without invoking dependencies", () => {
    expect(() => createPostgresFirebaseAuthorizedMemoryReadRuntime({
      authorization: {} as never,
      product: {} as never,
      extra: true,
    } as never)).toThrow("invalid Firebase-authorized memory read runtime options");
  });

});
