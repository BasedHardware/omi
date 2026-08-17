// domain-pending(UNK-DOMAPPS-001)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { SqliteSettingsProjectionStore } from "./settings-projection";

const unmetered = Object.freeze({
  planLabel: "Omi Plus",
  limitKey: "memories",
  used: 7,
  limit: null,
  limitReached: false,
  upgradeAvailable: true,
});

describe("SQLite Settings projection adapter", () => {
  test("preserves blank identity, authoritative absence, and unmetered after reopen", () => {
    const path = `/tmp/settings-projection-${process.pid}-${Date.now()}.sqlite`;
    const firstDb = new Database(path, { create: true });
    const first = new SqliteSettingsProjectionStore(firstDb);
    first.putIdentity("blank", { displayName: "", email: "" });
    first.putIdentity("unmetered", { displayName: "U", email: "u@example.invalid" });
    first.putEntitlement("unmetered", unmetered);
    firstDb.close();

    const secondDb = new Database(path);
    const second = new SqliteSettingsProjectionStore(secondDb);
    expect(second.readSettings("blank")).toEqual({
      status: "available",
      snapshot: { identity: { displayName: "", email: "" }, entitlement: null },
    });
    const snapshot = second.readSettings("unmetered");
    expect(snapshot).toEqual({
      status: "available",
      snapshot: {
        identity: { displayName: "U", email: "u@example.invalid" },
        entitlement: unmetered,
      },
    });
    if (snapshot.status === "available") {
      expect(snapshot.snapshot.entitlement).toEqual(second.readEntitlement("unmetered"));
    }
    secondDb.close();
  });
});
