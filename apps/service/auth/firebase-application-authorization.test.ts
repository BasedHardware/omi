import { describe, expect, test } from "bun:test";

import { assertAuthorizedLedgerWriteContext } from "./authorized-context";
import {
  composeFirebaseApplicationAuthorization,
  type FirebaseApplicationAuthorizationConfig,
  type FirebaseApplicationAuthorizationSourceRequest,
} from "./firebase-application-authorization";

const NOW = 100;
const ACCOUNT = "account:alice";
const APP = "app:desktop";
const CAPABILITY = "memories.write";

const identity = (overrides: Record<string, unknown> = {}) => ({
  firebase_project_id: "omi-fixture-project",
  firebase_uid: "firebase-user-alice",
  authentication_strength: "firebase-id-token",
  expires_at_epoch_seconds: 400,
  ...overrides,
});

const authorizationRow = (overrides: Record<string, unknown> = {}) => ({
  status: "current",
  firebase_project_id: "omi-fixture-project",
  firebase_uid: "firebase-user-alice",
  principal_id: "principal:alice",
  account_id: ACCOUNT,
  application_id: APP,
  credential_id: "credential:desktop:one",
  credential_generation: 4,
  credential_lifecycle: "active",
  authentication_strength: "firebase-id-token",
  credential_expires_at_epoch_seconds: 300,
  capability: CAPABILITY,
  grant_id: "grant:memories:write",
  grant_version: 9,
  grant_lifecycle: "active",
  grant_enabled: true,
  authorization_state_digest: "a".repeat(64),
  control_revision: 17,
  account_epoch: 12,
  destination_activation_revision: 17,
  ...overrides,
});

const controlEnvelope = (overrides: Record<string, unknown> = {}) => ({
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
    ...overrides,
  },
});

const setup = (options: {
  readonly identityResult?: unknown;
  readonly authorizationResult?: unknown;
  readonly controlResult?: unknown;
  readonly identityThrow?: unknown;
  readonly authorizationThrow?: unknown;
  readonly controlThrow?: unknown;
  readonly ttl?: number;
} = {}) => {
  const order: string[] = [];
  const requests: FirebaseApplicationAuthorizationSourceRequest[] = [];
  const accounts: string[] = [];
  const identityVerifier = {
    async resolve(): Promise<unknown> {
      order.push("identity");
      if (options.identityThrow !== undefined) throw options.identityThrow;
      return Object.prototype.hasOwnProperty.call(options, "identityResult")
        ? options.identityResult
        : identity();
    },
  };
  const authorizationSource = {
    async load(request: FirebaseApplicationAuthorizationSourceRequest): Promise<unknown> {
      order.push("authorization");
      requests.push(request);
      if (options.authorizationThrow !== undefined) throw options.authorizationThrow;
      return Object.prototype.hasOwnProperty.call(options, "authorizationResult")
        ? options.authorizationResult
        : authorizationRow();
    },
  };
  const controlSource = {
    async load(accountId: string): Promise<unknown> {
      order.push("control");
      accounts.push(accountId);
      if (options.controlThrow !== undefined) throw options.controlThrow;
      return Object.prototype.hasOwnProperty.call(options, "controlResult")
        ? options.controlResult
        : controlEnvelope();
    },
  };
  const config: FirebaseApplicationAuthorizationConfig = {
    identity_verifier: identityVerifier as never,
    authorization_source: authorizationSource,
    control_source: controlSource,
    application_id: APP,
    capability: CAPABILITY,
    context_ttl_seconds: options.ttl ?? 60,
  };
  return {
    authorizer: composeFirebaseApplicationAuthorization(config),
    order,
    requests,
    accounts,
    dependencies: { identityVerifier, authorizationSource, controlSource },
  };
};

