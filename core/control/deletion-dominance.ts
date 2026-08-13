import { isProxy } from "node:util/types";

import {
  isWellFormedAccountId,
  type AccountControlConflict,
  type AccountControlProjection,
  type AccountGeneration,
} from "./account-control";
import {
  DELETION_CLEANUP_SURFACES,
  isVerifiedDeletionCleanupInventory,
  type DeletionCleanupSurface,
  type VerifiedDeletionCleanupInventory,
  type VerifiedDeletionInventoryRow,
} from "./deletion-cleanup-inventory";

export { DELETION_CLEANUP_SURFACES } from "./deletion-cleanup-inventory";
export type { DeletionCleanupSurface } from "./deletion-cleanup-inventory";

export const DELETION_DOMINANCE_PLAN_VERSION = "deletion-dominance-plan-v1" as const;

const DIGEST = /^[0-9a-f]{64}$/;
const MAX_COORDINATE_LENGTH = 256;

const GENERATIONS = Object.freeze([
  "legacy",
  "migrating",
  "new",
  "rolled_back_stranded",
] as const satisfies readonly AccountGeneration[]);

export type LifecycleOperationMode =
  | "control_unavailable"
  | "legacy_active"
  | "migration_fenced"
  | "destination_fenced"
  | "destination_active"
  | "stranded_fenced"
  | "deletion_pending"
  | "deleted_blocked"
  | "deleted_cleanup_ready"
  | "deleted_complete";

export type DeletionDominanceObligation =
  | "deny_data_plane_requests"
  | "deny_new_model_work"
  | "drain_or_reject_leases"
  | "suppress_outbox_effects"
  | "stop_migration_resume"
  | "stop_projection_rebuild"
  | "stop_index_rebuild"
  | "deactivate_destination_epoch"
  | "await_terminal_control"
  | "consult_item_tombstones_on_migration_resume"
  | "retain_terminal_control_tombstone"
  | "require_terminal_export_receipt"
  | "require_verified_cleanup_inventory"
  | "replay_tombstones_before_restore_traffic"
  | "require_retention_disposition_approval"
  | "require_recovery_objectives_approval"
  | "require_legal_hold_verification"
  | "isolate_legal_hold_content"
  | "dispose_policy_authorized_surfaces";

export type DeletionCleanupBlocker =
  | "control_unavailable"
  | "terminal_control_not_replayed"
  | "terminal_export_receipt_missing"
  | "cleanup_inventory_unverified"
  | "restore_replay_incomplete"
  | "legal_hold_unverified"
  | "legal_hold_active"
  | "retention_disposition_unratified"
  | "recovery_objectives_unratified";

export interface TerminalControlTombstone {
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly account_generation: AccountGeneration;
  readonly transitioned_at_epoch_seconds: number;
  readonly content_digest: string;
}

export interface TerminalDeletionExportReceipt {
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly account_generation: AccountGeneration;
  readonly stranded_data_present: boolean;
  readonly export_contract_version: string;
  readonly export_record_digest: string;
  readonly retention_locked_sink_receipt_digest: string;
}

export type RestoreReplayState =
  | { readonly state: "not_required" }
  | {
      readonly state: "required";
      readonly checkpoint: null | {
        readonly account_id: string;
        readonly through_control_revision: number;
        readonly through_deletion_epoch: number;
        readonly checkpoint_digest: string;
      };
    };

export type RatificationCoordinate =
  | { readonly status: "unratified" }
  | {
      readonly status: "ratified";
      readonly policy_version: string;
      readonly approval_digest: string;
    };

/**
 * An externally authorized disposition check. `held` blocks physical cleanup
 * but never relaxes lifecycle fences; this core neither places nor releases
 * holds.
 */
export type LegalHoldCoordinate =
  | { readonly status: "unverified" }
  | {
      readonly status: "clear" | "held";
      readonly policy_version: string;
      readonly disposition_receipt_digest: string;
    };

export type DeletionSurfaceInventoryRow = VerifiedDeletionInventoryRow;

export interface DeletionDominanceInput {
  readonly control_projection: AccountControlProjection | null;
  readonly terminal_control_tombstone: TerminalControlTombstone | null;
  readonly terminal_export_receipt: TerminalDeletionExportReceipt | null;
  readonly restore_replay: RestoreReplayState;
  readonly legal_hold: LegalHoldCoordinate;
  readonly retention_disposition: RatificationCoordinate;
  readonly recovery_objectives: RatificationCoordinate;
  readonly inventory: VerifiedDeletionCleanupInventory | null;
}

