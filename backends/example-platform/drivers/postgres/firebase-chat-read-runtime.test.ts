import { expect, test } from "bun:test";
import { CHAT_CAPABILITIES } from "../../apps/service/routes/chat-messages";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseChatReadRuntime } from "./firebase-chat-read-runtime";

const authorization = (pool: PostgresTransactionPool) => ({
  pool,
  project_id: "qa-project",
  runtime_mode: "deployed" as const,
  application_id: "qa-app",
  context_ttl_seconds: 60,
  database_generation_digest: "a".repeat(64),
  id_token_adapter: {
    verification_source: "firebase_production" as const,
    verifyIdToken: async () => {
      const now = Math.floor(Date.now() / 1000);
      return {
        aud: "qa-project",
        iss: "https://securetoken.google.com/qa-project",
        sub: "unmigrated-uid",
        uid: "unmigrated-uid",
        iat: now - 60,
        auth_time: now - 60,
        exp: now + 3600,
      };
    },
  },
});

const runtimeFor = (pool: PostgresTransactionPool) => createPostgresFirebaseChatReadRuntime({
  authorization: authorization(pool),
  codecRootSecret: new Uint8Array(32).fill(7),
  cursorSigningKeyset: {
    active_key_id: "test",
    keys: [{ key_id: "test", secret: new Uint8Array(32).fill(8) }],
  },
});

test("chat GET denies missing tokens and missing grants instead of returning empty history", async () => {
  let queries = 0;
  const pool: PostgresTransactionPool = {
    withTransaction: async (_options, callback) => callback({
      connectionIdentity: {},
      query: async () => {
        queries += 1;
        return [];
      },
      execute: async () => ({ rowCount: 0 }),
    }),
  };
  const runtime = runtimeFor(pool);
  const request = (headers: HeadersInit = {}) => new Request(
    "https://service.example/v1/chat-messages?limit=50",
    { headers },
  );
  const missing = await runtime.executeRequest(request());
  expect(missing.status).toBe(401);
  expect(await missing.json()).toEqual({
    error: { code: "unauthorized", retryable: false, action: "reauthenticate" },
  });
  expect(queries).toBe(0);
  const denied = await runtime.executeRequest(request({
    authorization: "Bearer header.payload.signature",
  }));
  expect(denied.status).toBe(403);
  expect(await denied.json()).toEqual({
    error: { code: "forbidden", retryable: false, action: "none" },
  });
  expect(queries).toBeGreaterThan(0);
  expect(CHAT_CAPABILITIES.maxAttachmentsPerMessage).toBe(4);
  const cancelled = new AbortController();
  cancelled.abort();
  expect((await runtime.executeRequest(new Request(request(), { signal: cancelled.signal }))).status)
    .toBe(503);
});

test("chat writes stay nested 404 without consulting grants or inventing admission", async () => {
  let queries = 0;
  const pool: PostgresTransactionPool = {
    withTransaction: async (_options, callback) => callback({
      connectionIdentity: {},
      query: async () => {
        queries += 1;
        return [];
      },
      execute: async () => ({ rowCount: 0 }),
    }),
  };
  const runtime = runtimeFor(pool);
  const nestedNotFound = {
    error: { code: "not_found", retryable: false, action: "none" },
  };
  for (const request of [
    new Request("https://service.example/v1/chat-messages", { method: "POST", body: "{}" }),
    new Request("https://service.example/v1/chat-generations/generation-1/events"),
    new Request("https://service.example/v1/chat-generations/generation-1", { method: "DELETE" }),
    new Request("https://service.example/v1/chat-attachments", { method: "POST", body: "{}" }),
    new Request("https://service.example/v1/chat-attachments/att-1/complete", {
      method: "POST",
      body: "{}",
    }),
  ]) {
    const response = await runtime.executeRequest(request);
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual(nestedNotFound);
  }
  expect(queries).toBe(0);
});
