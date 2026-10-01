import { expect, test } from "bun:test";

import { composeFirebaseMemoryAuthorization } from "../../apps/service/composition/firebase-memory-authorization";
import type { PostgresTransactionPool } from "./connection";
import { createPostgresFirebaseAuthorizationRuntime } from "./firebase-authorized-runtime-support";

const NOW = 100;
const PROJECT = "omi-fixture-project";
const ACCOUNT = "account:alice";
const APP = "app:desktop";

const claims = (overrides: Record<string, unknown> = {}) => ({
  aud: PROJECT,
  iss: `https://securetoken.google.com/${PROJECT}`,
  sub: "firebase-user-alice",
  uid: "firebase-user-alice",
  exp: 400,
  iat: 90,
  auth_time: 80,
  ...overrides,
});

const authorization = (capability: string, overrides: Record<string, unknown> = {}) => ({
  status: "current",
  firebase_project_id: PROJECT,
  firebase_uid: "firebase-user-alice",
  principal_id: "principal:alice",
  account_id: ACCOUNT,
  application_id: APP,
  credential_id: "credential:desktop:one",
  credential_generation: 4,
  credential_lifecycle: "active",
  authentication_strength: "firebase-id-token",
  credential_expires_at_epoch_seconds: 300,
  capability,
  grant_id: `grant:${capability}`,
  grant_version: 9,
  grant_lifecycle: "active",
  grant_enabled: true,
  authorization_state_digest: "a".repeat(64),
  control_revision: 17,
  account_epoch: 12,
  destination_activation_revision: 17,
  database_generation_digest: "b".repeat(64),
  restore_release_revision: 3,
  restore_release_content_hash: "c".repeat(64),
  ...overrides,
});

const control = () => ({
  status: "current",
  projection: {
    account_id: ACCOUNT,
    control_revision: 17,
    account_generation: "new",
    account_epoch: 12,
    lifecycle_state: "active",
    deletion_epoch: null,
    activation: { activated_epoch: 12, at_control_revision: 17 },
    conflict: null,
  },
});

const unusedPool: PostgresTransactionPool = Object.freeze({
  withTransaction: async () => {
    throw new Error("formation work authorization must not mint a production worker");
  },
});

const runtimeOptions = (pool: PostgresTransactionPool = unusedPool) => ({
  pool,
  project_id: PROJECT,
  runtime_mode: "deployed" as const,
  application_id: APP,
  context_ttl_seconds: 60,
  database_generation_digest: "d".repeat(64),
  id_token_adapter: {
    verification_source: "firebase_production" as const,
    verifyIdToken: async () => claims(),
  },
});

test("memories.work.accept and execute are distinct from memories.write", async () => {
  const accept = createPostgresFirebaseAuthorizationRuntime(runtimeOptions(), "memories.work.accept");
  const execute = createPostgresFirebaseAuthorizationRuntime(runtimeOptions(), "memories.work.execute");
  expect(Object.keys(accept)).toEqual(["pool", "authorizer"]);
  expect(Object.keys(execute)).toEqual(["pool", "authorizer"]);
  expect(() => createPostgresFirebaseAuthorizationRuntime(
    runtimeOptions(),
    "memories.work.dispatch" as never,
  )).toThrow("invalid PostgreSQL Firebase runtime capability");
});

test("memories.write never mints memories.work.accept", async () => {
  const controlLoads: string[] = [];
  const authorizer = composeFirebaseMemoryAuthorization({
    project_id: PROJECT,
    runtime_mode: "deployed",
    id_token_adapter: {
      verification_source: "firebase_production",
      verifyIdToken: async () => claims(),
    },
    authorization_source: {
      async load() {
        return authorization("memories.write");
      },
    },
    control_source: {
      async load(account) {
        controlLoads.push(account);
        return control();
      },
    },
    application_id: APP,
    capability: "memories.work.accept",
    context_ttl_seconds: 60,
  });
  expect(await authorizer.authorize("header.payload.signature", NOW)).toEqual({
    authorized: false,
    outcome: "authorization",
  });
  expect(controlLoads).toEqual([]);
});

test("revoked or missing memories.work.execute never mints execute", async () => {
  for (const authorizationResult of [
    authorization("memories.work.execute", { grant_lifecycle: "revoked" }),
    authorization("memories.work.accept"),
    { status: "absent" },
  ]) {
    const authorizer = composeFirebaseMemoryAuthorization({
      project_id: PROJECT,
      runtime_mode: "deployed",
      id_token_adapter: {
        verification_source: "firebase_production",
        verifyIdToken: async () => claims(),
      },
      authorization_source: {
        async load() {
          return authorizationResult;
        },
      },
      control_source: {
        async load() {
          throw new Error("must not reach control");
        },
      },
      application_id: APP,
      capability: "memories.work.execute",
      context_ttl_seconds: 60,
    });
    expect(await authorizer.authorize("header.payload.signature", NOW)).toEqual({
      authorized: false,
      outcome: "authorization",
    });
  }
});

test("production composition does not import or schedule the formation one-shot runtime", async () => {
  const app = await Bun.file(new URL("./firebase-authorized-memory-service-app.ts", import.meta.url)).text();
  const processSource = await Bun.file(new URL("./firebase-authorized-memory-service-process.ts", import.meta.url)).text();
  const production = await Bun.file(new URL("../../apps/service/bin/production-server.ts", import.meta.url)).text();
  const memoryApp = await Bun.file(new URL("../../apps/service/memory-service-app.ts", import.meta.url)).text();
  for (const source of [app, processSource, production, memoryApp]) {
    expect(source).not.toContain("formation-one-shot-runtime");
    expect(source).not.toContain("memories.work.accept");
    expect(source).not.toContain("memories.work.execute");
    expect(source).not.toContain("createPostgresFormationOneShotRuntime");
  }
});

test("a verified identity with no memories.work.accept grant is authorization, not a worker", async () => {
  const names: string[] = [];
  const pool: PostgresTransactionPool = {
    withTransaction: async (_options, callback) => callback({
      connectionIdentity: {},
      query: async (statement) => {
        names.push(statement.name);
        expect(statement.values).toContain("memories.work.accept");
        return [];
      },
      execute: async () => ({ rowCount: 0 }),
    }),
  };
  const runtime = createPostgresFirebaseAuthorizationRuntime(runtimeOptions(pool), "memories.work.accept");
  expect(await runtime.authorizer.authorize("header.payload.signature", NOW)).toEqual({
    authorized: false,
    outcome: "authorization",
  });
  expect(names).toEqual(["firebase_authorization.lookup_current"]);
});