export interface DeletionActivityFences {
  /** `false` means only that lifecycle does not fence; it never grants authority. */
  readonly request_reads: boolean;
  readonly request_writes: boolean;
  readonly new_model_work: boolean;
  readonly lease_resume: boolean;
  readonly outbox_effects: boolean;
  readonly migration_resume: boolean;
  readonly projection_rebuild: boolean;
  readonly index_rebuild: boolean;
}

export interface DeletionDominancePlan {
  readonly version: typeof DELETION_DOMINANCE_PLAN_VERSION;
  readonly mode: LifecycleOperationMode;
  readonly account_id: string | null;
  readonly control_revision: number | null;
  readonly deletion_epoch: number | null;
  readonly fences: DeletionActivityFences;
  readonly obligations: readonly DeletionDominanceObligation[];
  readonly cleanup: {
    readonly state: "not_applicable" | "blocked" | "ready" | "complete";
    readonly blockers: readonly DeletionCleanupBlocker[];
    readonly remaining_total: number;
    readonly remaining_surfaces: readonly DeletionCleanupSurface[];
  };
}

export type DeletionDominanceInputErrorCode =
  | "invalid_input"
  | "invalid_control_projection"
  | "invalid_terminal_tombstone"
  | "invalid_terminal_export_receipt"
  | "invalid_restore_replay"
  | "invalid_legal_hold_coordinate"
  | "invalid_ratification_coordinate"
  | "invalid_inventory"
  | "account_coordinate_mismatch"
  | "terminal_coordinate_mismatch";

export class DeletionDominanceInputError extends TypeError {
  readonly code: DeletionDominanceInputErrorCode;

  constructor(code: DeletionDominanceInputErrorCode) {
    super(code);
    this.name = "DeletionDominanceInputError";
    this.code = code;
  }
}

const fail = (code: DeletionDominanceInputErrorCode): never => {
  throw new DeletionDominanceInputError(code);
};

type PlainRecord = Record<string, unknown>;

