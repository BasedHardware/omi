import { describe, expect, test } from "bun:test";

import { assertAuthorizedLedgerWriteContext } from "../auth/authorized-context";
import { composeFirebaseMemoryAuthorization } from "./firebase-memory-authorization";

const NOW = 100;
const PROJECT = "omi-fixture-project";
const ACCOUNT = "account:alice";
const APP = "app:desktop";
const CAPABILITY = "memories.write";

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

const authorization = (overrides: Record<string, unknown> = {}) => ({
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
  capability: CAPABILITY,
  grant_id: "grant:memories:write",
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

const control = (overrides: Record<string, unknown> = {}) => ({
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
  readonly decoded?: unknown;
  readonly verification_source?: "firebase_production" | "firebase_auth_emulator";
} = {}) => {
  const order: string[] = [];
  const revoked: boolean[] = [];
  const requests: unknown[] = [];
  const accounts: string[] = [];
  const adapter = {
    verification_source: options.verification_source ?? "firebase_production" as const,
    async verifyIdToken(_token: string, checkRevoked: true): Promise<unknown> {
      order.push("identity");
      revoked.push(checkRevoked);
      return Object.prototype.hasOwnProperty.call(options, "decoded") ? options.decoded : claims();
    },
  };
  const authorizationSource = {
    async load(request: unknown): Promise<unknown> {
      order.push("authorization");
      requests.push(request);
      return authorization();
    },
  };
  const controlSource = {
    async load(account: string): Promise<unknown> {
      order.push("control");
      accounts.push(account);
      return control();
    },
  };
  const authorizer = composeFirebaseMemoryAuthorization({
    project_id: PROJECT,
    runtime_mode: "deployed",
    id_token_adapter: adapter,
    authorization_source: authorizationSource,
    control_source: controlSource,
    application_id: APP,
    capability: CAPABILITY,
    context_ttl_seconds: 60,
  });
  return { authorizer, adapter, authorizationSource, controlSource, order, revoked, requests, accounts };
};

describe("Firebase identity to application authorization composition", () => {
  test("checks identity, fixed application grant, and coherent epoch in order before minting", async () => {
    const fixture = setup();
    const result = await fixture.authorizer.authorize("header.payload.signature", NOW);
    expect(fixture.order).toEqual(["identity", "authorization", "control"]);
    expect(fixture.revoked).toEqual([true]);
    expect(fixture.requests).toEqual([{
      firebase_project_id: PROJECT,
      firebase_uid: "firebase-user-alice",
      application_id: APP,
      capability: CAPABILITY,
    }]);
    expect(fixture.accounts).toEqual([ACCOUNT]);
    expect(result.authorized).toBe(true);
    if (!result.authorized) throw new Error("expected authorization");
    expect(assertAuthorizedLedgerWriteContext(result.context)).toBe(result.context);
    expect(result.context).toMatchObject({
      principal_id: "principal:alice",
      account_id: ACCOUNT,
      application_id: APP,
      capability: CAPABILITY,
      account_epoch: 12,
      destination_activation_revision: 17,
      expires_at_epoch_seconds: 160,
    });
    expect(Object.keys(fixture.authorizer)).toEqual(["authorize"]);
  });

  test("invalid identity never reaches authorization or control", async () => {
    for (const decoded of [
      claims({ aud: "other-project" }),
      claims({ uid: "different-user" }),
      claims({ exp: NOW }),
      claims({ iat: NOW + 1 }),
    ]) {
      const fixture = setup({ decoded });
      expect(await fixture.authorizer.authorize("header.payload.signature", NOW)).toEqual({
        authorized: false,
        outcome: "authentication",
      });
      expect(fixture.order).toEqual(["identity"]);
    }
  });

  test("deployed mode refuses an emulator adapter at construction", () => {
    expect(() => setup({ verification_source: "firebase_auth_emulator" }))
      .toThrow("deployed Firebase identity forbids the Auth emulator");
  });

  test("construction snapshots nested dependency methods", async () => {
    const fixture = setup();
    fixture.adapter.verifyIdToken = async () => claims({ sub: "firebase-user-bob", uid: "firebase-user-bob" });
    fixture.authorizationSource.load = async () => authorization({ account_id: "account:bob" });
    fixture.controlSource.load = async () => ({ status: "absent" });
    const result = await fixture.authorizer.authorize("header.payload.signature", NOW);
    expect(result.authorized).toBe(true);
    if (result.authorized) expect(result.context.account_id).toBe(ACCOUNT);
  });

  test("hostile outer configuration fails without invoking accessors", () => {
    const fixture = setup();
    const base = {
      project_id: PROJECT,
      runtime_mode: "deployed" as const,
      id_token_adapter: fixture.adapter,
      authorization_source: fixture.authorizationSource,
      control_source: fixture.controlSource,
      application_id: APP,
      capability: CAPABILITY,
      context_ttl_seconds: 60,
    };
    for (const candidate of [{ ...base, extra: true }, new Proxy(base, {})]) {
      expect(() => composeFirebaseMemoryAuthorization(candidate as never))
        .toThrow("invalid Firebase memory authorization composition");
    }
    let getters = 0;
    const accessor = Object.create(Object.prototype, Object.fromEntries(
      Object.entries(base).map(([key, value]) => [key, key === "project_id"
        ? { enumerable: true, get: () => { getters += 1; return value; } }
        : { enumerable: true, value }]),
    ));
    expect(() => composeFirebaseMemoryAuthorization(accessor)).toThrow("invalid Firebase");
    expect(getters).toBe(0);
  });

  test("composition source imports no driver, route, environment, database, model, or issuer", async () => {
    const source = await Bun.file(new URL("./firebase-memory-authorization.ts", import.meta.url)).text();
    for (const forbidden of [
      "drivers/", "routes/", "process.env", "firebase-admin", "postgres", "sqlite",
      "drivers/model", "authorized-context-internal",
    ]) expect(source).not.toContain(forbidden);
  });
});
