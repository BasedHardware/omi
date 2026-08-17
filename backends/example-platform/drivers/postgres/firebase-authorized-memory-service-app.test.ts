import { describe, expect, test } from "bun:test";

import { createServedCounter } from "../../apps/service/observability/served-count";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseAuthorizedMemoryServiceApp } from
  "./firebase-authorized-memory-service-app";

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => { throw new Error("invalid identity must not reach PostgreSQL"); },
});

const options = () => ({
  mcp_handler: () => new Response("mcp", { status: 202 }),
  memory_read: {
    authorization: {
      pool: unusedPool,
      project_id: "omi-project",
      runtime_mode: "deployed" as const,
      id_token_adapter: {
        verification_source: "firebase_production" as const,
        verifyIdToken: async () => { throw new Error("raw identity detail"); },
      },
      application_id: "app:memory",
      context_ttl_seconds: 60,
      database_generation_digest: "d".repeat(64),
    },
    product: {
      account_timezone: "UTC",
      codec_root_secret: new Uint8Array(32).fill(0x31),
      produce_renders: async () => [],
      verify_cursor: () => { throw new Error("not reached"); },
      issue_cursor: () => { throw new Error("not reached"); },
      trace_sink: () => undefined,
      accepted_coverage_state: "bypassed" as const,
      stm_coverage_state: "bypassed" as const,
    },
  },
  now_epoch_seconds: () => 100,
  counter: createServedCounter(),
});

describe("PostgreSQL Firebase canonical memory service app", () => {
  test("binds invalid Firebase identity to the existing 401 and keeps MCP on the same root", async () => {
    const app = createPostgresFirebaseAuthorizedMemoryServiceApp(options());
    const memory = await app.request("/v1/memories", {
      headers: { authorization: "Bearer invalid.token" },
    });
    expect(memory.status).toBe(401);
    expect(await memory.text()).toBe('{"error":"unauthorized"}');
    const malformedQuery = await app.request("/v1/memories?limit=0", {
      headers: { authorization: "Bearer invalid.token" },
    });
    expect(malformedQuery.status).toBe(401);
    expect(await malformedQuery.text()).toBe('{"error":"unauthorized"}');
    const mcp = await app.request("/mcp", { method: "POST" });
    expect(mcp.status).toBe(202);
    expect(await mcp.text()).toBe("mcp");
  });

  test("a valid signature that cannot re-check revocation is not a logout", async () => {
    const projectId = "omi-project";
    const now = 1_800_000_000;
    const base = options();
    const app = createPostgresFirebaseAuthorizedMemoryServiceApp({
      ...base,
      now_epoch_seconds: () => now,
      memory_read: {
        ...base.memory_read,
        authorization: {
          ...base.memory_read.authorization,
          project_id: projectId,
          id_token_adapter: {
            verification_source: "firebase_production",
            async verifyIdToken(_token: string, checkRevoked: boolean): Promise<unknown> {
              if (checkRevoked) throw new Error("firebase_admin_identity_unavailable");
              return {
                aud: projectId,
                iss: `https://securetoken.google.com/${projectId}`,
                sub: "firebase-user-1",
                uid: "firebase-user-1",
                exp: now + 3_600,
                iat: now - 60,
                auth_time: now - 120,
              };
            },
          },
        },
      },
    });
    const memory = await app.request("/v1/memories", {
      headers: { authorization: "Bearer header.payload.signature" },
    });
    expect(memory.status).toBe(500);
    expect(await memory.text()).toBe('{"error":"internal_server_error"}');
    expect(memory.status).not.toBe(401);
    expect(memory.status).not.toBe(200);
  });

  test("rejects extra, accessor, and proxy composition options before dependency work", () => {
    expect(() => createPostgresFirebaseAuthorizedMemoryServiceApp({
      ...options(),
      extra: true,
    } as never)).toThrow("invalid PostgreSQL Firebase memory service options");

    let getters = 0;
    const hostile = Object.defineProperty(options(), "mcp_handler", {
      enumerable: true,
      get() { getters += 1; return () => new Response(null); },
    });
    expect(() => createPostgresFirebaseAuthorizedMemoryServiceApp(hostile as never)).toThrow();
    expect(getters).toBe(0);
    expect(() => createPostgresFirebaseAuthorizedMemoryServiceApp(
      new Proxy(options(), {}) as never,
    )).toThrow();
  });
});
