import { describe, expect, test } from "bun:test";

import type { AccountControlProjection } from "./account-control";
import {
  DELETION_INVENTORY_CONTRACT_VERSION,
  DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
  verifyDeletionCleanupInventory,
  type VerifiedDeletionCleanupInventory,
} from "./deletion-cleanup-inventory";
import {
  DELETION_CLEANUP_SURFACES,
  DeletionDominanceInputError,
  planDeletionDominance,
  type DeletionDominanceInput,
  type DeletionDominanceInputErrorCode,
  type TerminalControlTombstone,
  type TerminalDeletionExportReceipt,
} from "./deletion-dominance";

const ACCOUNT = "acct-deletion-plan-fixture";
const digest = (character: string): string => character.repeat(64);

const projection = (
  overrides: Partial<AccountControlProjection> = {},
): AccountControlProjection => ({
  account_id: ACCOUNT,
  control_revision: 3,
  account_generation: "legacy",
  account_epoch: null,
  lifecycle_state: "active",
  deletion_epoch: null,
  activation: null,
  conflict: null,
  ...overrides,
});

const inventory = (
  counts: Partial<Record<typeof DELETION_CLEANUP_SURFACES[number], number>> = {},
): VerifiedDeletionCleanupInventory => {
  const result = verifyDeletionCleanupInventory({
    terminal_coordinate: {
      account_id: ACCOUNT,
      control_revision: 7,
      deletion_epoch: 31,
    },
    source_receipts: DELETION_CLEANUP_SURFACES.map((surface, index) => ({
      version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
      inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION,
      scanner_contract_version: `scanner-${surface}-v1`,
      account_id: ACCOUNT,
      control_revision: 7,
      deletion_epoch: 31,
      surface,
      source_frontier_digest: digest(String(index % 10)),
      source_authorization_digest: digest("a"),
      scan_fence_state: "held" as const,
      scan_fence_receipt_digest: digest("b"),
      remaining_count: counts[surface] ?? 0,
      remaining_set_digest: digest("c"),
    })),
  });
  expect(result.report.blockers).toEqual([]);
  return result.verified_inventory!;
};

const tombstone = (
  overrides: Partial<TerminalControlTombstone> = {},
): TerminalControlTombstone => ({
  account_id: ACCOUNT,
  control_revision: 7,
  deletion_epoch: 31,
  account_generation: "new",
  transitioned_at_epoch_seconds: 1_800_000_000,
  content_digest: digest("a"),
  ...overrides,
});

const exportReceipt = (
  overrides: Partial<TerminalDeletionExportReceipt> = {},
): TerminalDeletionExportReceipt => ({
  account_id: ACCOUNT,
  control_revision: 7,
  deletion_epoch: 31,
  account_generation: "new",
  stranded_data_present: false,
  export_contract_version: "terminal-deletion-export-v1",
  export_record_digest: digest("b"),
  retention_locked_sink_receipt_digest: digest("c"),
  ...overrides,
});

const ratified = (version: string) => ({
  status: "ratified" as const,
  policy_version: version,
  approval_digest: digest(version === "retention-v1" ? "d" : "e"),
});

const clearLegalHold = () => ({
  status: "clear" as const,
  account_id: ACCOUNT,
  control_revision: 7,
  deletion_epoch: 31,
  policy_version: "legal-hold-v1",
  disposition_receipt_digest: digest("f"),
});

const input = (
  overrides: Partial<DeletionDominanceInput> = {},
): DeletionDominanceInput => ({
  control_projection: projection(),
  terminal_control_tombstone: null,
  terminal_export_receipt: null,
  restore_replay: { state: "not_required" },
  legal_hold: { status: "unverified" },
  retention_disposition: { status: "unratified" },
  recovery_objectives: { status: "unratified" },
  inventory: null,
  ...overrides,
});

const terminalInput = (
  overrides: Partial<DeletionDominanceInput> = {},
): DeletionDominanceInput => input({
  control_projection: projection({
    control_revision: 7,
    account_generation: "new",
    account_epoch: 9,
    lifecycle_state: "deleted",
    deletion_epoch: 31,
    activation: { activated_epoch: 9, at_control_revision: 3 },
  }),
  terminal_control_tombstone: tombstone(),
  terminal_export_receipt: exportReceipt(),
  legal_hold: clearLegalHold(),
  retention_disposition: ratified("retention-v1"),
  recovery_objectives: ratified("recovery-v1"),
  inventory: inventory(),
  ...overrides,
});

const expectErrorCode = (call: () => unknown, code: DeletionDominanceInputErrorCode): void => {
  try {
    call();
    throw new Error("expected deletion-dominance input error");
  } catch (error) {
    expect(error).toBeInstanceOf(DeletionDominanceInputError);
    expect((error as DeletionDominanceInputError).code).toBe(code);
  }
};

