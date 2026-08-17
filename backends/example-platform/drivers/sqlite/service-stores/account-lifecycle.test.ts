import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { SqliteAccountLifecycleStore } from "./account-lifecycle";

describe("SQLite account lifecycle adapter", () => {
  test("keeps missing state null and persists explicit lifecycle across reopen", () => {
    const path = `/private/tmp/account-lifecycle-${process.pid}-${Date.now()}.sqlite`;
    const firstDb = new Database(path, { create: true });
    const first = new SqliteAccountLifecycleStore(firstDb);
    expect(first.readLifecycle("unknown")).toBeNull();
    first.setLifecycle("account-active", "active");
    first.setLifecycle("account-a", "deletion_pending");
    first.setLifecycle("account-b", "deleted");
    firstDb.close();

    const secondDb = new Database(path);
    const second = new SqliteAccountLifecycleStore(secondDb);
    expect(second.readLifecycle("account-active")).toBe("active");
    expect(second.readLifecycle("account-a")).toBe("deletion_pending");
    expect(second.readLifecycle("account-b")).toBe("deleted");
    secondDb.close();
  });
});
