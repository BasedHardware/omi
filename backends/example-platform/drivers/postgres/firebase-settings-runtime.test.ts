import { expect, test } from "bun:test";
import { FIREBASE_ID_TOKEN_VERIFICATION_UNAVAILABLE } from "../../apps/service/auth/firebase-identity";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseSettingsRuntime } from "./firebase-settings-runtime";

const PROJECT = "qa-project";
const SIGNED_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signature";

const claims = (now: number) => ({
  aud: PROJECT,
  iss: `https://securetoken.google.com/${PROJECT}`,
  sub: "firebase-user-1",
  uid: "firebase-user-1",
  exp: now + 3_600,
  iat: now - 60,
  auth_time: now - 120,
  email: "private@example.invalid",
  name: "Invented Profile",
});

const authorization = (
  verify: (token: string, checkRevoked: boolean) => Promise<unknown>,
  pool: PostgresTransactionPool,
) => ({
  pool,
  project_id: PROJECT,
  runtime_mode: "deployed" as const,
  application_id: "qa-app",
  context_ttl_seconds: 60,
  database_generation_digest: "a".repeat(64),
  id_token_adapter: {
    verification_source: "firebase_production" as const,
    verifyIdToken: verify,
  },
});

const unusedPool: PostgresTransactionPool = {
  withTransaction: async () => {
    throw new Error("settings must not query PostgreSQL until a producer exists");
  },
};

test("signed-out settings stay null and verified identity stays unavailable without inventing a profile", async () => {
  const calls: boolean[] = [];
  const runtime = createPostgresFirebaseSettingsRuntime({
    authorization: authorization(async (_token, checkRevoked) => {
      calls.push(checkRevoked);
      return claims(Math.floor(Date.now() / 1000));
    }, unusedPool),
  });
  const absent = await runtime.executeRequest(new Request("https://service.example/v1/settings"));
  expect(absent.status).toBe(200);
  expect(await absent.json()).toEqual({ identity: null, entitlement: null });
  expect(calls).toEqual([]);

  const verified = await runtime.executeRequest(new Request("https://service.example/v1/settings", {
    headers: { authorization: `Bearer ${SIGNED_TOKEN}` },
  }));
  const body = await verified.text();
  expect(verified.status).toBe(503);
  expect(verified.headers.get("retry-after")).toBeNull();
  expect(body).toBe(
    '{"error":{"code":"service_unavailable","retryable":false,"action":"none"}}',
  );
  expect(body).not.toContain("private@example.invalid");
  expect(body).not.toContain("Invented Profile");
  expect(calls).toEqual([false, true]);

  expect((await runtime.executeRequest(new Request(
    "https://service.example/v1/settings",
    { headers: { authorization: "Bearer invalid.token" } },
  ))).status).toBe(401);
  expect((await runtime.executeRequest(new Request(
    "https://service.example/v1/settings?appearance=dark",
    { headers: { authorization: `Bearer ${SIGNED_TOKEN}` } },
  ))).status).toBe(400);
  expect((await runtime.executeRequest(new Request(
    "https://service.example/v1/settings",
    { method: "POST", body: "{}" },
  ))).status).toBe(404);
});

test("Firebase verification outage is unavailable rather than a signed-out envelope", async () => {
  const runtime = createPostgresFirebaseSettingsRuntime({
    authorization: authorization(async () => {
      throw new Error(FIREBASE_ID_TOKEN_VERIFICATION_UNAVAILABLE);
    }, unusedPool),
  });
  const result = await runtime.executeRequest(new Request("https://service.example/v1/settings", {
    headers: { authorization: `Bearer ${SIGNED_TOKEN}` },
  }));
  expect(result.status).toBe(503);
  expect(result.headers.get("retry-after")).toBe("60");
  expect(await result.text()).toBe('{"error":"service_unavailable"}');
});
