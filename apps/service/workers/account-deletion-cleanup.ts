import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import {
  verifyDeletionCleanupInventory,
  type DeletionCleanupSurface,
  type DeletionInventorySourceReceipt,
} from "../../../core/control/deletion-cleanup-inventory";
import {
  planDeletionDominance,
  type DeletionDominanceInput,
  type DeletionCleanupBlocker,
} from "../../../core/control/deletion-dominance";

const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;

/** Child/derived surfaces precede their authoritative inputs. */
export const DELETION_DISPOSAL_ORDER = Object.freeze([
  "external_objects",
  "search_documents",
  "vector_embeddings",
  "rebuildable_groups_indexes",
  "product_projections",
  "experiment_results",
  "staged_results",
  "durable_work",
  "authoritative_memory",
  "migration_state",
  "stranded_product_data",
  "account_access",
] as const satisfies readonly DeletionCleanupSurface[]);

const disposalRank = new Map<DeletionCleanupSurface, number>(
  DELETION_DISPOSAL_ORDER.map((surface, index) => [surface, index]),
);

export interface DeletionCleanupDispositionReceipt {
  readonly version: "deletion-cleanup-disposition-v1";
  readonly surface: DeletionCleanupSurface;
  readonly result: "disposed" | "already_absent";
  readonly receipt_digest: string;
}

export interface HeldDeletionCleanupSession {
  scanAll(): Promise<readonly DeletionInventorySourceReceipt[]>;
  dispose(surface: DeletionCleanupSurface): Promise<DeletionCleanupDispositionReceipt>;
}

export interface AccountDeletionCleanupPort {
  withHeldFence<T>(
    coordinate: Readonly<{ account_id: string; control_revision: number; deletion_epoch: number }>,
    operationRef: string,
    eligibilityDigest: string,
    callback: (session: HeldDeletionCleanupSession) => Promise<T>,
  ): Promise<T>;
}

export interface AccountDeletionCleanupCycleInput {
  readonly operation_ref: string;
  readonly plan_input: Omit<DeletionDominanceInput, "inventory">;
}

export type AccountDeletionCleanupCycleOutcome =
  | Readonly<{
      kind: "blocked";
      mode: "deleted_blocked";
      blockers: readonly DeletionCleanupBlocker[];
      inventory_digest: string | null;
    }>
  | Readonly<{
      kind: "retryable";
      error_code: "scan_failed" | "disposal_failed" | "postcondition_failed";
    }>
  | Readonly<{
      kind: "complete";
      before_inventory_digest: string;
      after_inventory_digest: string;
      disposed_surfaces: readonly DeletionCleanupSurface[];
      disposition_set_digest: string;
    }>;

const digest = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) throw new TypeError("invalid cleanup input");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) {
    throw new TypeError("invalid cleanup input");
  }
  const result: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      throw new TypeError("invalid cleanup input");
    }
    result[key] = descriptor.value;
  }
  return result;
};

const retryable = (
  error_code: Extract<AccountDeletionCleanupCycleOutcome, { kind: "retryable" }> ["error_code"],
): AccountDeletionCleanupCycleOutcome => Object.freeze({ kind: "retryable" as const, error_code });

const validatedInput = (value: AccountDeletionCleanupCycleInput): AccountDeletionCleanupCycleInput => {
  const input = exactRecord(value, ["operation_ref", "plan_input"]);
  const plan = exactRecord(input["plan_input"], [
    "control_projection", "terminal_control_tombstone", "terminal_export_receipt",
    "restore_replay", "legal_hold", "retention_disposition", "recovery_objectives",
  ]);
  const detached = Object.freeze({
    operation_ref: input["operation_ref"] as string,
    plan_input: Object.freeze(plan) as unknown as Omit<DeletionDominanceInput, "inventory">,
  });
  // Reuse the authoritative strict parser before the port can observe input.
  planDeletionDominance({ ...detached.plan_input, inventory: null });
  return detached;
};

const exactCoordinate = (input: AccountDeletionCleanupCycleInput) => {
  if (!OPERATION_REF.test(input.operation_ref)) throw new TypeError("invalid cleanup operation ref");
  const projection = input.plan_input.control_projection;
  const tombstone = input.plan_input.terminal_control_tombstone;
  if (projection === null || tombstone === null || projection.lifecycle_state !== "deleted"
    || projection.account_id !== tombstone.account_id
    || projection.control_revision !== tombstone.control_revision
    || projection.deletion_epoch !== tombstone.deletion_epoch) {
    throw new TypeError("cleanup requires exact terminal coordinates");
  }
  return Object.freeze({
    account_id: tombstone.account_id,
    control_revision: tombstone.control_revision,
    deletion_epoch: tombstone.deletion_epoch,
  });
};

