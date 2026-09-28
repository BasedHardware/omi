// domain-pending(DIV-DOMCORE-001)
import { describe, expect, test } from "bun:test";

import { createInMemoryAccountControlProjectionStore } from "../control/projection-store";
import {
  LOCAL_OWNER_ACCOUNT_EPOCH,
  LocalOwnerWriteReadyError,
  ensureLocalOwnerWriteReady,
} from "./local-owner-cutover";

const OWNER = "local-dev-user";

const observation = (overrides: Record<string, unknown> = {}) => ({
  account_id: OWNER,
  control_revision: 1,
  account_generation: "legacy" as const,
  account_epoch: null,
  lifecycle_state: "active" as const,
  deletion_epoch: null,
  ...overrides,
});

describe("ensureLocalOwnerWriteReady", () => {
  test("admits a fresh account and is a no-op on the second call", () => {
    const store = createInMemoryAccountControlProjectionStore();
    expect(store.read(OWNER)).toBeNull();
    expect(ensureLocalOwnerWriteReady(store, OWNER)).toBe("admitted");
    const first = store.read(OWNER);
    expect(first).toMatchObject({
      account_generation: "new",
      account_epoch: LOCAL_OWNER_ACCOUNT_EPOCH,
      activation: {
        activated_epoch: LOCAL_OWNER_ACCOUNT_EPOCH,
        at_control_revision: 3,
      },
    });
    expect(ensureLocalOwnerWriteReady(store, OWNER)).toBe("already_ready");
    expect(store.read(OWNER)).toEqual(first);
  });

  test("does not restage a write-ready projection at a different epoch", () => {
    const store = createInMemoryAccountControlProjectionStore();
    store.observe(observation());
    store.observe(observation({ control_revision: 2, account_generation: "migrating" }));
    store.observe(observation({
      control_revision: 3, account_generation: "new", account_epoch: 12,
    }));
    expect(store.activate(OWNER, { epoch: 12, at_control_revision: 3 }).activated).toBe(true);
    expect(ensureLocalOwnerWriteReady(store, OWNER)).toBe("already_ready");
    expect(store.read(OWNER)?.account_epoch).toBe(12);
  });

  test("refuses a partial projection rather than restaging from revision 1", () => {
    const store = createInMemoryAccountControlProjectionStore();
    expect(store.observe(observation()).accepted).toBe(true);
    expect(() => ensureLocalOwnerWriteReady(store, OWNER)).toThrow(LocalOwnerWriteReadyError);
    expect(store.read(OWNER)).toMatchObject({
      control_revision: 1,
      account_generation: "legacy",
      account_epoch: null,
      activation: null,
    });
  });
});
