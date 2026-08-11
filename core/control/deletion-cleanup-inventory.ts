import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "./account-control";

export const DELETION_INVENTORY_CONTRACT_VERSION = "deletion-cleanup-inventory-v1" as const;
export const DELETION_INVENTORY_SOURCE_RECEIPT_VERSION = "deletion-inventory-source-receipt-v1" as const;

export const DELETION_CLEANUP_SURFACES = Object.freeze([
  "durable_work",
  "staged_results",
  "experiment_results",
  "product_projections",
  "search_documents",
  "vector_embeddings",
  "rebuildable_groups_indexes",
  "migration_state",
  "stranded_product_data",
  "external_objects",
] as const);

export type DeletionCleanupSurface = typeof DELETION_CLEANUP_SURFACES[number];

export interface DeletionInventoryTerminalCoordinate {
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
}

export interface DeletionInventorySourceReceipt {
  readonly version: typeof DELETION_INVENTORY_SOURCE_RECEIPT_VERSION;
  readonly inventory_contract_version: typeof DELETION_INVENTORY_CONTRACT_VERSION;
  readonly scanner_contract_version: string;
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly surface: DeletionCleanupSurface;
  readonly source_frontier_digest: string;
  readonly source_authorization_digest: string;
  readonly scan_fence_state: "held" | "released";
  readonly scan_fence_receipt_digest: string;
  readonly remaining_count: number;
  readonly remaining_set_digest: string;
}

export interface VerifiedDeletionInventoryRow {
  readonly surface: DeletionCleanupSurface;
  readonly remaining_count: number;
}

export interface VerifiedDeletionCleanupInventory {
  readonly version: typeof DELETION_INVENTORY_CONTRACT_VERSION;
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly rows: readonly VerifiedDeletionInventoryRow[];
  readonly inventory_digest: string;
}

export type DeletionInventoryBlocker = "source_missing" | "source_fence_not_held";

export interface DeletionInventoryVerificationReport {
  readonly version: typeof DELETION_INVENTORY_CONTRACT_VERSION;
  readonly supplied_source_count: number;
  readonly required_source_count: number;
  readonly missing_surfaces: readonly DeletionCleanupSurface[];
  readonly unfenced_surfaces: readonly DeletionCleanupSurface[];
  readonly blockers: readonly DeletionInventoryBlocker[];
  readonly inventory_digest: string | null;
}

export interface DeletionInventoryVerificationResult {
  readonly report: DeletionInventoryVerificationReport;
  /** Internal capability; never serialize this owner-bearing value. */
  readonly verified_inventory: VerifiedDeletionCleanupInventory | null;
}

export interface DeletionInventoryVerificationInput {
  readonly terminal_coordinate: DeletionInventoryTerminalCoordinate;
  readonly source_receipts: readonly DeletionInventorySourceReceipt[];
}

export type DeletionInventoryInputErrorCode =
  | "invalid_input"
  | "invalid_terminal_coordinate"
  | "invalid_source_receipts"
  | "invalid_source_receipt"
  | "duplicate_source_receipt"
  | "source_coordinate_mismatch";

export class DeletionInventoryInputError extends TypeError {
  readonly code: DeletionInventoryInputErrorCode;

  constructor(code: DeletionInventoryInputErrorCode) {
    super(code);
    this.name = "DeletionInventoryInputError";
    this.code = code;
  }
}

const verifiedInventoryBrand = new WeakSet<object>();
const DIGEST = /^[0-9a-f]{64}$/;
const MAX_COORDINATE_LENGTH = 256;
const MAX_REMAINING_COUNT = 1_000_000_000;

const fail = (code: DeletionInventoryInputErrorCode): never => {
  throw new DeletionInventoryInputError(code);
};

type PlainRecord = Record<string, unknown>;

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: DeletionInventoryInputErrorCode,
): PlainRecord => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key !== "string") || ownKeys.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail(code);
  for (const descriptor of Object.values(descriptors)) {
    if (!("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as PlainRecord;
};

const exactArray = (value: unknown): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > DELETION_CLEANUP_SURFACES.length) fail("invalid_source_receipts");
  const array = value as unknown[];
  const descriptors = Object.getOwnPropertyDescriptors(array);
  const ownKeys = Reflect.ownKeys(descriptors);
  if (ownKeys.some((key) => typeof key !== "string") || ownKeys.length !== array.length + 1
    || !Object.prototype.hasOwnProperty.call(descriptors, "length")) fail("invalid_source_receipts");
  for (let index = 0; index < array.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (descriptor === undefined || !("value" in descriptor) || !descriptor.enumerable) {
      fail("invalid_source_receipts");
    }
  }
  return array;
};

const safeInteger = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const boundedCoordinate = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && value.length <= MAX_COORDINATE_LENGTH
  && /^[\x21-\x7e]+$/.test(value);

const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);

const surface = (value: unknown): value is DeletionCleanupSurface =>
  typeof value === "string" && (DELETION_CLEANUP_SURFACES as readonly string[]).includes(value);

const sha256 = (value: unknown): string =>
  createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex");

const parseTerminal = (value: unknown): DeletionInventoryTerminalCoordinate => {
  const row = exactRecord(
    value,
    ["account_id", "control_revision", "deletion_epoch"],
    "invalid_terminal_coordinate",
  );
  if (!isWellFormedAccountId(row.account_id) || !safeInteger(row.control_revision)
    || !safeInteger(row.deletion_epoch)) fail("invalid_terminal_coordinate");
  return Object.freeze({
    account_id: row.account_id as string,
    control_revision: row.control_revision as number,
    deletion_epoch: row.deletion_epoch as number,
  });
};

