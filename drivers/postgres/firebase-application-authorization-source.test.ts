import { describe, expect, test } from "bun:test";

import { composeFirebaseApplicationAuthorization } from "../../apps/service/auth/firebase-application-authorization";
import {
  createPostgresFirebaseApplicationAuthorizationSource,
  LOOKUP_FIREBASE_APPLICATION_AUTHORIZATION,
  type FirebaseApplicationAuthorizationQueryPort,
} from "./firebase-application-authorization-source";
import type { SqlStatement } from "./connection";
import { authorizationStateDigest, type AuthorityStateRow } from "./transaction";

const request = (overrides: Record<string, unknown> = {}) => ({
  firebase_project_id: "omi-fixture-project",
  firebase_uid: "firebase-user-alice",
  application_id: "app:desktop",
  capability: "memories.write",
  ...overrides,
});

const row = (overrides: Record<string, unknown> = {}) => ({
  firebase_project_id: "omi-fixture-project",
  firebase_uid: "firebase-user-alice",
  principal_id: "principal:alice",
  account_id: "account:alice",
  application_id: "app:desktop",
  credential_id: "credential:desktop:one",
  credential_generation: 4,
  credential_lifecycle: "active",
  authentication_strength: "firebase-id-token",
  credential_expires_at_epoch_seconds: 300,
  capability: "memories.write",
  grant_id: "grant:memories:write",
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
  ...overrides,
});

const expectedDigest = (): string => authorizationStateDigest({
  account_id: "account:alice",
  principal_id: "principal:alice",
  application_id: "app:desktop",
  credential_id: "credential:desktop:one",
  credential_generation: 4,
  capability: "memories.write",
  grant_id: "grant:memories:write",
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
  credential_expires_at_epoch_seconds: 300,
  control_revision: 17,
  control_content_hash: "1".repeat(64),
  credential_content_hash: "2".repeat(64),
  grant_content_hash: "3".repeat(64),
  db_now_epoch_seconds: 0,
} satisfies AuthorityStateRow);

const setup = (result: unknown = [row()]) => {
  const statements: SqlStatement[] = [];
  const queryPort = {
    async query(statement: SqlStatement): Promise<readonly Record<string, unknown>[]> {
      statements.push(statement);
      if (result instanceof Error) throw result;
      return result as readonly Record<string, unknown>[];
    },
  } satisfies FirebaseApplicationAuthorizationQueryPort;
  return {
    source: createPostgresFirebaseApplicationAuthorizationSource(queryPort),
    statements,
    queryPort,
  };
};

