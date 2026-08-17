import { describe, expect, test } from "bun:test";

import { createInMemoryAccountLifecycleStore } from "./account-lifecycle";

describe("in-memory account lifecycle adapter", () => {
  test("keeps unknown state missing and preserves explicit source states", () => {
    const store = createInMemoryAccountLifecycleStore();
    expect(store.readLifecycle("unknown")).toBeNull();

    store.setLifecycle("account-a", "active");
    expect(store.readLifecycle("account-a")).toBe("active");
    store.setLifecycle("account-a", "deletion_pending");
    expect(store.readLifecycle("account-a")).toBe("deletion_pending");
    store.setLifecycle("account-a", "deleted");
    expect(store.readLifecycle("account-a")).toBe("deleted");

    expect(() => store.setLifecycle("account-b", "paused" as never))
      .toThrow("invalid account lifecycle state");
    store.reset();
    expect(store.readLifecycle("account-a")).toBeNull();
  });
});