const exactPlainRecord = (
  value: unknown,
  keys: readonly string[],
  code: DeletionDominanceInputErrorCode,
): PlainRecord => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key !== "string")
    || ownKeys.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail(code);
  for (const descriptor of Object.values(descriptors)) {
    if (!("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as PlainRecord;
};

const plainDiscriminant = (
  value: unknown,
  key: string,
  code: DeletionDominanceInputErrorCode,
): unknown => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  if (descriptor === undefined || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  return descriptor.value;
};

const safeEpoch = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const boundedCoordinate = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && value.length <= MAX_COORDINATE_LENGTH
  && /^[\x21-\x7e]+$/.test(value);

const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);

const generation = (value: unknown): value is AccountGeneration =>
  typeof value === "string" && (GENERATIONS as readonly string[]).includes(value);

const parseConflict = (value: unknown): AccountControlConflict | null => {
  if (value === null) return null;
  const row = exactPlainRecord(value, ["at_control_revision", "detail"], "invalid_control_projection");
  const details = [
    "malformed_observation",
    "account_id_mismatch",
    "stale_observation",
    "conflicting_observation",
    "unordered_generation_transition",
    "unordered_epoch",
    "withdrawn_epoch",
    "unordered_lifecycle",
    "mutated_deletion_epoch",
    "projection_conflicted",
  ];
  if (!(typeof row.at_control_revision === "number" && Number.isSafeInteger(row.at_control_revision)
    && row.at_control_revision >= -1) || typeof row.detail !== "string"
    || !details.includes(row.detail)) fail("invalid_control_projection");
  return value as AccountControlConflict;
};

const parseProjection = (value: unknown): AccountControlProjection | null => {
  if (value === null) return null;
  const row = exactPlainRecord(value, [
    "account_id",
    "control_revision",
    "account_generation",
    "account_epoch",
    "lifecycle_state",
    "deletion_epoch",
    "activation",
    "conflict",
  ], "invalid_control_projection");
  if (!isWellFormedAccountId(row.account_id) || !safeEpoch(row.control_revision)
    || !generation(row.account_generation)
    || !(row.account_epoch === null || safeEpoch(row.account_epoch))
    || !(["active", "deletion_pending", "deleted"] as const).includes(row.lifecycle_state as never)
    || !(row.deletion_epoch === null || safeEpoch(row.deletion_epoch))
    || (row.lifecycle_state === "active") !== (row.deletion_epoch === null)) {
    fail("invalid_control_projection");
  }
  if (row.activation !== null) {
    const activation = exactPlainRecord(
      row.activation,
      ["activated_epoch", "at_control_revision"],
      "invalid_control_projection",
    );
    if (!safeEpoch(activation.activated_epoch) || !safeEpoch(activation.at_control_revision)
      || row.account_generation !== "new" || row.account_epoch !== activation.activated_epoch
      || activation.at_control_revision > (row.control_revision as number)) fail("invalid_control_projection");
  }
  parseConflict(row.conflict);
  return value as AccountControlProjection;
};

const parseTombstone = (value: unknown): TerminalControlTombstone | null => {
  if (value === null) return null;
  const row = exactPlainRecord(value, [
    "account_id",
    "control_revision",
    "deletion_epoch",
    "account_generation",
    "transitioned_at_epoch_seconds",
    "content_digest",
  ], "invalid_terminal_tombstone");
  if (!isWellFormedAccountId(row.account_id) || !safeEpoch(row.control_revision)
    || !safeEpoch(row.deletion_epoch) || !generation(row.account_generation)
    || !safeEpoch(row.transitioned_at_epoch_seconds) || !digest(row.content_digest)) {
    fail("invalid_terminal_tombstone");
  }
  return value as TerminalControlTombstone;
};

const parseExportReceipt = (value: unknown): TerminalDeletionExportReceipt | null => {
  if (value === null) return null;
  const row = exactPlainRecord(value, [
    "account_id",
    "control_revision",
    "deletion_epoch",
    "account_generation",
    "stranded_data_present",
    "export_contract_version",
    "export_record_digest",
    "retention_locked_sink_receipt_digest",
  ], "invalid_terminal_export_receipt");
  if (!isWellFormedAccountId(row.account_id) || !safeEpoch(row.control_revision)
    || !safeEpoch(row.deletion_epoch) || !generation(row.account_generation)
    || typeof row.stranded_data_present !== "boolean"
    || !boundedCoordinate(row.export_contract_version)
    || !digest(row.export_record_digest) || !digest(row.retention_locked_sink_receipt_digest)) {
    fail("invalid_terminal_export_receipt");
  }
  return value as TerminalDeletionExportReceipt;
};

const parseRestoreReplay = (value: unknown): RestoreReplayState => {
  const state = plainDiscriminant(value, "state", "invalid_restore_replay");
  if (state === "not_required") {
    exactPlainRecord(value, ["state"], "invalid_restore_replay");
    return value as RestoreReplayState;
  }
  const row = exactPlainRecord(value, ["state", "checkpoint"], "invalid_restore_replay");
  if (row.state !== "required") fail("invalid_restore_replay");
  if (row.checkpoint !== null) {
    const checkpoint = exactPlainRecord(row.checkpoint, [
      "account_id",
      "through_control_revision",
      "through_deletion_epoch",
      "checkpoint_digest",
    ], "invalid_restore_replay");
    if (!isWellFormedAccountId(checkpoint.account_id)
      || !safeEpoch(checkpoint.through_control_revision)
      || !safeEpoch(checkpoint.through_deletion_epoch)
      || !digest(checkpoint.checkpoint_digest)) fail("invalid_restore_replay");
  }
  return value as RestoreReplayState;
};

const parseRatification = (value: unknown): RatificationCoordinate => {
  const status = plainDiscriminant(value, "status", "invalid_ratification_coordinate");
  if (status === "unratified") {
    exactPlainRecord(value, ["status"], "invalid_ratification_coordinate");
    return value as RatificationCoordinate;
  }
  const row = exactPlainRecord(
    value,
    ["status", "policy_version", "approval_digest"],
    "invalid_ratification_coordinate",
  );
  if (row.status !== "ratified" || !boundedCoordinate(row.policy_version)
    || !digest(row.approval_digest)) fail("invalid_ratification_coordinate");
  return value as RatificationCoordinate;
};

const parseLegalHold = (value: unknown): LegalHoldCoordinate => {
  const status = plainDiscriminant(value, "status", "invalid_legal_hold_coordinate");
  if (status === "unverified") {
    exactPlainRecord(value, ["status"], "invalid_legal_hold_coordinate");
    return value as LegalHoldCoordinate;
  }
  const row = exactPlainRecord(
    value,
    ["status", "policy_version", "disposition_receipt_digest"],
    "invalid_legal_hold_coordinate",
  );
  if ((row.status !== "clear" && row.status !== "held")
    || !boundedCoordinate(row.policy_version)
    || !digest(row.disposition_receipt_digest)) fail("invalid_legal_hold_coordinate");
  return value as LegalHoldCoordinate;
};

const emptyInventory = Object.freeze(DELETION_CLEANUP_SURFACES.map((surface) => Object.freeze({
  surface,
  remaining_count: 0,
})));

const fenceAll = (): DeletionActivityFences => Object.freeze({
  request_reads: true,
  request_writes: true,
  new_model_work: true,
  lease_resume: true,
  outbox_effects: true,
  migration_resume: true,
  projection_rebuild: true,
  index_rebuild: true,
});

const activeFences = (mode: LifecycleOperationMode): DeletionActivityFences => {
  if (mode === "destination_active") {
    return Object.freeze({
      request_reads: false,
      request_writes: false,
      new_model_work: false,
      lease_resume: false,
      outbox_effects: false,
      migration_resume: true,
      projection_rebuild: false,
      index_rebuild: false,
    });
  }
  if (mode === "migration_fenced") {
    return Object.freeze({ ...fenceAll(), migration_resume: false });
  }
  return fenceAll();
};

const baseDeletionObligations = Object.freeze([
  "deny_data_plane_requests",
  "deny_new_model_work",
  "drain_or_reject_leases",
  "suppress_outbox_effects",
  "stop_migration_resume",
  "stop_projection_rebuild",
  "stop_index_rebuild",
] as const satisfies readonly DeletionDominanceObligation[]);

const freezeObligations = (
  obligations: readonly DeletionDominanceObligation[],
): readonly DeletionDominanceObligation[] => Object.freeze([...obligations]);

const freezeCleanup = (
  state: DeletionDominancePlan["cleanup"]["state"],
  blockers: readonly DeletionCleanupBlocker[],
  inventory: readonly DeletionSurfaceInventoryRow[],
): DeletionDominancePlan["cleanup"] => Object.freeze({
  state,
  blockers: Object.freeze([...blockers]),
  remaining_total: inventory.reduce((total, row) => total + row.remaining_count, 0),
  remaining_surfaces: Object.freeze(inventory
    .filter((row) => row.remaining_count > 0)
    .map((row) => row.surface)),
});

/**
 * Produces obligations only. It never mutates control state or executes data
 * disposition. The caller must bind any future executor to the exact same
 * account/control/deletion coordinates through a separately authorized port.
 */
export const planDeletionDominance = (inputValue: unknown): DeletionDominancePlan => {
  const input = exactPlainRecord(inputValue, [
    "control_projection",
    "terminal_control_tombstone",
    "terminal_export_receipt",
    "restore_replay",
    "legal_hold",
    "retention_disposition",
    "recovery_objectives",
    "inventory",
  ], "invalid_input");
  const projection = parseProjection(input.control_projection);
  const tombstone = parseTombstone(input.terminal_control_tombstone);
  const exportReceipt = parseExportReceipt(input.terminal_export_receipt);
  const restoreReplay = parseRestoreReplay(input.restore_replay);
  const legalHold = parseLegalHold(input.legal_hold);
  const retention = parseRatification(input.retention_disposition);
  const recovery = parseRatification(input.recovery_objectives);
  const verifiedInventory = input.inventory === null
    ? null
    : isVerifiedDeletionCleanupInventory(input.inventory)
      ? input.inventory
      : fail("invalid_inventory");
  const inventory = verifiedInventory?.rows ?? emptyInventory;

  const accountIds = [
    projection?.account_id,
    tombstone?.account_id,
    exportReceipt?.account_id,
    verifiedInventory?.account_id,
  ]
    .filter((value): value is string => value !== undefined);
  if (new Set(accountIds).size > 1) fail("account_coordinate_mismatch");
  if (restoreReplay.state === "required" && restoreReplay.checkpoint !== null
    && accountIds.length > 0 && restoreReplay.checkpoint.account_id !== accountIds[0]) {
    fail("account_coordinate_mismatch");
  }
  if (exportReceipt !== null) {
    if (tombstone === null
      || exportReceipt.control_revision !== tombstone.control_revision
      || exportReceipt.deletion_epoch !== tombstone.deletion_epoch
      || exportReceipt.account_generation !== tombstone.account_generation) {
      fail("terminal_coordinate_mismatch");
    }
    const stranded = inventory.find((row) => row.surface === "stranded_product_data")!;
    if (stranded.remaining_count > 0 && !exportReceipt.stranded_data_present) {
      fail("terminal_coordinate_mismatch");
    }
  }
  if (verifiedInventory !== null) {
    if (tombstone === null
      || verifiedInventory.control_revision !== tombstone.control_revision
      || verifiedInventory.deletion_epoch !== tombstone.deletion_epoch) {
      fail("terminal_coordinate_mismatch");
    }
  }
  if (projection?.lifecycle_state === "deleted") {
    if (tombstone === null
      || tombstone.control_revision !== projection.control_revision
      || tombstone.deletion_epoch !== projection.deletion_epoch
      || tombstone.account_generation !== projection.account_generation) {
      fail("terminal_coordinate_mismatch");
    }
  }
  if (tombstone !== null && projection !== null) {
    if (projection.control_revision > tombstone.control_revision
      || (projection.control_revision === tombstone.control_revision
        && (projection.lifecycle_state !== "deleted"
          || projection.deletion_epoch !== tombstone.deletion_epoch
          || projection.account_generation !== tombstone.account_generation))) {
      fail("terminal_coordinate_mismatch");
    }
  }

  const accountId = accountIds[0] ?? null;
  const controlRevision = tombstone?.control_revision ?? projection?.control_revision ?? null;
  const deletionEpoch = tombstone?.deletion_epoch ?? projection?.deletion_epoch ?? null;

  if (projection === null || projection.conflict !== null) {
    return Object.freeze({
      version: DELETION_DOMINANCE_PLAN_VERSION,
      mode: "control_unavailable",
      account_id: accountId,
      control_revision: controlRevision,
      deletion_epoch: deletionEpoch,
      fences: fenceAll(),
      obligations: freezeObligations([
        ...baseDeletionObligations,
        ...(tombstone === null ? [] : ["replay_tombstones_before_restore_traffic" as const]),
      ]),
      cleanup: freezeCleanup("blocked", ["control_unavailable"], inventory),
    });
  }

  const restoredBehindTerminal = tombstone !== null
    && projection.control_revision < tombstone.control_revision;
  if (restoredBehindTerminal) {
    const blockers: DeletionCleanupBlocker[] = ["terminal_control_not_replayed"];
    if (exportReceipt === null) blockers.push("terminal_export_receipt_missing");
    if (verifiedInventory === null) blockers.push("cleanup_inventory_unverified");
    if (legalHold.status === "unverified") blockers.push("legal_hold_unverified");
    if (legalHold.status === "held") blockers.push("legal_hold_active");
    if (retention.status !== "ratified") blockers.push("retention_disposition_unratified");
    if (recovery.status !== "ratified") blockers.push("recovery_objectives_unratified");
    return Object.freeze({
      version: DELETION_DOMINANCE_PLAN_VERSION,
      mode: "deleted_blocked",
      account_id: accountId,
      control_revision: tombstone.control_revision,
      deletion_epoch: tombstone.deletion_epoch,
      fences: fenceAll(),
      obligations: freezeObligations([
        ...baseDeletionObligations,
        ...(projection.activation === null ? [] : ["deactivate_destination_epoch" as const]),
        "retain_terminal_control_tombstone",
        ...(exportReceipt === null ? ["require_terminal_export_receipt" as const] : []),
        ...(verifiedInventory === null ? ["require_verified_cleanup_inventory" as const] : []),
        "replay_tombstones_before_restore_traffic",
        ...(legalHold.status === "unverified"
          ? ["require_legal_hold_verification" as const]
          : legalHold.status === "held"
            ? ["isolate_legal_hold_content" as const]
            : []),
        ...(retention.status === "ratified" ? [] : ["require_retention_disposition_approval" as const]),
        ...(recovery.status === "ratified" ? [] : ["require_recovery_objectives_approval" as const]),
      ]),
      cleanup: freezeCleanup("blocked", blockers, inventory),
    });
  }

  if (projection.lifecycle_state === "active") {
    if (tombstone !== null || exportReceipt !== null || verifiedInventory !== null) {
      fail("terminal_coordinate_mismatch");
    }
    let mode: LifecycleOperationMode;
    switch (projection.account_generation) {
      case "legacy": mode = "legacy_active"; break;
      case "migrating": mode = "migration_fenced"; break;
      case "rolled_back_stranded": mode = "stranded_fenced"; break;
      case "new":
        mode = projection.account_epoch !== null
          && projection.activation?.activated_epoch === projection.account_epoch
          ? "destination_active"
          : "destination_fenced";
        break;
    }
    return Object.freeze({
      version: DELETION_DOMINANCE_PLAN_VERSION,
      mode,
      account_id: projection.account_id,
      control_revision: projection.control_revision,
      deletion_epoch: null,
      fences: activeFences(mode),
      obligations: freezeObligations(mode === "migration_fenced"
        ? ["consult_item_tombstones_on_migration_resume" as const]
        : []),
      cleanup: freezeCleanup("not_applicable", [], inventory),
    });
  }

  if (projection.lifecycle_state === "deletion_pending") {
    if (tombstone !== null || exportReceipt !== null || verifiedInventory !== null) {
      fail("terminal_coordinate_mismatch");
    }
    return Object.freeze({
      version: DELETION_DOMINANCE_PLAN_VERSION,
      mode: "deletion_pending",
      account_id: projection.account_id,
      control_revision: projection.control_revision,
      deletion_epoch: projection.deletion_epoch,
      fences: fenceAll(),
      obligations: freezeObligations([
        ...baseDeletionObligations,
        ...(projection.activation === null ? [] : ["deactivate_destination_epoch" as const]),
        "await_terminal_control",
      ]),
      cleanup: freezeCleanup("not_applicable", [], inventory),
    });
  }

  if (tombstone === null) fail("terminal_coordinate_mismatch");
  const blockers: DeletionCleanupBlocker[] = [];
  if (exportReceipt === null) blockers.push("terminal_export_receipt_missing");
  if (verifiedInventory === null) blockers.push("cleanup_inventory_unverified");
  const restoreCheckpoint = restoreReplay.state === "required" ? restoreReplay.checkpoint : null;
  if (restoreReplay.state === "required"
    && (restoreCheckpoint === null
      || restoreCheckpoint.through_control_revision < tombstone.control_revision
      || restoreCheckpoint.through_deletion_epoch < tombstone.deletion_epoch)) {
    blockers.push("restore_replay_incomplete");
  }
  if (legalHold.status === "unverified") blockers.push("legal_hold_unverified");
  if (legalHold.status === "held") blockers.push("legal_hold_active");
  if (retention.status !== "ratified") blockers.push("retention_disposition_unratified");
  if (recovery.status !== "ratified") blockers.push("recovery_objectives_unratified");

  const remainingTotal = inventory.reduce((total, row) => total + row.remaining_count, 0);
  const cleanupState = blockers.length > 0 ? "blocked" : remainingTotal > 0 ? "ready" : "complete";
  const mode: LifecycleOperationMode = cleanupState === "blocked"
    ? "deleted_blocked"
    : cleanupState === "ready"
      ? "deleted_cleanup_ready"
      : "deleted_complete";
  const obligations: DeletionDominanceObligation[] = [
    ...baseDeletionObligations,
    ...(projection.activation === null ? [] : ["deactivate_destination_epoch" as const]),
    "retain_terminal_control_tombstone",
    ...(exportReceipt === null ? ["require_terminal_export_receipt" as const] : []),
    ...(verifiedInventory === null ? ["require_verified_cleanup_inventory" as const] : []),
    "replay_tombstones_before_restore_traffic",
    ...(legalHold.status === "unverified"
      ? ["require_legal_hold_verification" as const]
      : legalHold.status === "held"
        ? ["isolate_legal_hold_content" as const]
        : []),
    ...(retention.status === "ratified" ? [] : ["require_retention_disposition_approval" as const]),
    ...(recovery.status === "ratified" ? [] : ["require_recovery_objectives_approval" as const]),
    ...(cleanupState === "ready" ? ["dispose_policy_authorized_surfaces" as const] : []),
  ];
  return Object.freeze({
    version: DELETION_DOMINANCE_PLAN_VERSION,
    mode,
    account_id: projection.account_id,
    control_revision: projection.control_revision,
    deletion_epoch: projection.deletion_epoch,
    fences: fenceAll(),
    obligations: freezeObligations(obligations),
    cleanup: freezeCleanup(cleanupState, blockers, inventory),
  });
};
