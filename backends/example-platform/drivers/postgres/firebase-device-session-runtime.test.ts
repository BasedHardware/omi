import { expect, test } from "bun:test";
import { createPostgresFirebaseDeviceSessionRuntime } from "./firebase-device-session-runtime";
import type { PostgresTransactionPool } from "./connection";

test("device ingress denies missing tokens and unmigrated identities before accepting audio", async () => {
  let queries = 0, writes = 0;
  const pool: PostgresTransactionPool = {
    withTransaction: async (_options, callback) => callback({ connectionIdentity: {},
      query: async () => { queries++; return []; },
      execute: async () => { writes++; return { rowCount: 0 }; },
    }),
  };
  const now = Math.floor(Date.now() / 1000);
  const runtime = createPostgresFirebaseDeviceSessionRuntime({ pool, project_id: "qa-project", runtime_mode: "deployed",
    application_id: "qa-app", context_ttl_seconds: 60, database_generation_digest: "a".repeat(64),
    id_token_adapter: { verification_source: "firebase_production", verifyIdToken: async () => ({
      aud: "qa-project", iss: "https://securetoken.google.com/qa-project", sub: "unmigrated-uid", uid: "unmigrated-uid",
      iat: now - 60, auth_time: now - 60, exp: now + 3600,
    }) },
  });
  const request = (headers: HeadersInit = {}) => new Request("https://service.example/v1/device-sessions", { method: "POST", headers,
    body: JSON.stringify({ captureId: "ad99598c-36a8-4e12-a428-63d0a3e06170", deviceId: "omi", codec: 20 }),
  });
  expect((await runtime.fetch(request())).status).toBe(401);
  expect(queries).toBe(0);
  const denied = await runtime.fetch(request({ authorization: "Bearer header.payload.signature" }));
  expect(denied.status).toBe(403);
  expect(await denied.json()).toEqual({ error: { code: "forbidden" } });
  expect(queries).toBeGreaterThan(0);
  expect(writes).toBe(0);
  const cancelled = new AbortController();
  cancelled.abort();
  expect((await runtime.fetch(new Request(request(), { signal: cancelled.signal }))).status).toBe(503);
  expect(writes).toBe(0);
});
