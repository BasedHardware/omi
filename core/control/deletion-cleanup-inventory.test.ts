import { describe, expect, test } from "bun:test";

import {
  DELETION_CLEANUP_SURFACES,
  DELETION_INVENTORY_CONTRACT_VERSION,
  DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
  DeletionInventoryInputError,
  isVerifiedDeletionCleanupInventory,
  verifyDeletionCleanupInventory,
  type DeletionCleanupSurface,
  type DeletionInventoryInputErrorCode,
  type DeletionInventorySourceReceipt,
} from "./deletion-cleanup-inventory";

const ACCOUNT = "acct-deletion-inventory-fixture";
const digest = (character: string): string => character.repeat(64);

const receipt = (
  surface: DeletionCleanupSurface,
  index: number,
  overrides: Partial<DeletionInventorySourceReceipt> = {},
): DeletionInventorySourceReceipt => ({
  version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
  inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION,
  scanner_contract_version: `scanner-${surface}-v1`,
  account_id: ACCOUNT,
  control_revision: 7,
  deletion_epoch: 31,
  surface,
  source_frontier_digest: digest(String(index % 10)),
  source_authorization_digest: digest("a"),
  scan_fence_state: "held",
  scan_fence_receipt_digest: digest("b"),
  remaining_count: index,
  remaining_set_digest: digest("c"),
  ...overrides,
});

const receipts = (): DeletionInventorySourceReceipt[] =>
  DELETION_CLEANUP_SURFACES.map((surface, index) => receipt(surface, index));

const input = (sourceReceipts: readonly DeletionInventorySourceReceipt[] = receipts()) => ({
  terminal_coordinate: {
    account_id: ACCOUNT,
    control_revision: 7,
    deletion_epoch: 31,
  },
  source_receipts: sourceReceipts,
});

const expectErrorCode = (call: () => unknown, code: DeletionInventoryInputErrorCode): void => {
  try {
    call();
    throw new Error("expected deletion inventory input error");
  } catch (error) {
    expect(error).toBeInstanceOf(DeletionInventoryInputError);
    expect((error as DeletionInventoryInputError).code).toBe(code);
  }
};

describe("complete-source inventory", () => {
  test("one held receipt per source produces a canonical verified inventory", () => {
    const forward = verifyDeletionCleanupInventory(input());
    const reversed = verifyDeletionCleanupInventory(input(receipts().reverse()));
    expect(forward.report).toEqual(reversed.report);
    expect(forward.verified_inventory).toEqual(reversed.verified_inventory);
    expect(forward.report).toMatchObject({
      version: "deletion-cleanup-inventory-v4",
      supplied_source_count: 13,
      required_source_count: 13,
      missing_surfaces: [],
      unfenced_surfaces: [],
      blockers: [],
    });
    expect(forward.report.inventory_digest).toMatch(/^[0-9a-f]{64}$/);
    expect(isVerifiedDeletionCleanupInventory(forward.verified_inventory)).toBe(true);
    expect(forward.verified_inventory?.rows.map((row) => row.surface))
      .toEqual([...DELETION_CLEANUP_SURFACES]);
  });

  test("every zero is receipt-backed and remains distinct from a missing scanner", () => {
    const zeroReceipts = DELETION_CLEANUP_SURFACES.map((surface, index) => receipt(surface, index, {
      remaining_count: 0,
      remaining_set_digest: digest("0"),
    }));
    const zero = verifyDeletionCleanupInventory(input(zeroReceipts));
    expect(zero.report.blockers).toEqual([]);
    expect(zero.verified_inventory?.rows.every((row) => row.remaining_count === 0)).toBe(true);

    const missing = verifyDeletionCleanupInventory(input(zeroReceipts.slice(1)));
    expect(missing.report).toMatchObject({
      blockers: ["source_missing"],
      missing_surfaces: ["durable_work"],
      inventory_digest: null,
    });
    expect(missing.verified_inventory).toBeNull();

    expectErrorCode(() => verifyDeletionCleanupInventory(input(zeroReceipts.map((row, index) =>
      index === 0 ? { ...row, remaining_set_digest: null as never } : row))), "invalid_source_receipt");
  });

  test("released scan fences block without erasing otherwise complete counts", () => {
    const released = receipts();
    const experimentIndex = released.findIndex((row) => row.surface === "experiment_results");
    const externalIndex = released.findIndex((row) => row.surface === "external_objects");
    released[experimentIndex] = {
      ...released[experimentIndex]!,
      scan_fence_state: "released",
    };
    released[externalIndex] = {
      ...released[externalIndex]!,
      scan_fence_state: "released",
    };
    const result = verifyDeletionCleanupInventory(input(released));
    expect(result.report).toMatchObject({
      supplied_source_count: 13,
      missing_surfaces: [],
      unfenced_surfaces: ["experiment_results", "external_objects"],
      blockers: ["source_fence_not_held"],
      inventory_digest: null,
    });
    expect(result.verified_inventory).toBeNull();
  });
});