describe("single Firebase application-authorization composition", () => {
  test("verifies identity, exact grant, and coherent control once in order before minting", async () => {
    const fixture = setup();
    const result = await fixture.authorizer.authorize("header.payload.signature", NOW);
    expect(fixture.order).toEqual(["identity", "authorization", "control"]);
    expect(fixture.requests).toEqual([{
      firebase_project_id: "omi-fixture-project",
      firebase_uid: "firebase-user-alice",
      application_id: APP,
      capability: CAPABILITY,
    }]);
    expect(Object.isFrozen(fixture.requests[0])).toBe(true);
    expect(fixture.accounts).toEqual([ACCOUNT]);
    expect(result.authorized).toBe(true);
    if (!result.authorized) throw new Error("expected authorization");
    expect(result.outcome).toBe("authorized");
    expect(Object.isFrozen(result)).toBe(true);
    expect(assertAuthorizedLedgerWriteContext(result.context)).toBe(result.context);
    expect(result.context).toEqual({
      context_version: "authorized-ledger-write-context-v1",
      principal_id: "principal:alice",
      account_id: ACCOUNT,
      application_id: APP,
      credential_id: "credential:desktop:one",
      credential_generation: 4,
      capability: CAPABILITY,
      grant_id: "grant:memories:write",
      grant_version: 9,
      account_epoch: 12,
      destination_activation_revision: 17,
      lifecycle_state: "active",
      deletion_epoch: null,
      authentication_strength: "firebase-id-token",
      issued_at_epoch_seconds: NOW,
      expires_at_epoch_seconds: 160,
      authorization_state_digest: "a".repeat(64),
    });
  });

  test("context expiry is the minimum of token, credential, and configured lifetime", async () => {
    for (const [identityExpiry, credentialExpiry, ttl, expected] of [
      [120, 300, 60, 120],
      [400, 130, 60, 130],
      [400, null, 30, 130],
    ] as const) {
      const result = await setup({
        identityResult: identity({ expires_at_epoch_seconds: identityExpiry }),
        authorizationResult: authorizationRow({
          credential_expires_at_epoch_seconds: credentialExpiry,
        }),
        ttl,
      }).authorizer.authorize("header.payload.signature", NOW);
      expect(result.authorized).toBe(true);
      if (result.authorized) expect(result.context.expires_at_epoch_seconds).toBe(expected);
    }
  });

  test("authentication failure never asks for account, grant, or control state", async () => {
    for (const identityResult of [null, {}, identity({ expires_at_epoch_seconds: NOW })]) {
      const fixture = setup({ identityResult });
      expect(await fixture.authorizer.authorize("bad", NOW)).toEqual({
        authorized: false,
        outcome: "authentication",
      });
      expect(fixture.order).toEqual(["identity"]);
      expect(JSON.stringify(await fixture.authorizer.authorize("bad", -1))).not.toContain(ACCOUNT);
    }
  });

  test("absent or invalid authorization never asks the control source", async () => {
    const candidates: unknown[] = [
      { status: "absent" },
      { status: "current" },
      authorizationRow({ firebase_project_id: "other-project" }),
      authorizationRow({ firebase_uid: "other-user" }),
      authorizationRow({ principal_id: "bad principal" }),
      authorizationRow({ account_id: "" }),
      authorizationRow({ application_id: "app:other" }),
      authorizationRow({ capability: "memories.read" }),
      authorizationRow({ credential_lifecycle: "revoked" }),
      authorizationRow({ authentication_strength: "custom-claim" }),
      authorizationRow({ credential_expires_at_epoch_seconds: NOW }),
      authorizationRow({ grant_lifecycle: "revoked" }),
      authorizationRow({ grant_enabled: false }),
      authorizationRow({ authorization_state_digest: "not-a-digest" }),
      authorizationRow({ credential_generation: -1 }),
      authorizationRow({ grant_version: Number.MAX_SAFE_INTEGER + 1 }),
    ];
    for (const authorizationResult of candidates) {
      const fixture = setup({ authorizationResult });
      const result = await fixture.authorizer.authorize("header.payload.signature", NOW);
      expect(result).toEqual({ authorized: false, outcome: "authorization" });
      expect(fixture.order).toEqual(["identity", "authorization"]);
      expect(JSON.stringify(result)).not.toContain(ACCOUNT);
    }
  });

  test("source failures are unavailable and never expose raw details", async () => {
    const sentinel = `raw-provider-${ACCOUNT}`;
    for (const fixture of [
      setup({ authorizationThrow: new Error(sentinel) }),
      setup({ controlThrow: new Error(sentinel) }),
    ]) {
      const result = await fixture.authorizer.authorize("header.payload.signature", NOW);
      expect(result).toEqual({ authorized: false, outcome: "unavailable" });
      expect(JSON.stringify(result)).not.toContain(sentinel);
      expect(JSON.stringify(result)).not.toContain(ACCOUNT);
    }
  });

  test("control freshness and exact snapshot disagreement stay distinct", async () => {
    for (const [controlResult, authorizationResult, outcome] of [
      [{ status: "stale" }, authorizationRow(), "stale_epoch"],
      [{ status: "unavailable" }, authorizationRow(), "unavailable"],
      [controlEnvelope(), authorizationRow({ control_revision: 16 }), "stale_epoch"],
      [controlEnvelope(), authorizationRow({ account_epoch: 11 }), "stale_epoch"],
      [controlEnvelope(), authorizationRow({ destination_activation_revision: 16 }), "stale_epoch"],
      [controlEnvelope({ account_generation: "migrating", activation: null }), authorizationRow(), "authorization"],
      [controlEnvelope({ lifecycle_state: "deletion_pending", deletion_epoch: 13 }), authorizationRow(), "authorization"],
      [controlEnvelope({ lifecycle_state: "deleted", deletion_epoch: 13 }), authorizationRow(), "authorization"],
      [controlEnvelope({ conflict: { at_control_revision: 17, detail: "conflicting_observation" } }), authorizationRow(), "authorization"],
    ] as const) {
      const result = await setup({ controlResult, authorizationResult }).authorizer
        .authorize("header.payload.signature", NOW);
      expect(result).toEqual({ authorized: false, outcome });
      expect(JSON.stringify(result)).not.toContain(ACCOUNT);
    }
  });

  test("hostile source data is authorization denial without invoking accessors", async () => {
    let getterCalls = 0;
    const hostile = authorizationRow();
    Object.defineProperty(hostile, "principal_id", {
      enumerable: true,
      get: () => { getterCalls += 1; return "principal:alice"; },
    });
    for (const authorizationResult of [
      hostile,
      new Proxy(authorizationRow(), {}),
      { ...authorizationRow(), extra: true },
    ]) {
      const result = await setup({ authorizationResult }).authorizer
        .authorize("header.payload.signature", NOW);
      expect(result).toEqual({ authorized: false, outcome: "authorization" });
    }
    expect(getterCalls).toBe(0);
  });

  test("construction snapshots dependencies and later source mutation cannot retarget authority", async () => {
    const fixture = setup();
    fixture.dependencies.authorizationSource.load = async () => authorizationRow({ account_id: "account:bob" });
    fixture.dependencies.controlSource.load = async () => ({ status: "absent" });
    fixture.dependencies.identityVerifier.resolve = async () => identity({ firebase_uid: "firebase-user-bob" });
    const result = await fixture.authorizer.authorize("header.payload.signature", NOW);
    expect(result.authorized).toBe(true);
    if (result.authorized) expect(result.context.account_id).toBe(ACCOUNT);
  });

  test("configuration and clocks are bounded before dependency work", async () => {
    const valid = setup();
    expect(await valid.authorizer.authorize("header.payload.signature", -1)).toEqual({
      authorized: false,
      outcome: "authentication",
    });
    expect(valid.order).toEqual([]);

    const base = {
      identity_verifier: { resolve: async () => identity() },
      authorization_source: { load: async () => authorizationRow() },
      control_source: { load: async () => controlEnvelope() },
      application_id: APP,
      capability: CAPABILITY,
      context_ttl_seconds: 60,
    };
    for (const candidate of [
      { ...base, context_ttl_seconds: 0 },
      { ...base, context_ttl_seconds: 301 },
      { ...base, application_id: "bad app" },
      { ...base, capability: "" },
      { ...base, extra: true },
      new Proxy(base, {}),
    ]) expect(() => composeFirebaseApplicationAuthorization(candidate as never)).toThrow(
      "invalid Firebase application authorization configuration",
    );

    let getterCalls = 0;
    const accessor = Object.create(Object.prototype, {
      identity_verifier: { enumerable: true, get: () => { getterCalls += 1; return base.identity_verifier; } },
      authorization_source: { enumerable: true, value: base.authorization_source },
      control_source: { enumerable: true, value: base.control_source },
      application_id: { enumerable: true, value: APP },
      capability: { enumerable: true, value: CAPABILITY },
      context_ttl_seconds: { enumerable: true, value: 60 },
    });
    expect(() => composeFirebaseApplicationAuthorization(accessor)).toThrow("invalid Firebase");
    expect(getterCalls).toBe(0);
  });

  test("a copied visible context cannot forge the runtime mint", async () => {
    const result = await setup().authorizer.authorize("header.payload.signature", NOW);
    if (!result.authorized) throw new Error("expected authorization");
    expect(() => assertAuthorizedLedgerWriteContext({ ...result.context }))
      .toThrow("not issued by auth composition");
  });

  test("the composition imports no route, persistence, SDK, model, environment, or secret module", async () => {
    const source = await Bun.file(new URL("./firebase-application-authorization.ts", import.meta.url)).text();
    for (const forbidden of [
      "apps/service/routes",
      "drivers/postgres",
      "drivers/sqlite",
      "firebase-admin",
      "drivers/model",
      "process.env",
      "node:fs",
    ]) expect(source).not.toContain(forbidden);
  });
});
