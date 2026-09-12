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

test("a missing transcription source is nested non-retryable without inventing speech", async () => {
  const now = Math.floor(Date.now() / 1000);
  const ownershipKey = new Uint8Array(32).fill(7);
  const runtime = createPostgresFirebaseDeviceSessionRuntime(
    authorizationOptions(admittedPool(now), async () => claims(now)),
    undefined,
    ownershipKey,
  );
  const headers = { authorization: "Bearer header.payload.signature" };
  const owner = await runtime.fetch(
    captureRequest("/v1/device-sessions/ownership", "GET", headers),
  );
  expect(owner.status).toBe(200);
  const receipt = ((await owner.json()) as { ownership: { receipt: string } })
    .ownership.receipt;
  const transcribe = await runtime.fetch(
    new Request(
      "https://service.example/v1/device-sessions/ad99598c-36a8-4e12-a428-63d0a3e06170/transcribe",
      {
        method: "POST",
        headers: { ...headers, "x-omi-capture-ownership": receipt },
      },
    ),
  );
  expect(transcribe.status).toBe(503);
  expect(transcribe.headers.get("retry-after")).toBeNull();
  expect((await transcribe.json()) as unknown).toEqual({
    error: { code: "service_unavailable", retryable: false, action: "none" },
  });
});

test("completed SQL-null providerResult is nested non-retryable without inventing speech", async () => {
  const now = Math.floor(Date.now() / 1000);
  const sessionId = "ad99598c-36a8-4e12-a428-63d0a3e06170";
  const pool: PostgresTransactionPool = {
    withTransaction: async (_options, callback) => callback({
      connectionIdentity: {},
      query: async (statement: SqlStatement) => {
        if (statement.name === "firebase_authorization.lookup_current") {
          return admittedPool(now).withTransaction(
            { isolationLevel: "serializable", accessMode: "read write" },
            connection => connection.query(statement),
          );
        }
        if (statement.name === "application_control.load_current") {
          return admittedPool(now).withTransaction(
            { isolationLevel: "serializable", accessMode: "read write" },
            connection => connection.query(statement),
          );
        }
        if (statement.name === "authority.set_local") return [];
        if (statement.name === "authority.lock_and_revalidate") {
          return [{
            account_id: "account:alice",
            principal_id: "principal:alice",
            application_id: APPLICATION,
            credential_id: "credential:capture:one",
            credential_generation: 4,
            capability: "listen.capture.write",
            grant_id: "grant:listen:capture:write",
            grant_version: 9,
            account_epoch: 12,
            control_conflict_reason: null,
            control_conflict_at_revision: null,
            destination_activation_epoch: 12,
            destination_activation_revision: 17,
            lifecycle_state: "active",
            deletion_epoch: null,
            account_generation: "new",
            credential_lifecycle: "active",
            grant_lifecycle: "active",
            grant_enabled: true,
            authentication_strength: "firebase-id-token",
            credential_expires_at_epoch_seconds: now + 3600,
            control_revision: 17,
            control_content_hash: "1".repeat(64),
            credential_content_hash: "2".repeat(64),
            grant_content_hash: "3".repeat(64),
            db_now_epoch_seconds: Math.floor(Date.now() / 1000),
          }];
        }
        if (statement.name === "listen.transcription.read") {
          return [{
            result: {
              sessionId,
              state: "completed",
              providerResult: null,
              discardedLeadingPackets: 0,
              errorCode: null,
              updatedAt: 123,
              startedAt: "2026-09-07T00:00:00Z",
              codec: 21,
              chunkCount: 1,
              byteCount: 3,
            },
          }];
        }
        if (statement.name === "listen.transcription.final_clock") {
          return [{ now: Math.floor(Date.now() / 1000) }];
        }
        throw new Error(`unexpected ${statement.name}`);
      },
      execute: async () => {
        throw new Error("completed SQL-null transcript GET must not mutate capture rows");
      },
    }),
  };
  const runtime = createPostgresFirebaseDeviceSessionRuntime(
    authorizationOptions(pool, async () => claims(now)),
  );
  const response = await runtime.fetch(
    captureRequest(`/v1/device-sessions/${sessionId}/transcript`, "GET", {
      authorization: "Bearer header.payload.signature",
    }),
  );
  expect(response.status).toBe(503);
  expect(response.headers.get("retry-after")).toBeNull();
  expect(await response.json()).toEqual({
    error: { code: "service_unavailable", retryable: false, action: "none" },
  });
});

test("completed unreadable providerResult is nested non-retryable without inventing speech", async () => {
  const now = Math.floor(Date.now() / 1000);
  const sessionId = "ad99598c-36a8-4e12-a428-63d0a3e06170";
  const pool: PostgresTransactionPool = {
    withTransaction: async (_options, callback) => callback({
      connectionIdentity: {},
      query: async (statement: SqlStatement) => {
        if (statement.name === "firebase_authorization.lookup_current") {
          return admittedPool(now).withTransaction(
            { isolationLevel: "serializable", accessMode: "read write" },
            connection => connection.query(statement),
          );
        }
        if (statement.name === "application_control.load_current") {
          return admittedPool(now).withTransaction(
            { isolationLevel: "serializable", accessMode: "read write" },
            connection => connection.query(statement),
          );
        }
        if (statement.name === "authority.set_local") return [];
        if (statement.name === "authority.lock_and_revalidate") {
          return [{
            account_id: "account:alice",
            principal_id: "principal:alice",
            application_id: APPLICATION,
            credential_id: "credential:capture:one",
            credential_generation: 4,
            capability: "listen.capture.write",
            grant_id: "grant:listen:capture:write",
            grant_version: 9,
            account_epoch: 12,
            control_conflict_reason: null,
            control_conflict_at_revision: null,
            destination_activation_epoch: 12,
            destination_activation_revision: 17,
            lifecycle_state: "active",
            deletion_epoch: null,
            account_generation: "new",
            credential_lifecycle: "active",
            grant_lifecycle: "active",
            grant_enabled: true,
            authentication_strength: "firebase-id-token",
            credential_expires_at_epoch_seconds: now + 3600,
            control_revision: 17,
            control_content_hash: "1".repeat(64),
            credential_content_hash: "2".repeat(64),
            grant_content_hash: "3".repeat(64),
            db_now_epoch_seconds: Math.floor(Date.now() / 1000),
          }];
        }
        if (statement.name === "listen.transcription.read") {
          return [{
            result: {
              sessionId,
              state: "completed",
              providerResult: { durationSeconds: 1, segments: "nope" },
              discardedLeadingPackets: 0,
              errorCode: null,
              updatedAt: 123,
              startedAt: "2026-09-07T00:00:00Z",
              codec: 21,
              chunkCount: 1,
              byteCount: 3,
            },
          }];
        }
        if (statement.name === "listen.transcription.final_clock") {
          return [{ now: Math.floor(Date.now() / 1000) }];
        }
        throw new Error(`unexpected ${statement.name}`);
      },
      execute: async () => {
        throw new Error("completed unreadable transcript GET must not mutate capture rows");
      },
    }),
  };
  const runtime = createPostgresFirebaseDeviceSessionRuntime(
    authorizationOptions(pool, async () => claims(now)),
  );
  const response = await runtime.fetch(
    captureRequest(`/v1/device-sessions/${sessionId}/transcript`, "GET", {
      authorization: "Bearer header.payload.signature",
    }),
  );
  expect(response.status).toBe(503);
  expect(response.headers.get("retry-after")).toBeNull();
  expect(await response.json()).toEqual({
    error: { code: "service_unavailable", retryable: false, action: "none" },
  });
});
