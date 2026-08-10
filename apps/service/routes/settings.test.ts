// domain-pending(UNK-DOMAPPS-001)
import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { Hono } from "hono";

import { createLocalService } from "../app-facing";
import { createInMemorySettingsProjectionStore } from "../control/settings-projection";
import { createServedCounter } from "../observability/served-count";
import { registerSettingsRoutes } from "./settings";

const TOKEN = "valid-token";
const principal = Object.freeze({ uid: "account-a" });

const service = (options: {
  readonly projections?: ReturnType<typeof createInMemorySettingsProjectionStore>;
  readonly resolvePrincipal?: (token: string) => typeof principal | null;
} = {}) => {
  const app = new Hono({ strict: true });
  const counter = createServedCounter();
  registerSettingsRoutes(app, {
    projections: options.projections ?? createInMemorySettingsProjectionStore(),
    resolvePrincipal: options.resolvePrincipal ?? ((token) => token === TOKEN ? principal : null),
    counter,
  });
  return { app, counter };
};

const authorization = (token = TOKEN): HeadersInit => ({ authorization: `Bearer ${token}` });

describe("GET /v1/settings", () => {
  test("is registered by the real composition root", async () => {
    const db = new Database(":memory:");
    const local = createLocalService({
      db,
      ownerAccountId: "account-a",
      memoryCount: 1,
      accountTimezone: "UTC",
      devSecretLabel: "settings-composition-test",
    });

    const result = await local.app.request("/v1/settings", {
      headers: authorization(local.devToken),
    });
    expect(result.status).toBe(200);
    expect(await result.json()).toEqual({
      identity: { displayName: "account-a", email: "" },
      entitlement: null,
    });
    db.close();
  });

  test("proves no credential is signed-out 200 while each presented bad credential is 401", async () => {
    let resolveCalls = 0;
    const { app } = service({
      resolvePrincipal: (token) => {
        resolveCalls += 1;
        return token === TOKEN ? principal : null;
      },
    });

    const absent = await app.request("/v1/settings");
    expect(absent.status).toBe(200);
    expect(await absent.text()).toBe('{"identity":null,"entitlement":null}');
    expect(resolveCalls).toBe(0);

    for (const value of ["", "Basic nope", "Bearer ", "Bearer invalid"]) {
      const invalid = await app.request("/v1/settings", {
        headers: { authorization: value },
      });
      expect(invalid.status).toBe(401);
      expect(await invalid.text()).toBe('{"error":"unauthorized"}');
    }
    expect(resolveCalls).toBe(1);
  });

  test("an empty-string identity renders as an object, never null", async () => {
    const projections = createInMemorySettingsProjectionStore();
    projections.putIdentity("account-a", { displayName: "", email: "" });
    const { app } = service({ projections });

    const result = await app.request("/v1/settings", { headers: authorization() });
    expect(result.status).toBe(200);
    expect(await result.json()).toEqual({
      identity: { displayName: "", email: "" },
      entitlement: null,
    });
  });

  test("entitlement null and unmetered limit null remain distinct on the wire", async () => {
    const absent = createInMemorySettingsProjectionStore();
    absent.putIdentity("account-a", { displayName: "A", email: "a@example.invalid" });
    const absentResponse = await service({ projections: absent }).app.request(
      "/v1/settings",
      { headers: authorization() },
    );
    expect(await absentResponse.json()).toEqual({
      identity: { displayName: "A", email: "a@example.invalid" },
      entitlement: null,
    });

    const unmetered = createInMemorySettingsProjectionStore();
    unmetered.putIdentity("account-a", { displayName: "A", email: "a@example.invalid" });
    unmetered.putEntitlement("account-a", {
      planLabel: "Omi Plus",
      limitKey: "memories",
      used: 7,
      limit: null,
      limitReached: false,
      upgradeAvailable: true,
    });
    const unmeteredResponse = await service({ projections: unmetered }).app.request(
      "/v1/settings",
      { headers: authorization() },
    );
    expect(await unmeteredResponse.json()).toEqual({
      identity: { displayName: "A", email: "a@example.invalid" },
      entitlement: {
        planLabel: "Omi Plus",
        limitKey: "memories",
        used: 7,
        limit: null,
        limitReached: false,
        upgradeAvailable: true,
      },
    });
  });

  test("entitlement-source failure blacks out the whole read with fixed 503", async () => {
    const sourceFailure = createInMemorySettingsProjectionStore();
    sourceFailure.putIdentity("account-a", {
      displayName: "Private",
      email: "private@example.invalid",
    });
    const originalRead = sourceFailure.readSettings.bind(sourceFailure);
    const { app } = service({
      projections: Object.freeze({
        ...sourceFailure,
        readSettings: (accountId: string) => {
          void originalRead(accountId);
          throw new Error("entitlement source leaked detail");
        },
      }),
    });

    const result = await app.request("/v1/settings", { headers: authorization() });
    const body = await result.text();
    expect(result.status).toBe(503);
    expect(result.headers.get("retry-after")).toBe("60");
    expect(body).toBe('{"error":"service_unavailable"}');
    expect(body).not.toContain("private@example.invalid");
    expect(body).not.toContain("entitlement source leaked detail");
  });

  test("rejects every query and does not add shell-local appearance", async () => {
    const projections = createInMemorySettingsProjectionStore();
    projections.putIdentity("account-a", { displayName: "A", email: "" });
    const { app } = service({ projections });

    for (const query of ["?unknown=1", "?x=1&x=2", "?appearance=dark"]) {
      const result = await app.request(`/v1/settings${query}`, { headers: authorization() });
      expect(result.status).toBe(400);
      expect(await result.text()).toBe('{"error":"bad_request"}');
    }
    const valid = await app.request("/v1/settings", { headers: authorization() });
    expect(await valid.text()).not.toContain("appearance");
  });
});