describe("active generation modes", () => {
  test("distinguishes legacy, migration, activated, unactivated, and stranded states", () => {
    expect(planDeletionDominance(input()).mode).toBe("legacy_active");

    const migrating = planDeletionDominance(input({
      control_projection: projection({ account_generation: "migrating" }),
    }));
    expect(migrating).toMatchObject({
      mode: "migration_fenced",
      fences: { request_reads: true, request_writes: true, migration_resume: false },
      obligations: ["consult_item_tombstones_on_migration_resume"],
    });

    const unactivated = planDeletionDominance(input({
      control_projection: projection({ account_generation: "new", account_epoch: 9 }),
    }));
    expect(unactivated.mode).toBe("destination_fenced");
    expect(Object.values(unactivated.fences).every((fenced) => fenced)).toBe(true);

    const activated = planDeletionDominance(input({
      control_projection: projection({
        account_generation: "new",
        account_epoch: 9,
        activation: { activated_epoch: 9, at_control_revision: 3 },
      }),
    }));
    expect(activated).toMatchObject({
      mode: "destination_active",
      fences: {
        request_reads: false,
        request_writes: false,
        new_model_work: false,
        lease_resume: false,
        outbox_effects: false,
        migration_resume: true,
        projection_rebuild: false,
        index_rebuild: false,
      },
    });

    expect(planDeletionDominance(input({
      control_projection: projection({ account_generation: "rolled_back_stranded" }),
    })).mode).toBe("stranded_fenced");
  });

  test("missing and conflicted control are distinct fail-closed plans", () => {
    const missing = planDeletionDominance(input({ control_projection: null }));
    expect(missing).toMatchObject({
      mode: "control_unavailable",
      account_id: null,
      cleanup: { state: "blocked", blockers: ["control_unavailable"] },
    });
    expect(Object.values(missing.fences).every((fenced) => fenced)).toBe(true);

    const conflicted = planDeletionDominance(input({
      control_projection: projection({
        conflict: { at_control_revision: 3, detail: "conflicting_observation" },
      }),
    }));
    expect(conflicted.mode).toBe("control_unavailable");
  });
});

