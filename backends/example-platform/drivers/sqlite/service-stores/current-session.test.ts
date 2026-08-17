import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { SqliteCurrentSessionPort } from "./current-session";

describe("SQLite current-session adapter", () => {
  test("persists exact revocation and recognizes replay after reopen", () => {
    const path = `/tmp/current-session-${process.pid}-${Date.now()}.sqlite`;
    const resolve = (token: string) => token === "session-a" || token === "session-b"
      ? Object.freeze({ uid: "account" })
      : null;
    const firstDb = new Database(path, { create: true });
    const first = new SqliteCurrentSessionPort(firstDb);
    expect(first.revoke("session-a", resolve)).toEqual({ status: "revoked" });
    firstDb.close();

    const secondDb = new Database(path);
    const second = new SqliteCurrentSessionPort(secondDb);
    expect(second.authenticate("session-a", resolve)).toBeNull();
    expect(second.authenticate("session-b", resolve)).toEqual({ uid: "account" });
    expect(second.revoke("session-a", resolve)).toEqual({ status: "already_revoked" });
    expect(secondDb.query("SELECT token_digest FROM service_dev_token_revocations").get())
      .toEqual({ token_digest: expect.stringMatching(/^[0-9a-f]{64}$/) });
    secondDb.close();
  });
});
