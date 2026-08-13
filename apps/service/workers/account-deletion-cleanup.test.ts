import { describe, expect, test } from "bun:test";

import type { AccountControlProjection } from "../../../core/control/account-control";
import {
  DELETION_CLEANUP_SURFACES,
  DELETION_INVENTORY_CONTRACT_VERSION,
  DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
  type DeletionCleanupSurface,
} from "../../../core/control/deletion-cleanup-inventory";
import type {
  DeletionDominanceInput,
  TerminalControlTombstone,
  TerminalDeletionExportReceipt,
} from "../../../core/control/deletion-dominance";
import {
  runAccountDeletionCleanupCycle,
  type AccountDeletionCleanupPort,
  type HeldDeletionCleanupSession,
} from "./account-deletion-cleanup";

const ACCOUNT = "acct-cleanup-cycle";
const hash = (value: string) => value.repeat(64);
const operation = `opref1_${hash("1")}`;
const projection: AccountControlProjection = {
  account_id: ACCOUNT, control_revision: 7, account_generation: "new", account_epoch: 3,
  lifecycle_state: "deleted", deletion_epoch: 11,
  activation: { activated_epoch: 3, at_control_revision: 2 }, conflict: null,
};
const tombstone: TerminalControlTombstone = {
  account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11,
  account_generation: "new", transitioned_at_epoch_seconds: 100, content_digest: hash("2"),
};
const exportReceipt: TerminalDeletionExportReceipt = {
  account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11,
  account_generation: "new", stranded_data_present: false,
  export_contract_version: "terminal-v1", export_record_digest: hash("3"),
  retention_locked_sink_receipt_digest: hash("4"),
};
const planInput = (hold: "clear" | "held" = "clear"): Omit<DeletionDominanceInput, "inventory"> => ({
  control_projection: projection,
  terminal_control_tombstone: tombstone,
  terminal_export_receipt: exportReceipt,
  restore_replay: { state: "not_required" },
  legal_hold: {
    status: hold, account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11,
    policy_version: "hold-v1", disposition_receipt_digest: hash("5"),
  },
  retention_disposition: {
    status: "ratified", policy_version: "retention-v1", approval_digest: hash("6"),
  },
  recovery_objectives: {
    status: "ratified", policy_version: "recovery-v1", approval_digest: hash("7"),
  },
});

const receipts = (remaining: ReadonlyMap<DeletionCleanupSurface, number>) =>
  DELETION_CLEANUP_SURFACES.map((surface, index) => ({
    version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
    inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION,
    scanner_contract_version: `scanner-${surface}-v1`, account_id: ACCOUNT,
    control_revision: 7, deletion_epoch: 11, surface,
    source_frontier_digest: hash(String(index % 10)),
    source_authorization_digest: hash("a"), scan_fence_state: "held" as const,
    scan_fence_receipt_digest: hash("b"), remaining_count: remaining.get(surface) ?? 0,
    remaining_set_digest: hash((remaining.get(surface) ?? 0) > 0 ? "c" : "0"),
  }));

const port = (
  initial: ReadonlyMap<DeletionCleanupSurface, number>,
  options: { failDispose?: boolean; staleAfter?: boolean } = {},
) => {
  const remaining = new Map(initial);
  const calls: string[] = [];
  let active = false;
  const session: HeldDeletionCleanupSession = {
    async scanAll() {
      expect(active).toBe(true);
      calls.push("scan");
      return receipts(remaining);
    },
    async dispose(surface) {
      expect(active).toBe(true);
      calls.push(`dispose:${surface}`);
      if (options.failDispose) throw new Error("sensitive provider failure");
      if (!options.staleAfter) remaining.set(surface, 0);
      return {
        version: "deletion-cleanup-disposition-v1" as const,
        surface, result: "disposed" as const, receipt_digest: hash("d"),
      };
    },
  };
  const adapter: AccountDeletionCleanupPort = {
    async withHeldFence(coordinate, operationRef, eligibilityDigest, callback) {
      expect(coordinate).toEqual({ account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11 });
      expect(operationRef).toBe(operation);
      expect(eligibilityDigest).toMatch(/^[0-9a-f]{64}$/);
      active = true;
      try { return await callback(session); } finally { active = false; calls.push("release"); }
    },
  };
  return { adapter, calls };
};

