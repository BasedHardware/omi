import { describe, expect, test } from "bun:test";

import { createInMemoryCurrentSessionPort, digestSessionHandle } from "./current-session";

describe("in-memory current-session revocation", () => {
  test("revokes only the presented token and returns replay as already revoked", () => {
    const sessions = createInMemoryCurrentSessionPort();
    const resolve = (token: string) => token === "session-a" || token === "session-b"
      ? Object.freeze({ uid: "account" })
      : null;

    expect(sessions.authenticate("session-a", resolve)).toEqual({ uid: "account" });
    expect(sessions.revoke("session-a", resolve)).toEqual({ status: "revoked" });
    expect(sessions.authenticate("session-a", resolve)).toBeNull();
    expect(sessions.authenticate("session-b", resolve)).toEqual({ uid: "account" });
    expect(sessions.revoke("session-a", resolve)).toEqual({ status: "already_revoked" });
    expect(sessions.revoke("never-issued", resolve)).toEqual({ status: "unrecognized" });
  });

  test("stores a fixed one-way session handle representation", () => {
    expect(digestSessionHandle("session-a")).toMatch(/^[0-9a-f]{64}$/);
    expect(digestSessionHandle("session-a")).not.toContain("session-a");
    expect(digestSessionHandle("session-a")).not.toBe(digestSessionHandle("session-b"));
  });
});
