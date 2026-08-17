import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";
import { Hono } from "hono";

import { createLocalDevService } from "../app-facing";
import { createInMemoryCurrentSessionPort } from "../auth/current-session";
import { registerCurrentSessionRoutes } from "./current-session";

const resolve = (token: string) => token === "valid"
  ? Object.freeze({ uid: "account-a" })
  : null;

const service = (sessions = createInMemoryCurrentSessionPort()) => {
  const app = new Hono({ strict: true });
  registerCurrentSessionRoutes(app, { sessions, resolveDevToken: resolve });
  return app;
};

const authorization = (token = "valid"): HeadersInit => ({ authorization: `Bearer ${token}` });

describe("DELETE /v1/session/current", () => {
  test("returns 204 for first revocation and replay, with empty no-store responses", async () => {
    const app = service();
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const result = await app.request("/v1/session/current", {
        method: "DELETE",
        headers: authorization(),
      });
      expect(result.status).toBe(204);
      expect(result.headers.get("cache-control")).toBe("no-store");
      expect(result.headers.get("content-type")).toBeNull();
      expect(await result.text()).toBe("");
    }
  });

  test("returns the same 401 for absent, malformed, and unrecognized credentials", async () => {
    const app = service();
    for (const value of [undefined, "", "Basic nope", "Bearer ", "Bearer invalid"]) {
      const result = await app.request("/v1/session/current", {
        method: "DELETE",
        headers: value === undefined ? undefined : { authorization: value },
      });
      expect(result.status).toBe(401);
      expect(await result.text()).toBe('{"error":"unauthorized"}');
    }
  });

  test("rejects every query and any request body", async () => {
    const app = service();
    const query = await app.request("/v1/session/current?all=true", {
      method: "DELETE",
      headers: authorization(),
    });
    expect(query.status).toBe(400);
    expect(await query.text()).toBe('{"error":"bad_request"}');

    const body = await app.request("/v1/session/current", {
      method: "DELETE",
      headers: authorization(),
      body: "{}",
    });
    expect(body.status).toBe(400);
    expect(await body.text()).toBe('{"error":"bad_request"}');
  });

  test("returns fixed retryable 503 when revocation cannot be recorded", async () => {
    const app = service(Object.freeze({
      authenticate: () => null,
      revoke: () => { throw new Error("revocation database secret"); },
    }));
    const result = await app.request("/v1/session/current", {
      method: "DELETE",
      headers: authorization(),
    });
    const body = await result.text();
    expect(result.status).toBe(503);
    expect(result.headers.get("retry-after")).toBe("60");
    expect(body).toBe('{"error":"service_unavailable"}');
    expect(body).not.toContain("revocation database secret");
  });

  test("the real composition rejects later app-facing use and accepts sign-out replay", async () => {
    const db = new Database(":memory:");
    const local = createLocalDevService({
      db,
      ownerAccountId: "account-a",
      memoryCount: 1,
      accountTimezone: "UTC",
      devSecretLabel: "current-session-composition-test",
    });
    const headers = authorization(local.devToken);

    const first = await local.app.request("/v1/session/current", { method: "DELETE", headers });
    expect(first.status).toBe(204);
    const laterUse = await local.app.request("/v1/settings", { headers });
    expect(laterUse.status).toBe(401);
    expect(await laterUse.text()).toBe('{"error":"unauthorized"}');
    const replay = await local.app.request("/v1/session/current", { method: "DELETE", headers });
    expect(replay.status).toBe(204);
    db.close();
  });
});