describe("PostgreSQL Firebase application authorization source", () => {
  test("binds only the verified external identity and fixed application capability", async () => {
    const fixture = setup();
    const result = await fixture.source.load(request());
    expect(fixture.statements).toEqual([{
      name: "firebase_authorization.lookup_current",
      text: LOOKUP_FIREBASE_APPLICATION_AUTHORIZATION,
      values: [
        "omi-fixture-project",
        "firebase-user-alice",
        "app:desktop",
        "memories.write",
      ],
    }]);
    expect(Object.isFrozen(fixture.statements[0])).toBe(true);
    expect(Object.isFrozen(fixture.statements[0]!.values)).toBe(true);
    expect(result).toEqual({
      status: "current",
      firebase_project_id: "omi-fixture-project",
      firebase_uid: "firebase-user-alice",
      principal_id: "principal:alice",
      account_id: "account:alice",
      application_id: "app:desktop",
      credential_id: "credential:desktop:one",
      credential_generation: 4,
      credential_lifecycle: "active",
      authentication_strength: "firebase-id-token",
      credential_expires_at_epoch_seconds: 300,
      capability: "memories.write",
      grant_id: "grant:memories:write",
      grant_version: 9,
      grant_lifecycle: "active",
      grant_enabled: true,
      authorization_state_digest: expectedDigest(),
      control_revision: 17,
      account_epoch: 12,
      destination_activation_revision: 17,
    });
    expect(Object.isFrozen(result)).toBe(true);
  });

  test("structurally composes into the single authorization path without another lookup", async () => {
    const fixture = setup();
    const authorizer = composeFirebaseApplicationAuthorization({
      identity_verifier: {
        async resolve(_token: string, _nowEpochSeconds: number) {
          return Object.freeze({
            firebase_project_id: "omi-fixture-project",
            firebase_uid: "firebase-user-alice",
            authentication_strength: "firebase-id-token" as const,
            expires_at_epoch_seconds: 400,
          });
        },
      },
      authorization_source: fixture.source,
      control_source: {
        async load(): Promise<unknown> {
          return {
            status: "current",
            projection: {
              account_id: "account:alice",
              control_revision: 17,
              account_generation: "new",
              account_epoch: 12,
              lifecycle_state: "active",
              deletion_epoch: null,
              activation: { activated_epoch: 12, at_control_revision: 17 },
              conflict: null,
            },
          };
        },
      },
      application_id: "app:desktop",
      capability: "memories.write",
      context_ttl_seconds: 60,
    });
    const result = await authorizer.authorize("header.payload.signature", 100);
    expect(result.authorized).toBe(true);
    if (!result.authorized) throw new Error("expected authorization");
    expect(result.context.authorization_state_digest).toBe(expectedDigest());
    expect(fixture.statements).toHaveLength(1);
  });

  test("project and uid are separate exact lookup coordinates", async () => {
    for (const [overrides, expected] of [
      [{ firebase_project_id: "other-project" }, ["other-project", "firebase-user-alice"]],
      [{ firebase_uid: "firebase-user-bob" }, ["omi-fixture-project", "firebase-user-bob"]],
    ] as const) {
      const fixture = setup([row(overrides)]);
      expect((await fixture.source.load(request(overrides)) as { status: string }).status).toBe("current");
      expect(fixture.statements[0]!.values.slice(0, 2)).toEqual([...expected]);
    }
  });

  test("zero rows is absent while multiple or malformed rows are unavailable", async () => {
    expect(await setup([]).source.load(request())).toEqual({ status: "absent" });
    expect(await setup([row(), row()]).source.load(request())).toEqual({ status: "unavailable" });
    for (const result of [
      [row({ firebase_project_id: "other-project" })],
      [row({ firebase_uid: "other-user" })],
      [row({ application_id: "app:other" })],
      [row({ capability: "memories.read" })],
      [row({ control_content_hash: "bad" })],
      [row({ credential_generation: Number.MAX_SAFE_INTEGER + 1 })],
      [row({ lifecycle_state: "active", deletion_epoch: 4 })],
      [{ ...row(), extra: true }],
      Object.assign([row()], { extra: true }),
      new Proxy([row()], {}),
    ]) expect(await setup(result).source.load(request())).toEqual({ status: "unavailable" });
  });

  test("valid inactive and non-new authority remains detached for the composition to deny", async () => {
    const result = await setup([row({
      credential_lifecycle: "revoked",
      grant_lifecycle: "inactive",
      grant_enabled: false,
      account_epoch: null,
      destination_activation_revision: null,
      destination_activation_epoch: null,
      lifecycle_state: "deletion_pending",
      deletion_epoch: 13,
      account_generation: "legacy",
    })]).source.load(request()) as Record<string, unknown>;
    expect(result.status).toBe("current");
    expect(result.credential_lifecycle).toBe("revoked");
    expect(result.account_epoch).toBeNull();
    expect(result).not.toHaveProperty("lifecycle_state");
  });

  test("accessors, proxies, classes, extras, and invalid requests never reach authority", async () => {
    let getterCalls = 0;
    let queryCalls = 0;
    const hostile = row();
    Object.defineProperty(hostile, "account_id", {
      enumerable: true,
      get: () => { getterCalls += 1; return "account:alice"; },
    });
    const queryPort = {
      async query(): Promise<readonly Record<string, unknown>[]> {
        queryCalls += 1;
        return [hostile];
      },
    };
    const source = createPostgresFirebaseApplicationAuthorizationSource(queryPort);
    expect(await source.load(request())).toEqual({ status: "unavailable" });
    expect(getterCalls).toBe(0);
    expect(queryCalls).toBe(1);

    class RequestClass {
      firebase_project_id = "omi-fixture-project";
      firebase_uid = "firebase-user-alice";
      application_id = "app:desktop";
      capability = "memories.write";
    }
    for (const candidate of [
      { ...request(), extra: true },
      new Proxy(request(), {}),
      new RequestClass(),
      request({ firebase_uid: "bad\u0000uid" }),
    ]) expect(await source.load(candidate)).toEqual({ status: "unavailable" });
    expect(queryCalls).toBe(1);
  });

  test("query failure is closed and contains no provider or account bytes", async () => {
    const sentinel = "raw-provider-account:alice";
    const result = await setup(new Error(sentinel)).source.load(request());
    expect(result).toEqual({ status: "unavailable" });
    expect(JSON.stringify(result)).not.toContain(sentinel);
    expect(JSON.stringify(result)).not.toContain("account:alice");
  });

  test("construction and returned values snapshot their dependencies", async () => {
    const raw = row();
    const fixture = setup([raw]);
    fixture.queryPort.query = async () => [row({ account_id: "account:bob" })];
    const result = await fixture.source.load(request()) as Record<string, unknown>;
    raw.account_id = "account:bob";
    expect(result.account_id).toBe("account:alice");
    expect(fixture.statements).toHaveLength(1);
  });

  test("construction rejects non-plain or expanding query capabilities", () => {
    class QueryClass {
      async query(): Promise<readonly Record<string, unknown>[]> { return []; }
    }
    for (const candidate of [
      new QueryClass(),
      { query: async () => [], extra: true },
      new Proxy({ query: async () => [] }, {}),
    ]) expect(() => createPostgresFirebaseApplicationAuthorizationSource(candidate as never))
      .toThrow("invalid Firebase authorization query port");
  });

  test("the adapter imports no routes, SDK, environment, model, secret, or context issuer", async () => {
    const source = await Bun.file(
      new URL("./firebase-application-authorization-source.ts", import.meta.url),
    ).text();
    for (const forbidden of [
      "apps/service/routes",
      "firebase-admin",
      "process.env",
      "node:fs",
      "drivers/model",
      "authorized-context-internal",
      "credential.json",
    ]) expect(source).not.toContain(forbidden);
  });
});