describe("lifecycle dominance and terminal cleanup", () => {
  test("deletion_pending dominates an activated new generation without disposing data", () => {
    const plan = planDeletionDominance(input({
      control_projection: projection({
        control_revision: 6,
        account_generation: "new",
        account_epoch: 9,
        lifecycle_state: "deletion_pending",
        deletion_epoch: 31,
        activation: { activated_epoch: 9, at_control_revision: 3 },
      }),
    }));
    expect(plan.mode).toBe("deletion_pending");
    expect(Object.values(plan.fences).every((fenced) => fenced)).toBe(true);
    expect(plan.obligations).toContain("deactivate_destination_epoch");
    expect(plan.obligations).toContain("await_terminal_control");
    expect(plan.obligations).not.toContain("dispose_policy_authorized_surfaces");
    expect(plan.cleanup).toMatchObject({ state: "not_applicable", remaining_total: 0 });
  });

  test("terminal cleanup remains blocked until export and human policy coordinates exist", () => {
    const plan = planDeletionDominance(terminalInput({
      terminal_export_receipt: null,
      retention_disposition: { status: "unratified" },
      recovery_objectives: { status: "unratified" },
      inventory: inventory({ staged_results: 2 }),
    }));
    expect(plan).toMatchObject({
      mode: "deleted_blocked",
      cleanup: {
        state: "blocked",
        blockers: [
          "terminal_export_receipt_missing",
          "retention_disposition_unratified",
          "recovery_objectives_unratified",
        ],
        remaining_total: 2,
        remaining_surfaces: ["staged_results"],
      },
    });
    expect(plan.obligations).toContain("retain_terminal_control_tombstone");
    expect(plan.obligations).toContain("require_terminal_export_receipt");
    expect(plan.obligations).not.toContain("dispose_policy_authorized_surfaces");
  });

  test("a deleted projection without the exact terminal tombstone fails closed", () => {
    expectErrorCode(() => planDeletionDominance(terminalInput({
      terminal_control_tombstone: null,
      terminal_export_receipt: null,
    })), "terminal_coordinate_mismatch");
  });

  test("legal hold must be verified clear before disposal and never reopens product access", () => {
    const unverified = planDeletionDominance(terminalInput({
      legal_hold: { status: "unverified" },
      inventory: inventory({ product_projections: 2 }),
    }));
    expect(unverified).toMatchObject({
      mode: "deleted_blocked",
      cleanup: { state: "blocked", blockers: ["legal_hold_unverified"] },
    });
    expect(unverified.obligations).toContain("require_legal_hold_verification");
    expect(Object.values(unverified.fences).every((fenced) => fenced)).toBe(true);

    const held = planDeletionDominance(terminalInput({
      legal_hold: {
        status: "held",
        account_id: ACCOUNT,
        control_revision: 7,
        deletion_epoch: 31,
        policy_version: "legal-hold-v1",
        disposition_receipt_digest: digest("9"),
      },
      inventory: inventory({ product_projections: 2 }),
    }));
    expect(held).toMatchObject({
      mode: "deleted_blocked",
      cleanup: { state: "blocked", blockers: ["legal_hold_active"] },
    });
    expect(held.obligations).toContain("isolate_legal_hold_content");
    expect(held.obligations).not.toContain("dispose_policy_authorized_surfaces");
    expect(Object.values(held.fences).every((fenced) => fenced)).toBe(true);

    const clear = planDeletionDominance(terminalInput({
      inventory: inventory({ product_projections: 2 }),
    }));
    expect(clear.mode).toBe("deleted_cleanup_ready");
  });

  test("a terminal plan never interprets an unverified inventory as zero", () => {
    const plan = planDeletionDominance(terminalInput({ inventory: null }));
    expect(plan).toMatchObject({
      mode: "deleted_blocked",
      cleanup: { state: "blocked", blockers: ["cleanup_inventory_unverified"] },
    });
    expect(plan.obligations).toContain("require_verified_cleanup_inventory");
  });

  test("ratified coordinates make remaining surfaces eligible, not deleted", () => {
    const plan = planDeletionDominance(terminalInput({
      terminal_export_receipt: exportReceipt({ stranded_data_present: true }),
      inventory: inventory({
        product_projections: 4,
        stranded_product_data: 3,
        external_objects: 1,
      }),
    }));
    expect(plan).toMatchObject({
      mode: "deleted_cleanup_ready",
      cleanup: {
        state: "ready",
        blockers: [],
        remaining_total: 8,
        remaining_surfaces: ["product_projections", "stranded_product_data", "external_objects"],
      },
    });
    expect(plan.obligations).toContain("dispose_policy_authorized_surfaces");
    expect(plan.obligations).toContain("retain_terminal_control_tombstone");
  });

  test("legacy-generation data is independent of the stranded-new-generation export flag", () => {
    const plan = planDeletionDominance(terminalInput({
      terminal_export_receipt: exportReceipt({ stranded_data_present: false }),
      inventory: inventory({ legacy_generation_data: 2 }),
    }));
    expect(plan).toMatchObject({
      mode: "deleted_cleanup_ready",
      cleanup: {
        state: "ready",
        blockers: [],
        remaining_total: 2,
        remaining_surfaces: ["legacy_generation_data"],
      },
    });
  });

  test("zero remaining surfaces is terminally complete but still retains the tombstone", () => {
    const plan = planDeletionDominance(terminalInput());
    expect(plan).toMatchObject({
      mode: "deleted_complete",
      cleanup: { state: "complete", remaining_total: 0, remaining_surfaces: [] },
    });
    expect(plan.obligations).toContain("retain_terminal_control_tombstone");
    expect(plan.obligations).not.toContain("dispose_policy_authorized_surfaces");
  });
});

describe("restore non-resurrection", () => {
  test("a restored active projection behind a surviving terminal tombstone is fenced", () => {
    const plan = planDeletionDominance(input({
      control_projection: projection({
        control_revision: 3,
        account_generation: "new",
        account_epoch: 9,
        activation: { activated_epoch: 9, at_control_revision: 3 },
      }),
      terminal_control_tombstone: tombstone(),
      terminal_export_receipt: exportReceipt(),
      legal_hold: clearLegalHold(),
      retention_disposition: ratified("retention-v1"),
      recovery_objectives: ratified("recovery-v1"),
      inventory: inventory(),
    }));
    expect(plan).toMatchObject({
      mode: "deleted_blocked",
      control_revision: 7,
      deletion_epoch: 31,
      cleanup: { state: "blocked", blockers: ["terminal_control_not_replayed"] },
    });
    expect(Object.values(plan.fences).every((fenced) => fenced)).toBe(true);
    expect(plan.obligations).toContain("replay_tombstones_before_restore_traffic");
  });

  test("a required replay must cover the same account and terminal coordinates", () => {
    const blocked = planDeletionDominance(terminalInput({
      restore_replay: {
        state: "required",
        checkpoint: {
          account_id: ACCOUNT,
          through_control_revision: 6,
          through_deletion_epoch: 30,
          checkpoint_digest: digest("f"),
        },
      },
    }));
    expect(blocked).toMatchObject({
      mode: "deleted_blocked",
      cleanup: { blockers: ["restore_replay_incomplete"] },
    });

    const covered = planDeletionDominance(terminalInput({
      restore_replay: {
        state: "required",
        checkpoint: {
          account_id: ACCOUNT,
          through_control_revision: 8,
          through_deletion_epoch: 32,
          checkpoint_digest: digest("f"),
        },
      },
    }));
    expect(covered.mode).toBe("deleted_complete");

    expectErrorCode(() => planDeletionDominance(terminalInput({
      restore_replay: {
        state: "required",
        checkpoint: {
          account_id: "acct-other",
          through_control_revision: 8,
          through_deletion_epoch: 32,
          checkpoint_digest: digest("f"),
        },
      },
    })), "account_coordinate_mismatch");
  });
});