const eligibilityDigest = (input: AccountDeletionCleanupCycleInput): string => {
  const plan = input.plan_input;
  const tombstone = plan.terminal_control_tombstone!;
  const receipt = plan.terminal_export_receipt;
  return digest({
    version: "deletion-cleanup-eligibility-v1",
    account_id: tombstone.account_id,
    control_revision: tombstone.control_revision,
    deletion_epoch: tombstone.deletion_epoch,
    tombstone_content_digest: tombstone.content_digest,
    terminal_export: receipt === null ? null : {
      export_record_digest: receipt.export_record_digest,
      retention_locked_sink_receipt_digest: receipt.retention_locked_sink_receipt_digest,
    },
    restore_replay: plan.restore_replay,
    legal_hold: plan.legal_hold,
    retention_disposition: plan.retention_disposition,
    recovery_objectives: plan.recovery_objectives,
  });
};

const inventoryFrom = (
  input: AccountDeletionCleanupCycleInput,
  receipts: readonly DeletionInventorySourceReceipt[],
) => {
  const coordinate = exactCoordinate(input);
  return verifyDeletionCleanupInventory({
    terminal_coordinate: coordinate,
    source_receipts: receipts,
  });
};

/**
 * Runs one complete cleanup attempt inside a single adapter-owned source
 * fence. The adapter may delete only a named surface. Completion requires a
 * fresh, complete, held-fence zero scan after every disposal.
 */
export const runAccountDeletionCleanupCycle = async (
  inputValue: AccountDeletionCleanupCycleInput,
  port: AccountDeletionCleanupPort,
): Promise<AccountDeletionCleanupCycleOutcome> => {
  const input = validatedInput(inputValue);
  const coordinate = exactCoordinate(input);
  const eligibility = eligibilityDigest(input);
  return port.withHeldFence(coordinate, input.operation_ref, eligibility, async (session) => {
    let before;
    try {
      before = inventoryFrom(input, await session.scanAll());
    } catch {
      return retryable("scan_failed");
    }
    if (before.verified_inventory === null || before.report.inventory_digest === null) {
      return retryable("scan_failed");
    }
    const beforePlan = planDeletionDominance({
      ...input.plan_input,
      inventory: before.verified_inventory,
    });
    if (beforePlan.mode === "deleted_blocked") {
      return Object.freeze({
        kind: "blocked" as const,
        mode: "deleted_blocked" as const,
        blockers: Object.freeze([...beforePlan.cleanup.blockers]),
        inventory_digest: before.report.inventory_digest,
      });
    }
    if (beforePlan.mode === "deleted_complete") {
      return Object.freeze({
        kind: "complete" as const,
        before_inventory_digest: before.report.inventory_digest,
        after_inventory_digest: before.report.inventory_digest,
        disposed_surfaces: Object.freeze([]),
        disposition_set_digest: digest({
          version: "deletion-disposition-set-v1",
          operation_ref: input.operation_ref,
          eligibility_digest: eligibility,
          receipts: [],
        }),
      });
    }
    if (beforePlan.mode !== "deleted_cleanup_ready") return retryable("postcondition_failed");

    const dispositions: DeletionCleanupDispositionReceipt[] = [];
    const orderedSurfaces = [...beforePlan.cleanup.remaining_surfaces]
      .sort((left, right) => disposalRank.get(left)! - disposalRank.get(right)!);
    for (const surface of orderedSurfaces) {
      let receipt: DeletionCleanupDispositionReceipt;
      try {
        receipt = await session.dispose(surface);
      } catch {
        return retryable("disposal_failed");
      }
      if (receipt.version !== "deletion-cleanup-disposition-v1"
        || receipt.surface !== surface
        || (receipt.result !== "disposed" && receipt.result !== "already_absent")
        || !/^[0-9a-f]{64}$/.test(receipt.receipt_digest)) {
        return retryable("disposal_failed");
      }
      dispositions.push(Object.freeze({ ...receipt }));
    }

    let after;
    try {
      after = inventoryFrom(input, await session.scanAll());
    } catch {
      return retryable("scan_failed");
    }
    if (after.verified_inventory === null || after.report.inventory_digest === null) {
      return retryable("scan_failed");
    }
    const afterPlan = planDeletionDominance({
      ...input.plan_input,
      inventory: after.verified_inventory,
    });
    if (afterPlan.mode !== "deleted_complete") return retryable("postcondition_failed");

    return Object.freeze({
      kind: "complete" as const,
      before_inventory_digest: before.report.inventory_digest,
      after_inventory_digest: after.report.inventory_digest,
      disposed_surfaces: Object.freeze(dispositions.map((receipt) => receipt.surface)),
      disposition_set_digest: digest({
        version: "deletion-disposition-set-v1",
        operation_ref: input.operation_ref,
        eligibility_digest: eligibility,
        receipts: dispositions,
      }),
    });
  });
};