describe("receipt identity and closure", () => {
  test("duplicate, unknown, oversized, and cross-terminal sources fail", () => {
    const duplicate = receipts();
    duplicate[1] = { ...duplicate[0]! };
    expectErrorCode(() => verifyDeletionCleanupInventory(input(duplicate)), "duplicate_source_receipt");

    const unknown = receipts();
    unknown[0] = { ...unknown[0]!, surface: "unknown" as never };
    expectErrorCode(() => verifyDeletionCleanupInventory(input(unknown)), "invalid_source_receipt");
    expectErrorCode(() => verifyDeletionCleanupInventory(input([...receipts(), receipts()[0]!])),
      "invalid_source_receipts");

    const stale = receipts();
    stale[0] = {
      ...stale[0]!,
      version: "deletion-inventory-source-receipt-v3" as never,
      inventory_contract_version: "deletion-cleanup-inventory-v3" as never,
    };
    expectErrorCode(() => verifyDeletionCleanupInventory(input(stale)), "invalid_source_receipt");

    for (const changed of [
      { account_id: "acct-other" },
      { control_revision: 8 },
      { deletion_epoch: 32 },
    ]) {
      const rows = receipts();
      rows[0] = { ...rows[0]!, ...changed };
      expectErrorCode(() => verifyDeletionCleanupInventory(input(rows)), "source_coordinate_mismatch");
    }
  });

  test("every scanner/frontier/authorization/fence/set coordinate changes inventory identity", () => {
    const baseline = verifyDeletionCleanupInventory(input()).report.inventory_digest;
    for (const changed of [
      { scanner_contract_version: "scanner-durable-work-v2" },
      { source_frontier_digest: digest("d") },
      { source_authorization_digest: digest("e") },
      { scan_fence_receipt_digest: digest("f") },
      { remaining_count: 99 },
      { remaining_set_digest: digest("9") },
    ]) {
      const rows = receipts();
      rows[0] = { ...rows[0]!, ...changed };
      const candidate = verifyDeletionCleanupInventory(input(rows)).report.inventory_digest;
      expect(candidate).not.toBe(baseline);
    }
  });
});

describe("strict plain data and content-safe reports", () => {
  test("rejects proxies, accessors, classes, extras, sparse/decorated arrays, and unsafe counts", () => {
    expectErrorCode(() => verifyDeletionCleanupInventory(new Proxy(input(), {})), "invalid_input");
    expectErrorCode(() => verifyDeletionCleanupInventory({ ...input(), extra: true }), "invalid_input");

    class ReceiptClass {
      version = DELETION_INVENTORY_SOURCE_RECEIPT_VERSION;
      inventory_contract_version = DELETION_INVENTORY_CONTRACT_VERSION;
      scanner_contract_version = "scanner-durable-work-v1";
      account_id = ACCOUNT;
      control_revision = 7;
      deletion_epoch = 31;
      surface = "durable_work" as const;
      source_frontier_digest = digest("0");
      source_authorization_digest = digest("a");
      scan_fence_state = "held" as const;
      scan_fence_receipt_digest = digest("b");
      remaining_count = 0;
      remaining_set_digest = digest("c");
    }
    expectErrorCode(() => verifyDeletionCleanupInventory(input([
      new ReceiptClass() as DeletionInventorySourceReceipt,
      ...receipts().slice(1),
    ])), "invalid_source_receipt");

    let getterCalls = 0;
    const hostile = { ...receipts()[0] } as Record<string, unknown>;
    Object.defineProperty(hostile, "surface", {
      enumerable: true,
      get: () => {
        getterCalls += 1;
        return "durable_work";
      },
    });
    expectErrorCode(() => verifyDeletionCleanupInventory(input([
      hostile as never,
      ...receipts().slice(1),
    ])), "invalid_source_receipt");
    expect(getterCalls).toBe(0);

    const sparse = receipts();
    delete sparse[0];
    expectErrorCode(() => verifyDeletionCleanupInventory(input(sparse)), "invalid_source_receipts");
    const decorated = receipts() as DeletionInventorySourceReceipt[] & { extra?: boolean };
    decorated.extra = true;
    expectErrorCode(() => verifyDeletionCleanupInventory(input(decorated)), "invalid_source_receipts");

    const symbolKey = receipts()[0] as DeletionInventorySourceReceipt & { [key: symbol]: boolean };
    symbolKey[Symbol("hidden")] = true;
    expectErrorCode(() => verifyDeletionCleanupInventory(input([
      symbolKey,
      ...receipts().slice(1),
    ])), "invalid_source_receipt");

    expectErrorCode(() => verifyDeletionCleanupInventory(input(receipts().map((row, index) =>
      index === 0 ? { ...row, remaining_count: Number.MAX_SAFE_INTEGER + 1 } : row))),
    "invalid_source_receipt");
    expectErrorCode(() => verifyDeletionCleanupInventory(input(receipts().map((row, index) =>
      index === 0 ? { ...row, scanner_contract_version: "x".repeat(257) } : row))),
    "invalid_source_receipt");
    expectErrorCode(() => verifyDeletionCleanupInventory(input(receipts().map((row, index) =>
      index === 0 ? { ...row, source_frontier_digest: "not-a-digest" } : row))),
    "invalid_source_receipt");
  });

  test("report is deeply frozen, account-free, and detached from later mutation", () => {
    const mutableReceipts = receipts();
    const result = verifyDeletionCleanupInventory(input(mutableReceipts));
    const reportBytes = JSON.stringify(result.report);
    expect(reportBytes).not.toContain(ACCOUNT);
    expect(reportBytes).not.toContain("scanner-");
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.report)).toBe(true);
    expect(Object.isFrozen(result.report.missing_surfaces)).toBe(true);
    expect(Object.isFrozen(result.verified_inventory)).toBe(true);
    expect(Object.isFrozen(result.verified_inventory?.rows)).toBe(true);

    (mutableReceipts[0] as { remaining_count: number }).remaining_count = 999;
    expect(JSON.stringify(result.report)).toBe(reportBytes);
    expect(result.verified_inventory?.rows[0]?.remaining_count).toBe(0);
  });
});
