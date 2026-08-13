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
import { runAccountDeletionCleanupCycle } from "./account-deletion-cleanup";
import {
  createCompositeAccountDeletionCleanupPort,
  DeletionCleanupCompositeError,
  type DeletionEligibilityFenceCoordinator,
  type DeletionSurfaceParticipant,
  type EligibilityFenceRevalidationReceipt,
} from "./account-deletion-cleanup-composite";

const ACCOUNT = "acct-composite-cleanup";
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
const planInput = (): Omit<DeletionDominanceInput, "inventory"> => ({
  control_projection: projection,
  terminal_control_tombstone: tombstone,
  terminal_export_receipt: exportReceipt,
  restore_replay: { state: "not_required" },
  legal_hold: {
    status: "clear", account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11,
    policy_version: "hold-v1", disposition_receipt_digest: hash("5"),
  },
  retention_disposition: {
    status: "ratified", policy_version: "retention-v1", approval_digest: hash("6"),
  },
  recovery_objectives: {
    status: "ratified", policy_version: "recovery-v1", approval_digest: hash("7"),
  },
});

const ownership = Object.freeze([
  Object.freeze([
    "external_objects", "search_documents", "vector_embeddings",
    "rebuildable_groups_indexes", "product_projections",
  ] as const),
  Object.freeze([
    "durable_work", "staged_results", "experiment_results", "authoritative_memory",
    "migration_state", "stranded_product_data",
  ] as const),
  Object.freeze(["account_access"] as const),
]);

interface FixtureOptions {
  readonly driftParticipant?: number;
  readonly failScanParticipant?: number;
  readonly partialDisposeParticipant?: number;
  readonly failFinalRevalidation?: boolean;
}

const fixture = (
  initial: ReadonlyMap<DeletionCleanupSurface, number>,
  options: FixtureOptions = {},
) => {
  const remaining = new Map(initial);
  const events: string[] = [];
  let dependencyCalls = 0;
  let revalidations = 0;
  const participants: DeletionSurfaceParticipant[] = ownership.map((surfaces, index) => ({
    participant_id: `store_${index}`,
    owned_surfaces: surfaces,
    async withHeldSurfaceFence(_coordinate, _operationRef, eligibilityDigest, callback) {
      dependencyCalls += 1;
      events.push(`hold:${index}`);
      let scans = 0;
      try {
        return await callback({
          async scanOwned() {
            scans += 1;
            events.push(`scan:${index}:${scans}`);
            if (options.failScanParticipant === index) throw new Error("private failure detail");
            const selected = options.driftParticipant === index && scans > 1
              ? surfaces.slice(1) : surfaces;
            return selected.map((surface, surfaceIndex) => ({
              version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
              inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION,
              scanner_contract_version: `composite-store-${index}-v1`,
              account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11, surface,
              source_frontier_digest: hash(String((index + surfaceIndex) % 10)),
              source_authorization_digest: eligibilityDigest,
              scan_fence_state: "held" as const,
              scan_fence_receipt_digest: hash("a"),
              remaining_count: remaining.get(surface) ?? 0,
              remaining_set_digest: hash((remaining.get(surface) ?? 0) > 0 ? "b" : "0"),
            }));
          },
          async disposeOwned(group) {
            events.push(`dispose:${index}:${group.join("+")}`);
            const result = group.map((surface) => {
              const existed = (remaining.get(surface) ?? 0) > 0;
              remaining.set(surface, 0);
              return {
                version: "deletion-cleanup-disposition-v1" as const,
                surface,
                result: existed ? "disposed" as const : "already_absent" as const,
                receipt_digest: hash("c"),
              };
            });
            return options.partialDisposeParticipant === index ? result.slice(1) : result;
          },
        });
      } finally {
        events.push(`release:${index}`);
      }
    },
  }));
  const coordinator: DeletionEligibilityFenceCoordinator = {
    async withHeldEligibilityFence(coordinate, _operationRef, eligibilityDigest, callback) {
      dependencyCalls += 1;
      events.push("hold:eligibility");
      try {
        return await callback({
          async revalidateExact(): Promise<EligibilityFenceRevalidationReceipt> {
            revalidations += 1;
            events.push(`revalidate:${revalidations}`);
            return {
              version: "deletion-cleanup-eligibility-fence-v1",
              ...coordinate,
              eligibility_digest: options.failFinalRevalidation && revalidations > 1
                ? hash("f") : eligibilityDigest,
              state: "held",
              fence_receipt_digest: hash("d"),
            };
          },
        });
      } finally {
        events.push("release:eligibility");
      }
    },
  };
  return { participants, coordinator, events, dependencyCalls: () => dependencyCalls };
};