describe("account deletion cleanup cycle", () => {
  test("disposes only reported surfaces and proves zero under the same held fence", async () => {
    const fixture = port(new Map([
      ["authoritative_memory", 3], ["product_projections", 2], ["account_access", 1],
    ]));
    const outcome = await runAccountDeletionCleanupCycle({
      operation_ref: operation, plan_input: planInput(),
    }, fixture.adapter);
    expect(outcome).toMatchObject({
      kind: "complete",
      disposed_surfaces: ["product_projections", "authoritative_memory", "account_access"],
    });
    expect(fixture.calls).toEqual([
      "scan", "dispose:product_projections", "dispose:authoritative_memory",
      "dispose:account_access", "scan", "release",
    ]);
    expect(JSON.stringify(outcome)).not.toContain(ACCOUNT);
  });

  test("an active hold performs no disposal and keeps the account blocked", async () => {
    const fixture = port(new Map([["authoritative_memory", 3]]));
    const outcome = await runAccountDeletionCleanupCycle({
      operation_ref: operation, plan_input: planInput("held"),
    }, fixture.adapter);
    expect(outcome).toMatchObject({ kind: "blocked", blockers: ["legal_hold_active"] });
    expect(fixture.calls).toEqual(["scan", "release"]);
  });

  test("partial deletion, failed disposal, and malformed scan never become complete", async () => {
    const stale = port(new Map([["authoritative_memory", 1]]), { staleAfter: true });
    expect(await runAccountDeletionCleanupCycle({
      operation_ref: operation, plan_input: planInput(),
    }, stale.adapter)).toEqual({ kind: "retryable", error_code: "postcondition_failed" });

    const failed = port(new Map([["authoritative_memory", 1]]), { failDispose: true });
    expect(await runAccountDeletionCleanupCycle({
      operation_ref: operation, plan_input: planInput(),
    }, failed.adapter)).toEqual({ kind: "retryable", error_code: "disposal_failed" });

    const malformed: AccountDeletionCleanupPort = {
      async withHeldFence(_coordinate, _operationRef, _eligibilityDigest, callback) {
        return callback({
          async scanAll() { return receipts(new Map()).slice(1); },
          async dispose() { throw new Error("unreachable"); },
        });
      },
    };
    expect(await runAccountDeletionCleanupCycle({
      operation_ref: operation, plan_input: planInput(),
    }, malformed)).toEqual({ kind: "retryable", error_code: "scan_failed" });
  });

  test("already-empty cleanup is idempotently complete without disposal", async () => {
    const fixture = port(new Map());
    const first = await runAccountDeletionCleanupCycle({
      operation_ref: operation, plan_input: planInput(),
    }, fixture.adapter);
    const second = await runAccountDeletionCleanupCycle({
      operation_ref: operation, plan_input: planInput(),
    }, fixture.adapter);
    expect(first).toEqual(second);
    expect(first).toMatchObject({ kind: "complete", disposed_surfaces: [] });
  });

  test("rejects hostile input before acquiring the deletion fence", async () => {
    let calls = 0;
    const fixture = port(new Map());
    const guarded: AccountDeletionCleanupPort = {
      async withHeldFence(coordinate, operationRef, eligibilityDigest, callback) {
        calls += 1;
        return fixture.adapter.withHeldFence(
          coordinate,
          operationRef,
          eligibilityDigest,
          callback,
        );
      },
    };
    let getterCalls = 0;
    const hostile: Record<string, unknown> = { operation_ref: operation };
    Object.defineProperty(hostile, "plan_input", {
      enumerable: true,
      get() { getterCalls += 1; return planInput(); },
    });
    await expect(runAccountDeletionCleanupCycle(hostile as never, guarded))
      .rejects.toThrow("invalid cleanup input");
    await expect(runAccountDeletionCleanupCycle(new Proxy({
      operation_ref: operation, plan_input: planInput(),
    }, {}) as never, guarded)).rejects.toThrow("invalid cleanup input");
    expect(getterCalls).toBe(0);
    expect(calls).toBe(0);
  });
});
