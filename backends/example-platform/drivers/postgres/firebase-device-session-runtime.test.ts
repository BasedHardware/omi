import { expect, test } from "bun:test";
import { FIREBASE_ID_TOKEN_VERIFICATION_UNAVAILABLE } from "../../apps/service/auth/firebase-identity";
import { createPostgresFirebaseDeviceSessionRuntime } from "./firebase-device-session-runtime";
import type { PostgresTransactionPool, SqlStatement } from "./connection";

const PROJECT = "qa-project";
const APPLICATION = "qa-app";
const UID = "firebase-user-alice";
const DATABASE_GENERATION = "a".repeat(64);
const NESTED_OWNERSHIP_UNAVAILABLE = {
  error: { code: "capture_ownership_unavailable", retryable: false, action: "none" },
} as const;

const claims = (now: number, uid = UID) => ({
  aud: PROJECT,
  iss: `https://securetoken.google.com/${PROJECT}`,
  sub: uid,
  uid,
  iat: now - 60,
  auth_time: now - 60,
  exp: now + 3600,
});

const authorizationOptions = (
  pool: PostgresTransactionPool,
  verify: () => Promise<unknown>,
) => ({
  pool,
  project_id: PROJECT,
  runtime_mode: "deployed" as const,
  application_id: APPLICATION,
  context_ttl_seconds: 60,
  database_generation_digest: DATABASE_GENERATION,
  id_token_adapter: {
    verification_source: "firebase_production" as const,
    verifyIdToken: verify,
  },
});

const emptyPool = (counts: { queries: number; writes: number }): PostgresTransactionPool => ({
  withTransaction: async (_options, callback) => callback({
    connectionIdentity: {},
    query: async () => {
      counts.queries += 1;
      return [];
    },
    execute: async () => {
      counts.writes += 1;
      return { rowCount: 0 };
    },
  }),
});

const admittedPool = (now: number): PostgresTransactionPool => {
  const authorizationRow = {
    firebase_project_id: PROJECT,
    firebase_uid: UID,
    principal_id: "principal:alice",
    account_id: "account:alice",
    application_id: APPLICATION,
    credential_id: "credential:capture:one",
    credential_generation: 4,
    credential_lifecycle: "active",
    authentication_strength: "firebase-id-token",
    credential_expires_at_epoch_seconds: now + 3600,
    capability: "listen.capture.write",
    grant_id: "grant:listen:capture:write",
    grant_version: 9,
    grant_lifecycle: "active",
    grant_enabled: true,
    control_revision: 17,
    account_epoch: 12,
    destination_activation_revision: 17,
    destination_activation_epoch: 12,
    control_conflict_reason: null,
    control_conflict_at_revision: null,
    lifecycle_state: "active",
    deletion_epoch: null,
    account_generation: "new",
    control_content_hash: "1".repeat(64),
    credential_content_hash: "2".repeat(64),
    grant_content_hash: "3".repeat(64),
    database_generation_digest: DATABASE_GENERATION,
    restore_release_revision: 3,
    restore_release_content_hash: "c".repeat(64),
  };
  const controlRow = {
    account_id: "account:alice",
    control_revision: "17",
    account_generation: "new",
    account_epoch: "12",
    lifecycle_state: "active",
    deletion_epoch: null,
    activated_epoch: "12",
    activation_control_revision: "17",
    conflict_reason: null,
    conflict_at_revision: null,
  };
  return {
    withTransaction: async (_options, callback) => callback({
      connectionIdentity: {},
      query: async (statement: SqlStatement) => {
        if (statement.name === "firebase_authorization.lookup_current") return [authorizationRow];
        if (statement.name === "application_control.load_current") return [controlRow];
        throw new Error(`unexpected ${statement.name}`);
      },
      execute: async () => {
        throw new Error("missing signing key must not mutate capture rows");
      },
    }),
  };
};

const captureRequest = (path: string, method = "GET", headers: HeadersInit = {}) =>
  new Request(`https://service.example${path}`, {
    method,
    headers,
    ...(method === "POST"
      ? {
        body: JSON.stringify({
          captureId: "ad99598c-36a8-4e12-a428-63d0a3e06170",
          deviceId: "omi",
          codec: 20,
        }),
      }
      : {}),
  });

test("device ingress denies missing tokens and unmigrated identities before accepting audio", async () => {
  const counts = { queries: 0, writes: 0 };
  const now = Math.floor(Date.now() / 1000);
  const runtime = createPostgresFirebaseDeviceSessionRuntime(
    authorizationOptions(emptyPool(counts), async () => claims(now, "unmigrated-uid")),
  );
  const request = (headers: HeadersInit = {}) => captureRequest("/v1/device-sessions", "POST", headers);
  expect((await runtime.fetch(request())).status).toBe(401);
  expect(counts.queries).toBe(0);
  const denied = await runtime.fetch(request({ authorization: "Bearer header.payload.signature" }));
  expect(denied.status).toBe(403);
  expect(await denied.json()).toEqual({ error: { code: "forbidden" } });
  expect(counts.queries).toBeGreaterThan(0);
  expect(counts.writes).toBe(0);
  const cancelled = new AbortController();
  cancelled.abort();
  expect((await runtime.fetch(new Request(request(), { signal: cancelled.signal }))).status).toBe(503);
  expect(counts.writes).toBe(0);
});

test("a missing ownership signing key is nested non-retryable without inventing a receipt", async () => {
  const now = Math.floor(Date.now() / 1000);
  const runtime = createPostgresFirebaseDeviceSessionRuntime(
    authorizationOptions(admittedPool(now), async () => claims(now)),
  );
  const headers = { authorization: "Bearer header.payload.signature" };
  for (const request of [
    captureRequest("/v1/device-sessions/ownership", "GET", headers),
    captureRequest("/v1/device-sessions", "POST", headers),
  ]) {
    const response = await runtime.fetch(request);
    expect(response.status).toBe(503);
    expect(response.headers.get("retry-after")).toBeNull();
    expect(await response.json()).toEqual(NESTED_OWNERSHIP_UNAVAILABLE);
  }
});

test("identity and authorization outages stay retryable unavailable rather than missing ownership", async () => {
  const now = Math.floor(Date.now() / 1000);
  const identityRuntime = createPostgresFirebaseDeviceSessionRuntime(
    authorizationOptions(emptyPool({ queries: 0, writes: 0 }), async () => {
      throw new Error(FIREBASE_ID_TOKEN_VERIFICATION_UNAVAILABLE);
    }),
  );
  const throwingPool: PostgresTransactionPool = {
    withTransaction: async () => {
      throw new Error("authorization source outage");
    },
  };
  const authorizationRuntime = createPostgresFirebaseDeviceSessionRuntime(
    authorizationOptions(throwingPool, async () => claims(now)),
  );
  const headers = { authorization: "Bearer header.payload.signature" };
  for (const runtime of [identityRuntime, authorizationRuntime]) {
    for (const request of [
      captureRequest("/v1/device-sessions/ownership", "GET", headers),
      captureRequest("/v1/device-sessions", "POST", headers),
    ]) {
      const response = await runtime.fetch(request);
      expect(response.status).toBe(503);
      expect(response.headers.get("retry-after")).toBe("1");
      expect(await response.json()).toEqual({ error: { code: "unavailable" } });
    }
  }
});