describe("strict detached input and coordinate closure", () => {
  test("rejects cross-account and mismatched terminal artifacts", () => {
    expectErrorCode(() => planDeletionDominance(terminalInput({
      terminal_export_receipt: exportReceipt({ account_id: "acct-other" }),
    })), "account_coordinate_mismatch");
    expectErrorCode(() => planDeletionDominance(terminalInput({
      terminal_export_receipt: exportReceipt({ deletion_epoch: 32 }),
    })), "terminal_coordinate_mismatch");
    expectErrorCode(() => planDeletionDominance(terminalInput({
      terminal_control_tombstone: tombstone({ control_revision: 8 }),
    })), "terminal_coordinate_mismatch");
    expectErrorCode(() => planDeletionDominance(terminalInput({
      terminal_export_receipt: exportReceipt({ stranded_data_present: false }),
      inventory: inventory({ stranded_product_data: 1 }),
    })), "terminal_coordinate_mismatch");
    expectErrorCode(() => planDeletionDominance(terminalInput({
      legal_hold: { ...clearLegalHold(), account_id: "acct-other" },
    })), "account_coordinate_mismatch");
    expectErrorCode(() => planDeletionDominance(terminalInput({
      legal_hold: { ...clearLegalHold(), deletion_epoch: 32 },
    })), "terminal_coordinate_mismatch");
  });

  test("rejects proxies, accessors, extras, and forged inventory capabilities", () => {
    expectErrorCode(() => planDeletionDominance(new Proxy(input(), {})), "invalid_input");

    const accessor = input() as unknown as Record<string, unknown>;
    Object.defineProperty(accessor, "inventory", { enumerable: true, get: () => inventory() });
    expectErrorCode(() => planDeletionDominance(accessor), "invalid_input");

    let nestedGetterCalls = 0;
    const hostilePolicy = {};
    Object.defineProperty(hostilePolicy, "status", {
      enumerable: true,
      get: () => {
        nestedGetterCalls += 1;
        return "ratified";
      },
    });
    expectErrorCode(() => planDeletionDominance(input({
      retention_disposition: hostilePolicy as never,
    })), "invalid_ratification_coordinate");
    expect(nestedGetterCalls).toBe(0);
    expectErrorCode(() => planDeletionDominance(input({
      restore_replay: new Proxy({ state: "not_required" }, {}) as never,
    })), "invalid_restore_replay");
    expectErrorCode(() => planDeletionDominance(input({
      legal_hold: { status: "clear", policy_version: "legal-hold-v1" } as never,
    })), "invalid_legal_hold_coordinate");
    expectErrorCode(() => planDeletionDominance(input({
      legal_hold: new Proxy({ status: "unverified" }, {}) as never,
    })), "invalid_legal_hold_coordinate");

    expectErrorCode(() => planDeletionDominance({ ...input(), extra: true }), "invalid_input");
    const forged = JSON.parse(JSON.stringify(inventory())) as VerifiedDeletionCleanupInventory;
    expectErrorCode(() => planDeletionDominance(terminalInput({ inventory: forged })), "invalid_inventory");
    expectErrorCode(() => planDeletionDominance(terminalInput({
      inventory: new Proxy(inventory(), {}) as never,
    })), "invalid_inventory");
  });

  test("returns frozen, deterministic output detached from later input mutation", () => {
    const mutable = terminalInput({ inventory: inventory({ product_projections: 2 }) });
    const first = planDeletionDominance(mutable);
    const canonical = JSON.stringify(first);

    (mutable.control_projection as { control_revision: number }).control_revision = 999;

    expect(JSON.stringify(first)).toBe(canonical);
    expect(Object.isFrozen(first)).toBe(true);
    expect(Object.isFrozen(first.fences)).toBe(true);
    expect(Object.isFrozen(first.obligations)).toBe(true);
    expect(Object.isFrozen(first.cleanup)).toBe(true);
    expect(Object.isFrozen(first.cleanup.blockers)).toBe(true);
    expect(Object.isFrozen(first.cleanup.remaining_surfaces)).toBe(true);
    expect(planDeletionDominance(terminalInput({
      inventory: inventory({ product_projections: 2 }),
    }))).toEqual(first);
  });
});