const run = (f: ReturnType<typeof fixture>) => runAccountDeletionCleanupCycle({
  operation_ref: operation,
  plan_input: planInput(),
}, createCompositeAccountDeletionCleanupPort(f.coordinator, f.participants));

describe("account deletion cleanup composite", () => {
  test("rejects ownership gaps, overlap, and split atomic groups before dependency calls", () => {
    const gap = fixture(new Map());
    gap.participants[0] = { ...gap.participants[0]!, owned_surfaces: ownership[0]!.slice(1) };
    expect(() => createCompositeAccountDeletionCleanupPort(gap.coordinator, gap.participants))
      .toThrow(new DeletionCleanupCompositeError("invalid_configuration"));
    expect(gap.dependencyCalls()).toBe(0);

    const overlap = fixture(new Map());
    overlap.participants[2] = {
      ...overlap.participants[2]!, owned_surfaces: ["account_access", "authoritative_memory"],
    };
    expect(() => createCompositeAccountDeletionCleanupPort(overlap.coordinator, overlap.participants))
      .toThrow(new DeletionCleanupCompositeError("invalid_configuration"));
    expect(overlap.dependencyCalls()).toBe(0);

    const split = fixture(new Map());
    split.participants[0] = {
      ...split.participants[0]!, owned_surfaces: [...ownership[0]!, "staged_results"],
    };
    split.participants[1] = {
      ...split.participants[1]!, owned_surfaces: ownership[1]!.filter((s) => s !== "staged_results"),
    };
    expect(() => createCompositeAccountDeletionCleanupPort(split.coordinator, split.participants))
      .toThrow(new DeletionCleanupCompositeError("invalid_configuration"));
    expect(split.dependencyCalls()).toBe(0);
  });

  test("holds every participant, dispatches dependency groups, and zero-rescans all stores", async () => {
    const f = fixture(new Map([
      ["external_objects", 1], ["product_projections", 2],
      ["durable_work", 1], ["staged_results", 1],
      ["authoritative_memory", 3], ["account_access", 1],
    ]));
    await expect(run(f)).resolves.toMatchObject({
      kind: "complete",
      disposed_surfaces: [
        "external_objects", "product_projections", "durable_work", "staged_results",
        "authoritative_memory", "account_access",
      ],
    });
    expect(f.events.filter((event) => event.startsWith("dispose:"))).toEqual([
      "dispose:0:external_objects",
      "dispose:0:product_projections",
      "dispose:1:durable_work+staged_results",
      "dispose:1:authoritative_memory",
      "dispose:2:account_access",
    ]);
    expect(f.events.filter((event) => event.startsWith("scan:"))).toHaveLength(6);
    expect(f.events.slice(0, 6)).toEqual([
      "hold:eligibility", "hold:0", "hold:1", "hold:2", "revalidate:1", "scan:0:1",
    ]);
    expect(f.events.at(-1)).toBe("release:eligibility");
    expect(f.events).toContain("revalidate:2");
  });

  test("participant scan failure is closed and cannot expose provider detail", async () => {
    const f = fixture(new Map([["authoritative_memory", 1]]), { failScanParticipant: 1 });
    await expect(run(f)).rejects.toEqual(new DeletionCleanupCompositeError("scan_failed"));
    expect(f.events.some((event) => event.startsWith("dispose:"))).toBe(false);
  });

  test("an external participant fence failure is closed and cannot report completion", async () => {
    const f = fixture(new Map());
    f.participants[1] = {
      ...f.participants[1]!,
      async withHeldSurfaceFence() { throw new Error("external secret and provider path"); },
    };
    await expect(run(f)).rejects.toEqual(
      new DeletionCleanupCompositeError("participant_fence_failed"),
    );
    expect(f.events.some((event) => event.startsWith("scan:"))).toBe(false);
  });

  test("a participant or outer adapter cannot skip the nested callback and fabricate a result", async () => {
    const participantSkip = fixture(new Map());
    participantSkip.participants[1] = {
      ...participantSkip.participants[1]!,
      async withHeldSurfaceFence() { return { kind: "complete" } as never; },
    };
    await expect(run(participantSkip)).rejects.toEqual(
      new DeletionCleanupCompositeError("participant_fence_failed"),
    );

    const outerSkip = fixture(new Map());
    const dishonest: DeletionEligibilityFenceCoordinator = {
      async withHeldEligibilityFence() { return { kind: "complete" } as never; },
    };
    const port = createCompositeAccountDeletionCleanupPort(dishonest, outerSkip.participants);
    await expect(runAccountDeletionCleanupCycle({
      operation_ref: operation, plan_input: planInput(),
    }, port)).rejects.toEqual(new DeletionCleanupCompositeError("eligibility_fence_failed"));
  });

  test("drift after an await and partial disposal never become false completion", async () => {
    const drift = fixture(new Map([["authoritative_memory", 1]]), { driftParticipant: 1 });
    await expect(run(drift)).rejects.toEqual(new DeletionCleanupCompositeError("scan_failed"));

    const partial = fixture(new Map([
      ["durable_work", 1], ["staged_results", 1],
    ]), { partialDisposeParticipant: 1 });
    await expect(run(partial)).rejects.toEqual(new DeletionCleanupCompositeError("disposal_failed"));
    expect(partial.events.filter((event) => event.startsWith("scan:"))).toHaveLength(3);
  });

  test("final exact revalidation dominates an otherwise complete zero scan", async () => {
    const f = fixture(new Map([["external_objects", 1]]), { failFinalRevalidation: true });
    await expect(run(f)).rejects.toEqual(
      new DeletionCleanupCompositeError("eligibility_revalidation_failed"),
    );
    expect(f.events).toContain("scan:2:2");
    expect(f.events.at(-1)).toBe("release:eligibility");
  });

  test("inventory ownership is a frozen snapshot even if injected arrays later mutate", async () => {
    const f = fixture(new Map());
    const mutable = [...DELETION_CLEANUP_SURFACES];
    const single: DeletionSurfaceParticipant = {
      participant_id: "single",
      owned_surfaces: mutable,
      async withHeldSurfaceFence(_coordinate, _operationRef, eligibilityDigest, callback) {
        return callback({
          async scanOwned() {
            return DELETION_CLEANUP_SURFACES.map((surface) => ({
              version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
              inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION,
              scanner_contract_version: "single-v1", account_id: ACCOUNT,
              control_revision: 7, deletion_epoch: 11, surface,
              source_frontier_digest: hash("1"), source_authorization_digest: eligibilityDigest,
              scan_fence_state: "held" as const, scan_fence_receipt_digest: hash("2"),
              remaining_count: 0, remaining_set_digest: hash("0"),
            }));
          },
          async disposeOwned() { throw new Error("unreachable"); },
        });
      },
    };
    const port = createCompositeAccountDeletionCleanupPort(f.coordinator, [single]);
    mutable.length = 0;
    await expect(runAccountDeletionCleanupCycle({
      operation_ref: operation, plan_input: planInput(),
    }, port)).resolves.toMatchObject({ kind: "complete", disposed_surfaces: [] });
  });

  test("captured outer and participant callbacks cannot run after their fence method returns", async () => {
    const base = fixture(new Map());
    let outerCaptured: ((fence: Parameters<Parameters<DeletionEligibilityFenceCoordinator["withHeldEligibilityFence"]>[3]>[0]) => Promise<unknown>) | null = null;
    const outer: DeletionEligibilityFenceCoordinator = {
      async withHeldEligibilityFence(_coordinate, _operationRef, _digest, callback) {
        outerCaptured = callback as typeof outerCaptured;
        return { fabricated: true } as never;
      },
    };
    const outerPort = createCompositeAccountDeletionCleanupPort(outer, base.participants);
    await expect(outerPort.withHeldFence(
      { account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11 }, operation, hash("a"),
      async () => "never",
    )).rejects.toEqual(new DeletionCleanupCompositeError("eligibility_fence_failed"));
    await expect(outerCaptured!({
      async revalidateExact() { throw new Error("must not reach authority"); },
    })).rejects.toEqual(new DeletionCleanupCompositeError("eligibility_fence_failed"));

    const inner = fixture(new Map());
    let participantCaptured: ((session: Parameters<Parameters<DeletionSurfaceParticipant["withHeldSurfaceFence"]>[3]>[0]) => Promise<unknown>) | null = null;
    inner.participants[0] = {
      ...inner.participants[0]!,
      async withHeldSurfaceFence(_coordinate, _operationRef, _digest, callback) {
        participantCaptured = callback as typeof participantCaptured;
        return { fabricated: true } as never;
      },
    };
    await expect(run(inner)).rejects.toEqual(
      new DeletionCleanupCompositeError("participant_fence_failed"),
    );
    await expect(participantCaptured!({
      async scanOwned() { throw new Error("must not scan"); },
      async disposeOwned() { throw new Error("must not dispose"); },
    })).rejects.toEqual(new DeletionCleanupCompositeError("participant_fence_failed"));
  });

  test("an outer adapter returning during its callback cannot resume past a later await", async () => {
    const base = fixture(new Map());
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    let inFlight: Promise<unknown> | null = null;
    const racing: DeletionEligibilityFenceCoordinator = {
      async withHeldEligibilityFence(coordinate, _operationRef, eligibilityDigest, callback) {
        inFlight = callback({
          async revalidateExact() {
            await gate;
            return {
              version: "deletion-cleanup-eligibility-fence-v1", ...coordinate,
              eligibility_digest: eligibilityDigest, state: "held", fence_receipt_digest: hash("d"),
            };
          },
        });
        void inFlight.catch(() => undefined);
        return { fabricated: true } as never;
      },
    };
    const port = createCompositeAccountDeletionCleanupPort(racing, base.participants);
    await expect(port.withHeldFence(
      { account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11 }, operation, hash("a"),
      async (session) => { await session.scanAll(); return "must-not-complete"; },
    )).rejects.toEqual(new DeletionCleanupCompositeError("eligibility_fence_failed"));
    release();
    await expect(inFlight!).rejects.toEqual(
      new DeletionCleanupCompositeError("eligibility_fence_failed"),
    );
    expect(base.events.some((event) => event.startsWith("scan:"))).toBe(false);
  });

  test("drains an unawaited scan before final revalidation and fence release", async () => {
    const f = fixture(new Map());
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const original = f.participants[0]!;
    f.participants[0] = {
      ...original,
      async withHeldSurfaceFence(coordinate, operationRef, digest, callback) {
        return original.withHeldSurfaceFence(coordinate, operationRef, digest, async (session) =>
          callback({
            async scanOwned() { await gate; return session.scanOwned(); },
            disposeOwned: session.disposeOwned.bind(session),
          }));
      },
    };
    const port = createCompositeAccountDeletionCleanupPort(f.coordinator, f.participants);
    let settled = false;
    const completion = port.withHeldFence(
      { account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11 }, operation, hash("a"),
      async (session) => { void session.scanAll(); return "callback-returned"; },
    ).finally(() => { settled = true; });
    await Promise.resolve();
    await Promise.resolve();
    expect(settled).toBe(false);
    release();
    await expect(completion).resolves.toBe("callback-returned");
    expect(f.events.indexOf("revalidate:2")).toBeLessThan(f.events.indexOf("release:eligibility"));
  });

  test("snapshots participant and coordinator methods at construction", async () => {
    const f = fixture(new Map());
    const port = createCompositeAccountDeletionCleanupPort(f.coordinator, f.participants);
    (f.coordinator as { withHeldEligibilityFence: unknown }).withHeldEligibilityFence = async () => {
      throw new Error("mutated coordinator");
    };
    (f.participants[0] as { withHeldSurfaceFence: unknown }).withHeldSurfaceFence = async () => {
      throw new Error("mutated participant");
    };
    await expect(port.withHeldFence(
      { account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11 }, operation, hash("a"),
      async (session) => { await session.scanAll(); return "stable"; },
    )).resolves.toBe("stable");
  });

  test("rejects proxy and accessor receipts without executing them", async () => {
    const f = fixture(new Map());
    const original = f.participants[0]!;
    let getterCalls = 0;
    f.participants[0] = {
      ...original,
      async withHeldSurfaceFence(coordinate, operationRef, digest, callback) {
        return original.withHeldSurfaceFence(coordinate, operationRef, digest, async (session) =>
          callback({
            async scanOwned() {
              const rows = [...await session.scanOwned()];
              const hostile = { ...rows[0] };
              Object.defineProperty(hostile, "surface", {
                enumerable: true,
                get() { getterCalls += 1; return rows[0]!.surface; },
              });
              rows[0] = hostile as never;
              return rows;
            },
            disposeOwned: session.disposeOwned.bind(session),
          }));
      },
    };
    await expect(run(f)).rejects.toEqual(new DeletionCleanupCompositeError("scan_failed"));
    expect(getterCalls).toBe(0);
  });

  test("rejects accessor coordinates and proxy callbacks without invoking them", async () => {
    const f = fixture(new Map());
    const port = createCompositeAccountDeletionCleanupPort(f.coordinator, f.participants);
    let getterCalls = 0;
    const coordinate: Record<string, unknown> = { control_revision: 7, deletion_epoch: 11 };
    Object.defineProperty(coordinate, "account_id", {
      enumerable: true,
      get() { getterCalls += 1; return ACCOUNT; },
    });
    await expect(port.withHeldFence(
      coordinate as never, operation, hash("a"), async () => "unreachable",
    )).rejects.toEqual(new DeletionCleanupCompositeError("invalid_input"));
    expect(getterCalls).toBe(0);

    let callbackCalls = 0;
    const callback = new Proxy(async () => { callbackCalls += 1; return "unreachable"; }, {});
    await expect(port.withHeldFence(
      { account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11 },
      operation, hash("a"), callback,
    )).rejects.toEqual(new DeletionCleanupCompositeError("invalid_input"));
    expect(callbackCalls).toBe(0);
    expect(f.dependencyCalls()).toBe(0);
  });

  test("rejects decorated and proxy disposal groups before participant disposal", async () => {
    const f = fixture(new Map());
    const port = createCompositeAccountDeletionCleanupPort(f.coordinator, f.participants);
    const invoke = (surfaces: readonly DeletionCleanupSurface[]) => port.withHeldFence(
      { account_id: ACCOUNT, control_revision: 7, deletion_epoch: 11 }, operation, hash("a"),
      async (session) => session.dispose(surfaces),
    );
    const decorated = ["external_objects"] as DeletionCleanupSurface[] & { extra?: boolean };
    decorated.extra = true;
    await expect(invoke(decorated)).rejects.toEqual(
      new DeletionCleanupCompositeError("disposal_failed"),
    );
    await expect(invoke(new Proxy(["external_objects"] as DeletionCleanupSurface[], {})))
      .rejects.toEqual(new DeletionCleanupCompositeError("disposal_failed"));
    expect(f.events.some((event) => event.startsWith("dispose:"))).toBe(false);
  });
});
