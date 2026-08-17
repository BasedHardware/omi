// domain-pending(UNK-DOMAPPS-001)
import { describe, expect, test } from "bun:test";

import { createInMemorySettingsProjectionStore } from "./settings-projection";

const unmetered = Object.freeze({
  planLabel: "Omi Plus",
  limitKey: "memories",
  used: 7,
  limit: null,
  limitReached: false,
  upgradeAvailable: true,
});

describe("in-memory Settings sibling projections", () => {
  test("an empty-string identity is not null", () => {
    const store = createInMemorySettingsProjectionStore();
    store.putIdentity("blank", { displayName: "", email: "" });

    expect(store.readSettings("blank")).toEqual({
      status: "available",
      snapshot: {
        identity: { displayName: "", email: "" },
        entitlement: null,
      },
    });
    expect(store.readSettings("blank").status).toBe("available");
  });

  test("authoritative entitlement absence is distinct from an unmetered projection", () => {
    const store = createInMemorySettingsProjectionStore();
    store.putIdentity("absent", { displayName: "A", email: "a@example.invalid" });
    store.putIdentity("unmetered", { displayName: "U", email: "u@example.invalid" });
    store.putEntitlement("unmetered", unmetered);

    expect(store.readSettings("absent")).toEqual({
      status: "available",
      snapshot: {
        identity: { displayName: "A", email: "a@example.invalid" },
        entitlement: null,
      },
    });
    expect(store.readSettings("unmetered")).toEqual({
      status: "available",
      snapshot: {
        identity: { displayName: "U", email: "u@example.invalid" },
        entitlement: unmetered,
      },
    });
  });

  test("Settings and enforcement consume the same entitlement projection", () => {
    const store = createInMemorySettingsProjectionStore();
    store.putIdentity("same", { displayName: "Same", email: "same@example.invalid" });
    store.putEntitlement("same", unmetered);

    const settings = store.readSettings("same");
    expect(settings.status).toBe("available");
    if (settings.status !== "available") return;
    expect(settings.snapshot.entitlement).toBe(store.readEntitlement("same"));
  });

  test("missing required identity projection is unavailable, never signed out", () => {
    const store = createInMemorySettingsProjectionStore();
    store.putEntitlement("missing-identity", unmetered);

    expect(store.readSettings("missing-identity")).toEqual({ status: "unavailable" });
  });

  test("rejects an unmetered projection that claims its limit is reached", () => {
    const store = createInMemorySettingsProjectionStore();
    expect(() => store.putEntitlement("invalid", {
      ...unmetered,
      limitReached: true,
    })).toThrow("invalid settings entitlement projection");
  });
});
