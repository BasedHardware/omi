import { describe, expect, test } from "bun:test";

import type { FirebaseAuthorizedMemoryReadOutcome } from
  "./firebase-authorized-memory-read-runtime";
import { createPostgresFirebaseMemoryRouteReadPort } from
  "./firebase-memory-route-read-port";

const request = Object.freeze({
  bearer_token: "firebase-token",
  now_epoch_seconds: 123,
  request: Object.freeze({ limit: 7, cursor: null }),
});

describe("PostgreSQL Firebase memory route port", () => {
  for (const [runtimeOutcome, routeOutcome] of [
    [{ kind: "denied", outcome: "authentication" }, { kind: "authentication_denied" }],
    [{ kind: "denied", outcome: "authorization" }, { kind: "authorization_denied" }],
    [{ kind: "denied", outcome: "stale_epoch" }, { kind: "authorization_denied" }],
    [{ kind: "denied", outcome: "unavailable" }, { kind: "unavailable" }],
    [{ kind: "invalid_cursor" }, { kind: "invalid_cursor" }],
    [{ kind: "invalidated" }, { kind: "unavailable" }],
    [{ kind: "unavailable" }, { kind: "unavailable" }],
    [{ kind: "loaded", canonical_json: "{}" }, { kind: "loaded", canonical_json: "{}" }],
  ] as const) {
    test(`maps ${runtimeOutcome.kind}${"outcome" in runtimeOutcome ? `:${runtimeOutcome.outcome}` : ""}`, async () => {
      const seen: unknown[] = [];
      const port = createPostgresFirebaseMemoryRouteReadPort({
        authenticate: async (...args) => {
          seen.push(["authenticate", ...args]);
          return true;
        },
        read: async (...args) => {
          seen.push(["read", ...args]);
          return runtimeOutcome as FirebaseAuthorizedMemoryReadOutcome;
        },
      });
      await expect(port.authenticate({
        bearer_token: "firebase-token",
        now_epoch_seconds: 123,
      })).resolves.toBe(true);
      await expect(port.read(request)).resolves.toEqual(routeOutcome);
      expect(seen).toEqual([
        ["authenticate", "firebase-token", 123],
        ["read", "firebase-token", 123, { limit: 7, cursor: null }],
      ]);
    });
  }

  test("captures the runtime method once and rejects accessor/proxy runtimes", async () => {
    let first = 0;
    const runtime = {
      authenticate: async () => true,
      read: async () => { first += 1; return { kind: "unavailable" } as const; },
    };
    const port = createPostgresFirebaseMemoryRouteReadPort(runtime);
    runtime.read = async () => ({ kind: "loaded", canonical_json: "secret" }) as const;
    await expect(port.read(request)).resolves.toEqual({ kind: "unavailable" });
    expect(first).toBe(1);

    let getters = 0;
    const accessor = Object.defineProperty({}, "read", {
      enumerable: true,
      get() { getters += 1; return async () => ({ kind: "unavailable" }); },
    });
    Object.defineProperty(accessor, "authenticate", {
      enumerable: true,
      value: async () => true,
    });
    expect(() => createPostgresFirebaseMemoryRouteReadPort(accessor as never)).toThrow();
    expect(getters).toBe(0);
    expect(() => createPostgresFirebaseMemoryRouteReadPort(new Proxy(runtime, {}) as never)).toThrow();
  });
});