const parseReceipt = (value: unknown): DeletionInventorySourceReceipt => {
  const row = exactRecord(value, [
    "version",
    "inventory_contract_version",
    "scanner_contract_version",
    "account_id",
    "control_revision",
    "deletion_epoch",
    "surface",
    "source_frontier_digest",
    "source_authorization_digest",
    "scan_fence_state",
    "scan_fence_receipt_digest",
    "remaining_count",
    "remaining_set_digest",
  ], "invalid_source_receipt");
  if (row.version !== DELETION_INVENTORY_SOURCE_RECEIPT_VERSION
    || row.inventory_contract_version !== DELETION_INVENTORY_CONTRACT_VERSION
    || !boundedCoordinate(row.scanner_contract_version) || !isWellFormedAccountId(row.account_id)
    || !safeInteger(row.control_revision) || !safeInteger(row.deletion_epoch)
    || !surface(row.surface) || !digest(row.source_frontier_digest)
    || !digest(row.source_authorization_digest)
    || (row.scan_fence_state !== "held" && row.scan_fence_state !== "released")
    || !digest(row.scan_fence_receipt_digest) || !safeInteger(row.remaining_count)
    || row.remaining_count > MAX_REMAINING_COUNT || !digest(row.remaining_set_digest)) {
    fail("invalid_source_receipt");
  }
  return value as DeletionInventorySourceReceipt;
};

export const isVerifiedDeletionCleanupInventory = (
  value: unknown,
): value is VerifiedDeletionCleanupInventory =>
  value !== null && typeof value === "object" && !isProxy(value) && verifiedInventoryBrand.has(value);

export const verifyDeletionCleanupInventory = (
  inputValue: unknown,
): DeletionInventoryVerificationResult => {
  const input = exactRecord(
    inputValue,
    ["terminal_coordinate", "source_receipts"],
    "invalid_input",
  );
  const terminal = parseTerminal(input.terminal_coordinate);
  const receiptValues = exactArray(input.source_receipts);
  const receiptBySurface = new Map<DeletionCleanupSurface, DeletionInventorySourceReceipt>();
  for (const value of receiptValues) {
    const receipt = parseReceipt(value);
    if (receiptBySurface.has(receipt.surface)) fail("duplicate_source_receipt");
    if (receipt.account_id !== terminal.account_id
      || receipt.control_revision !== terminal.control_revision
      || receipt.deletion_epoch !== terminal.deletion_epoch) fail("source_coordinate_mismatch");
    receiptBySurface.set(receipt.surface, receipt);
  }

  const missingSurfaces = DELETION_CLEANUP_SURFACES.filter((name) => !receiptBySurface.has(name));
  const unfencedSurfaces = DELETION_CLEANUP_SURFACES.filter((name) =>
    receiptBySurface.get(name)?.scan_fence_state === "released");
  const blockers: DeletionInventoryBlocker[] = [];
  if (missingSurfaces.length > 0) blockers.push("source_missing");
  if (unfencedSurfaces.length > 0) blockers.push("source_fence_not_held");

  let verified: VerifiedDeletionCleanupInventory | null = null;
  let inventoryDigest: string | null = null;
  if (blockers.length === 0) {
    const receiptBindings = DELETION_CLEANUP_SURFACES.map((name) => {
      const receipt = receiptBySurface.get(name)!;
      return {
        surface: receipt.surface,
        scanner_contract_version: receipt.scanner_contract_version,
        source_frontier_digest: receipt.source_frontier_digest,
        source_authorization_digest: receipt.source_authorization_digest,
        scan_fence_state: receipt.scan_fence_state,
        scan_fence_receipt_digest: receipt.scan_fence_receipt_digest,
        remaining_count: receipt.remaining_count,
        remaining_set_digest: receipt.remaining_set_digest,
      };
    });
    inventoryDigest = sha256({
      version: DELETION_INVENTORY_CONTRACT_VERSION,
      account_id: terminal.account_id,
      control_revision: terminal.control_revision,
      deletion_epoch: terminal.deletion_epoch,
      source_receipts: receiptBindings,
    });
    const rows = Object.freeze(receiptBindings.map((receipt) => Object.freeze({
      surface: receipt.surface,
      remaining_count: receipt.remaining_count,
    })));
    verified = Object.freeze({
      version: DELETION_INVENTORY_CONTRACT_VERSION,
      account_id: terminal.account_id,
      control_revision: terminal.control_revision,
      deletion_epoch: terminal.deletion_epoch,
      rows,
      inventory_digest: inventoryDigest,
    });
    verifiedInventoryBrand.add(verified);
  }

  const report = Object.freeze({
    version: DELETION_INVENTORY_CONTRACT_VERSION,
    supplied_source_count: receiptBySurface.size,
    required_source_count: DELETION_CLEANUP_SURFACES.length,
    missing_surfaces: Object.freeze([...missingSurfaces]),
    unfenced_surfaces: Object.freeze([...unfencedSurfaces]),
    blockers: Object.freeze(blockers),
    inventory_digest: inventoryDigest,
  });
  return Object.freeze({ report, verified_inventory: verified });
};
