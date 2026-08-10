import { describe, expect, test } from "bun:test";

import { createInMemoryAccountLifecycleStore } from "./account-lifecycle";

describe("in-memory account lifecycle adapter", () => {
  test("defaults an unknown account to active and preserves terminal source states", () => {
    const store = createInMemoryAccountLifecycleStore();
    expect(store.readLifecycle("unknown")).toBe("active");

    store.setLifecycle("account-a", "deletion_pending");
    expect(store.readLifecycle("account-a")).toBe("deletion_pending");
    store.setLifecycle("account-a", "deleted");
    expect(store.readLifecycle("account-a")).toBe("deleted");
  });
});
