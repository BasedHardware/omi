import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../../core/control/account-control";
import {
  DELETION_INVENTORY_CONTRACT_VERSION,
  DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
  type DeletionCleanupSurface,
  type DeletionInventorySourceReceipt,
} from "../../../core/control/deletion-cleanup-inventory";
import type { DeletionCleanupDispositionReceipt } from "./account-deletion-cleanup";
import type {
  DeletionCleanupCoordinate,
  DeletionSurfaceParticipant,
  HeldDeletionSurfaceSession,
} from "./account-deletion-cleanup-composite";

export const FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT = 100_000 as const;

/**
 * The complete legacy account-owned Firestore document tree. The concrete
 * scanner discovers every current and future descendant collection while the
 * legacy writer fence is held; a hand-maintained collection allowlist could
 * silently manufacture a false zero when the legacy product adds a surface.
 */
export const FIRESTORE_LEGACY_GENERATION_COLLECTIONS = Object.freeze([
  ["legacy_user_tree", "users"],
] as const);

export type FirestoreLegacyGenerationRole = typeof FIRESTORE_LEGACY_GENERATION_COLLECTIONS[number][0];

export interface FirestoreLegacyGenerationRegistryConfiguration {
  readonly project_id: string;
  readonly database_id: string;
  readonly policy_digest: string;
}

export interface FirestoreLegacyGenerationCollectionRegistry {
  readonly version: "firestore-legacy-generation-collection-registry-v1";
  readonly project_id: string;
  readonly database_id: string;
  readonly policy_digest: string;
  readonly registry_digest: string;
  readonly collections: readonly Readonly<{
    readonly role: FirestoreLegacyGenerationRole;
    readonly collection_id: string;
  }>[];
}

export interface FirestoreLegacyGenerationScanRequest {
  readonly version: "firestore-legacy-generation-scan-request-v1";
  readonly project_id: string;
  readonly database_id: string;
  readonly role: FirestoreLegacyGenerationRole;
  readonly collection_id: string;
  readonly legacy_owner_key: string;
  readonly owner_mapping_digest: string;
  readonly maximum_documents: typeof FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT;
}

export interface FirestoreLegacyGenerationDocument {
  readonly document_path: string;
  readonly update_time: string;
}

export interface FirestoreLegacyGenerationScanResult {
  readonly version: "firestore-legacy-generation-scan-result-v1";
  readonly project_id: string;
  readonly database_id: string;
  readonly role: FirestoreLegacyGenerationRole;
  readonly collection_id: string;
  readonly legacy_owner_key: string;
  readonly owner_mapping_digest: string;
  /** True only after recursively traversing every descendant collection. */
  readonly descendant_complete: true;
  readonly provider_frontier_digest: string;
  readonly documents: readonly FirestoreLegacyGenerationDocument[];
}

export interface FirestoreLegacyGenerationDeleteRequest {
  readonly version: "firestore-legacy-generation-delete-request-v1";
  readonly project_id: string;
  readonly database_id: string;
  readonly role: FirestoreLegacyGenerationRole;
  readonly collection_id: string;
  readonly legacy_owner_key: string;
  readonly owner_mapping_digest: string;
  readonly document_path: string;
  readonly update_time: string;
}

export interface FirestoreLegacyGenerationDeleteResult {
  readonly version: "firestore-legacy-generation-delete-result-v1";
  readonly document_path: string;
  readonly update_time: string;
  readonly result: "deleted" | "already_absent";
  readonly provider_receipt_digest: string;
}

/**
 * Production implementation belongs beside the legacy Firestore writer. It
 * must hold that writer fence, recursively enumerate descendants, return only
 * document coordinates, and drain every callback operation before release.
 */
export interface HeldFirestoreLegacyGenerationFence {
  readonly source_generation_digest: string;
  readonly fence_receipt_digest: string;
  readonly owner_mapping_digest: string;
  readonly legacy_owner_keys: readonly string[];
  scanCollectionTree(
    request: FirestoreLegacyGenerationScanRequest,
  ): Promise<FirestoreLegacyGenerationScanResult>;
  deleteDocument(
    request: FirestoreLegacyGenerationDeleteRequest,
  ): Promise<FirestoreLegacyGenerationDeleteResult>;
}

export interface FirestoreLegacyGenerationFence {
  withHeldAccountWriteFence<T>(
    coordinate: DeletionCleanupCoordinate,
    operationRef: string,
    eligibilityDigest: string,
    callback: (session: HeldFirestoreLegacyGenerationFence) => Promise<T>,
  ): Promise<T>;
}

export interface FirestoreLegacyGenerationReceiptKey {
  readonly version: "firestore-legacy-generation-receipt-key-v1";
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly operation_ref: string;
  readonly eligibility_digest: string;
  readonly registry_digest: string;
  readonly policy_digest: string;
  readonly owner_mapping_digest: string;
  readonly project_id: string;
  readonly database_id: string;
  readonly role: FirestoreLegacyGenerationRole;
  readonly collection_id: string;
}

export interface FirestoreStoredLegacyGenerationReceipt extends FirestoreLegacyGenerationReceiptKey {
  readonly result: "disposed" | "already_absent";
  readonly pre_delete_count: number;
  readonly pre_delete_set_digest: string;
  readonly provider_receipt_digest: string;
  readonly receipt_digest: string;
}

export type FirestoreLegacyGenerationReceiptLoad =
  | Readonly<{ readonly kind: "missing" }>
  | Readonly<{ readonly kind: "found"; readonly receipt: FirestoreStoredLegacyGenerationReceipt }>;

export interface FirestoreLegacyGenerationReceiptRepository {
  load(key: FirestoreLegacyGenerationReceiptKey): Promise<FirestoreLegacyGenerationReceiptLoad>;
  record(
    receipt: FirestoreStoredLegacyGenerationReceipt,
  ): Promise<FirestoreStoredLegacyGenerationReceipt>;
}

export type FirestoreLegacyGenerationCleanupErrorCode =
  | "invalid_configuration"
  | "invalid_input"
  | "provider_fence_failed"
  | "callback_failed"
  | "scan_failed"
  | "disposal_failed"
  | "receipt_failed";

export class FirestoreLegacyGenerationCleanupError extends Error {
  constructor(readonly code: FirestoreLegacyGenerationCleanupErrorCode) {
    super(code);
    this.name = "FirestoreLegacyGenerationCleanupError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;
const PROJECT_ID = /^[a-z][a-z0-9-]{4,28}[a-z0-9]$/;
const DATABASE_ID = /^(?:\(default\)|[a-z][a-z0-9_-]{0,62})$/;
const OWNER_KEY = /^[\x20-\x2e\x30-\x7e]+$/;
const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$/;
const MAX_DOCUMENT_PATH_BYTES = 6_144;
const registryBrand = new WeakSet<object>();
type Plain = Record<string, unknown>;

const fail = (code: FirestoreLegacyGenerationCleanupErrorCode): never => {
  throw new FirestoreLegacyGenerationCleanupError(code);
};
const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");
const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);
const safeInt = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: FirestoreLegacyGenerationCleanupErrorCode,
): Plain => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail(code);
  const result: Plain = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    result[key] = descriptor.value;
  }
  return result;
};

const exactArray = (
  value: unknown,
  maximum: number,
  code: FirestoreLegacyGenerationCleanupErrorCode,
): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(descriptors).length !== value.length + 1) fail(code);
  const result: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    result.push(descriptor.value);
  }
  return result;
};

const role = (value: unknown): value is FirestoreLegacyGenerationRole =>
  typeof value === "string"
  && FIRESTORE_LEGACY_GENERATION_COLLECTIONS.some(([candidate]) => candidate === value);

const ownerMapping = (
  value: unknown,
  accountId: string,
): Readonly<{ readonly digest: string; readonly keys: readonly string[] }> => {
  const keys = exactArray(value, 32, "provider_fence_failed");
  if (keys.length === 0 || keys.some((key) => typeof key !== "string"
    || !OWNER_KEY.test(key) || Buffer.byteLength(key, "utf8") > 128)
    || keys.some((key, index) => index > 0
      && (key as string).localeCompare(keys[index - 1] as string) <= 0)) {
    fail("provider_fence_failed");
  }
  const normalized = Object.freeze(keys as string[]);
  return Object.freeze({
    digest: sha256({
      version: "firestore-legacy-owner-mapping-v1",
      account_id: accountId,
      legacy_owner_keys: normalized,
    }),
    keys: normalized,
  });
};

export const createFirestoreLegacyGenerationCollectionRegistry = (
  value: FirestoreLegacyGenerationRegistryConfiguration,
): FirestoreLegacyGenerationCollectionRegistry => {
  const row = exactRecord(
    value, ["project_id", "database_id", "policy_digest"], "invalid_configuration",
  );
  if (typeof row.project_id !== "string" || !PROJECT_ID.test(row.project_id)
    || typeof row.database_id !== "string" || !DATABASE_ID.test(row.database_id)
    || !digest(row.policy_digest)) fail("invalid_configuration");
  const collections = Object.freeze(FIRESTORE_LEGACY_GENERATION_COLLECTIONS.map(
    ([collectionRole, collectionId]) => Object.freeze({
      role: collectionRole,
      collection_id: collectionId,
    }),
  ));
  const core = Object.freeze({
    version: "firestore-legacy-generation-collection-registry-v1" as const,
    project_id: row.project_id as string,
    database_id: row.database_id as string,
    policy_digest: row.policy_digest as string,
    collections,
  });
  const registry = Object.freeze({
    ...core,
    registry_digest: sha256(core),
  });
  registryBrand.add(registry);
  return registry;
};

export const assertFirestoreLegacyGenerationCollectionRegistry = (
  value: unknown,
): FirestoreLegacyGenerationCollectionRegistry => {
  if (value === null || typeof value !== "object" || !registryBrand.has(value)) {
    fail("invalid_configuration");
  }
  return value as FirestoreLegacyGenerationCollectionRegistry;
};

const parseCoordinate = (value: DeletionCleanupCoordinate): DeletionCleanupCoordinate => {
  const row = exactRecord(
    value, ["account_id", "control_revision", "deletion_epoch"], "invalid_input",
  );
  if (!isWellFormedAccountId(row.account_id) || !safeInt(row.control_revision)
    || !safeInt(row.deletion_epoch)) fail("invalid_input");
  return Object.freeze({
    account_id: row.account_id,
    control_revision: row.control_revision,
    deletion_epoch: row.deletion_epoch,
  }) as DeletionCleanupCoordinate;
};

const capture = <T extends (...args: never[]) => unknown>(
  value: unknown,
  keys: readonly string[],
  name: string,
): T => {
  const row = exactRecord(value, keys, "invalid_configuration");
  if (typeof row[name] !== "function") fail("invalid_configuration");
  return (row[name] as (...args: never[]) => unknown).bind(value) as unknown as T;
};

const receiptDigest = (
  receipt: Omit<FirestoreStoredLegacyGenerationReceipt, "receipt_digest">,
): string => sha256({ contract_version: "firestore-legacy-generation-stored-receipt-v1", receipt });

const validateReceipt = (
  value: unknown,
  key: FirestoreLegacyGenerationReceiptKey,
): FirestoreStoredLegacyGenerationReceipt => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "policy_digest", "owner_mapping_digest",
    "project_id", "database_id", "role", "collection_id", "result", "pre_delete_count",
    "pre_delete_set_digest", "provider_receipt_digest", "receipt_digest",
  ], "receipt_failed");
  for (const field of [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "policy_digest", "owner_mapping_digest",
    "project_id", "database_id", "role", "collection_id",
  ] as const) if (row[field] !== key[field]) fail("receipt_failed");
  if ((row.result !== "disposed" && row.result !== "already_absent")
    || !safeInt(row.pre_delete_count, FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT)
    || (row.result === "disposed" && row.pre_delete_count === 0)
    || (row.result === "already_absent" && row.pre_delete_count !== 0)
    || !digest(row.pre_delete_set_digest) || !digest(row.provider_receipt_digest)
    || !digest(row.receipt_digest)) fail("receipt_failed");
  const copy = Object.freeze({ ...row }) as unknown as FirestoreStoredLegacyGenerationReceipt;
  const { receipt_digest: ignored, ...core } = copy;
  void ignored;
  if (receiptDigest(core) !== copy.receipt_digest) fail("receipt_failed");
  return copy;
};

const validateLoad = (
  value: unknown,
  key: FirestoreLegacyGenerationReceiptKey,
): FirestoreStoredLegacyGenerationReceipt | null => {
  if (value === null || typeof value !== "object" || isProxy(value)) fail("receipt_failed");
  const descriptor = Object.getOwnPropertyDescriptor(value, "kind");
  if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("receipt_failed");
  const row = exactRecord(
    value, descriptor.value === "found" ? ["kind", "receipt"] : ["kind"], "receipt_failed",
  );
  if (row.kind === "missing") return null;
  if (row.kind !== "found") fail("receipt_failed");
  return validateReceipt(row.receipt, key);
};

const parseDocument = (
  value: unknown,
  request: FirestoreLegacyGenerationScanRequest,
): FirestoreLegacyGenerationDocument => {
  const row = exactRecord(value, ["document_path", "update_time"], "scan_failed");
  const root = `users/${request.legacy_owner_key}`;
  if (typeof row.document_path !== "string"
    || (row.document_path !== root && !row.document_path.startsWith(`${root}/`))
    || row.document_path.includes("//") || row.document_path.split("/").some((part) => part.length === 0)
    || Buffer.byteLength(row.document_path, "utf8") > MAX_DOCUMENT_PATH_BYTES
    || typeof row.update_time !== "string" || !RFC3339.test(row.update_time)) fail("scan_failed");
  if (row.document_path !== root) {
    const tailSegments = row.document_path.slice(root.length + 1).split("/");
    if (tailSegments.length % 2 !== 0) fail("scan_failed");
  }
  return Object.freeze({
    document_path: row.document_path,
    update_time: row.update_time,
  }) as FirestoreLegacyGenerationDocument;
};

interface CollectionObservation {
  readonly role: FirestoreLegacyGenerationRole;
  readonly collection_id: string;
  readonly count: number;
  readonly set_digest: string;
  readonly frontier_digests: readonly string[];
  readonly documents: readonly Readonly<FirestoreLegacyGenerationDocument & {
    readonly legacy_owner_key: string;
  }>[];
}

const scanCollection = async (
  registry: FirestoreLegacyGenerationCollectionRegistry,
  entry: FirestoreLegacyGenerationCollectionRegistry["collections"][number],
  owners: Readonly<{ readonly digest: string; readonly keys: readonly string[] }>,
  scan: HeldFirestoreLegacyGenerationFence["scanCollectionTree"],
  assertOpen: () => void,
): Promise<CollectionObservation> => {
  const documents: Array<FirestoreLegacyGenerationDocument & { legacy_owner_key: string }> = [];
  const frontiers: string[] = [];
  const seen = new Set<string>();
  for (const ownerKey of owners.keys) {
    const request = Object.freeze({
      version: "firestore-legacy-generation-scan-request-v1" as const,
      project_id: registry.project_id,
      database_id: registry.database_id,
      role: entry.role,
      collection_id: entry.collection_id,
      legacy_owner_key: ownerKey,
      owner_mapping_digest: owners.digest,
      maximum_documents: FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT,
    });
    const value = await scan(request);
    assertOpen();
    const row = exactRecord(value, [
      "version", "project_id", "database_id", "role", "collection_id",
      "legacy_owner_key", "owner_mapping_digest", "descendant_complete",
      "provider_frontier_digest", "documents",
    ], "scan_failed");
    if (row.version !== "firestore-legacy-generation-scan-result-v1"
      || row.project_id !== registry.project_id || row.database_id !== registry.database_id
      || row.role !== entry.role || row.collection_id !== entry.collection_id
      || row.legacy_owner_key !== ownerKey || row.owner_mapping_digest !== owners.digest
      || row.descendant_complete !== true || !digest(row.provider_frontier_digest)) {
      fail("scan_failed");
    }
    frontiers.push(row.provider_frontier_digest as string);
    const values = exactArray(
      row.documents, FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT, "scan_failed",
    );
    for (const itemValue of values) {
      const item = parseDocument(itemValue, request);
      if (seen.has(item.document_path)) fail("scan_failed");
      seen.add(item.document_path);
      documents.push(Object.freeze({ ...item, legacy_owner_key: ownerKey }));
      if (documents.length > FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT) {
        fail("scan_failed");
      }
    }
  }
  const sorted = Object.freeze([...documents].sort((left, right) =>
    left.document_path.localeCompare(right.document_path)));
  return Object.freeze({
    role: entry.role,
    collection_id: entry.collection_id,
    count: sorted.length,
    set_digest: sha256({
      version: "firestore-legacy-generation-document-set-v1",
      registry_digest: registry.registry_digest,
      role: entry.role,
      collection_id: entry.collection_id,
      owner_mapping_digest: owners.digest,
      documents: sorted.map(({ document_path, update_time }) => ({ document_path, update_time })),
    }),
    frontier_digests: Object.freeze(frontiers),
    documents: sorted,
  });
};

export const createFirestoreLegacyGenerationCleanupParticipant = (
  registryValue: FirestoreLegacyGenerationCollectionRegistry,
  providerFenceValue: FirestoreLegacyGenerationFence,
  receiptRepositoryValue: FirestoreLegacyGenerationReceiptRepository,
): DeletionSurfaceParticipant => {
  const registry = assertFirestoreLegacyGenerationCollectionRegistry(registryValue);
  const withFence = capture<FirestoreLegacyGenerationFence["withHeldAccountWriteFence"]>(
    providerFenceValue, ["withHeldAccountWriteFence"], "withHeldAccountWriteFence",
  );
  const load = capture<FirestoreLegacyGenerationReceiptRepository["load"]>(
    receiptRepositoryValue, ["load", "record"], "load",
  );
  const record = capture<FirestoreLegacyGenerationReceiptRepository["record"]>(
    receiptRepositoryValue, ["load", "record"], "record",
  );
  return Object.freeze({
    participant_id: "firestore_legacy_generation_data",
    owned_surfaces: Object.freeze(["legacy_generation_data"] as const),
    async withHeldSurfaceFence<T>(
      coordinateValue: DeletionCleanupCoordinate,
      operationRef: string,
      eligibilityDigest: string,
      callback: (session: HeldDeletionSurfaceSession) => Promise<T>,
    ): Promise<T> {
      const coordinate = parseCoordinate(coordinateValue);
      if (!OPERATION_REF.test(operationRef) || !DIGEST.test(eligibilityDigest)
        || typeof callback !== "function" || isProxy(callback)) fail("invalid_input");
      let open = true;
      let callbackCount = 0;
      let callbackFailed = false;
      let callbackError: unknown;
      let resultValue: T | undefined;
      let outerResult: unknown;
      const resultToken = {};
      try {
        outerResult = await withFence(
          coordinate,
          operationRef,
          eligibilityDigest,
          async (providerValue) => {
            callbackCount += 1;
            if (!open || callbackCount !== 1) fail("provider_fence_failed");
            const provider = exactRecord(providerValue, [
              "source_generation_digest", "fence_receipt_digest", "owner_mapping_digest",
              "legacy_owner_keys", "scanCollectionTree", "deleteDocument",
            ], "provider_fence_failed");
            if (!digest(provider.source_generation_digest)
              || !digest(provider.fence_receipt_digest)
              || !digest(provider.owner_mapping_digest)
              || typeof provider.scanCollectionTree !== "function"
              || typeof provider.deleteDocument !== "function") fail("provider_fence_failed");
            const owners = ownerMapping(provider.legacy_owner_keys, coordinate.account_id);
            if (owners.digest !== provider.owner_mapping_digest) fail("provider_fence_failed");
            const scan = (provider.scanCollectionTree as Function).bind(providerValue) as
              HeldFirestoreLegacyGenerationFence["scanCollectionTree"];
            const dispose = (provider.deleteDocument as Function).bind(providerValue) as
              HeldFirestoreLegacyGenerationFence["deleteDocument"];
            const pending = new Set<Promise<unknown>>();
            let pendingFailed = false;
            let pendingError: unknown;
            let sessionOpen = true;
            const assertOpen = (): void => {
              if (!open || !sessionOpen) fail("provider_fence_failed");
            };
            const track = <R>(
              operation: () => Promise<R>,
              code: "scan_failed" | "disposal_failed",
            ): Promise<R> => {
              assertOpen();
              const promise = operation().catch((error) => {
                if (error instanceof FirestoreLegacyGenerationCleanupError) throw error;
                fail(code);
              });
              pending.add(promise);
              void promise.catch((error) => {
                if (!pendingFailed) pendingError = error;
                pendingFailed = true;
              }).finally(() => pending.delete(promise));
              return promise;
            };
            const heldSession: HeldDeletionSurfaceSession = Object.freeze({
              scanOwned: () => track(async () => {
                const observations: CollectionObservation[] = [];
                for (const entry of registry.collections) {
                  observations.push(await scanCollection(registry, entry, owners, scan, assertOpen));
                  assertOpen();
                }
                const remaining = observations.reduce((sum, item) => sum + item.count, 0);
                const remainingDigest = sha256({
                  version: "firestore-legacy-generation-set-v1",
                  registry_digest: registry.registry_digest,
                  owner_mapping_digest: owners.digest,
                  collections: observations.map((item) => ({
                    role: item.role,
                    collection_id: item.collection_id,
                    count: item.count,
                    set_digest: item.set_digest,
                  })),
                });
                return Object.freeze([Object.freeze({
                  version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
                  inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION,
                  scanner_contract_version: "legacy-firestore-recursive-user-tree-v1",
                  ...coordinate,
                  surface: "legacy_generation_data" as const,
                  source_frontier_digest: sha256({
                    version: "firestore-legacy-generation-frontier-v1",
                    source_generation_digest: provider.source_generation_digest,
                    registry_digest: registry.registry_digest,
                    frontier_digests: observations.flatMap((item) => item.frontier_digests),
                  }),
                  source_authorization_digest: eligibilityDigest,
                  scan_fence_state: "held" as const,
                  scan_fence_receipt_digest: provider.fence_receipt_digest,
                  remaining_count: remaining,
                  remaining_set_digest: remainingDigest,
                })]);
              }, "scan_failed"),
              disposeOwned: (surfaces: readonly DeletionCleanupSurface[]) => track(async () => {
                const requested = exactArray(surfaces, 1, "disposal_failed");
                if (requested.length !== 1 || requested[0] !== "legacy_generation_data") {
                  fail("disposal_failed");
                }
                const observations: Array<Readonly<{
                  readonly role: FirestoreLegacyGenerationRole;
                  readonly collection_id: string;
                  readonly count: number;
                  readonly stored_result: "disposed" | "already_absent";
                  readonly receipt_digest: string;
                }>> = [];
                for (const entry of registry.collections) {
                  const key: FirestoreLegacyGenerationReceiptKey = Object.freeze({
                    version: "firestore-legacy-generation-receipt-key-v1",
                    ...coordinate,
                    operation_ref: operationRef,
                    eligibility_digest: eligibilityDigest,
                    registry_digest: registry.registry_digest,
                    policy_digest: registry.policy_digest,
                    owner_mapping_digest: owners.digest,
                    project_id: registry.project_id,
                    database_id: registry.database_id,
                    role: entry.role,
                    collection_id: entry.collection_id,
                  });
                  const stored = validateLoad(await load(key), key);
                  assertOpen();
                  const before = await scanCollection(registry, entry, owners, scan, assertOpen);
                  assertOpen();
                  const providerDigests: string[] = [];
                  // Firestore does not cascade. Deepest documents must be removed
                  // before parents so no descendant becomes unreachable.
                  for (const item of [...before.documents].sort((left, right) =>
                    right.document_path.split("/").length - left.document_path.split("/").length
                    || left.document_path.localeCompare(right.document_path))) {
                    const request: FirestoreLegacyGenerationDeleteRequest = Object.freeze({
                      version: "firestore-legacy-generation-delete-request-v1",
                      project_id: registry.project_id,
                      database_id: registry.database_id,
                      role: entry.role,
                      collection_id: entry.collection_id,
                      legacy_owner_key: item.legacy_owner_key,
                      owner_mapping_digest: owners.digest,
                      document_path: item.document_path,
                      update_time: item.update_time,
                    });
                    const outcome = await dispose(request);
                    assertOpen();
                    if (outcome.version !== "firestore-legacy-generation-delete-result-v1"
                      || outcome.document_path !== item.document_path
                      || outcome.update_time !== item.update_time
                      || (outcome.result !== "deleted" && outcome.result !== "already_absent")
                      || !digest(outcome.provider_receipt_digest)) fail("disposal_failed");
                    providerDigests.push(outcome.provider_receipt_digest);
                  }
                  let durable = stored;
                  if (durable === null) {
                    const core = Object.freeze({
                      ...key,
                      result: before.count > 0 ? "disposed" as const : "already_absent" as const,
                      pre_delete_count: before.count,
                      pre_delete_set_digest: before.set_digest,
                      provider_receipt_digest: sha256({
                        version: "firestore-legacy-generation-provider-delete-set-v1",
                        role: entry.role,
                        collection_id: entry.collection_id,
                        provider_receipt_digests: providerDigests,
                      }),
                    });
                    const candidate = Object.freeze({
                      ...core,
                      receipt_digest: receiptDigest(core),
                    });
                    durable = validateReceipt(await record(candidate), key);
                    assertOpen();
                  }
                  observations.push(Object.freeze({
                    role: entry.role,
                    collection_id: entry.collection_id,
                    count: before.count,
                    stored_result: durable.result,
                    receipt_digest: durable.receipt_digest,
                  }));
                }
                const result = observations.some((item) =>
                  item.count > 0 || item.stored_result === "disposed")
                  ? "disposed" as const : "already_absent" as const;
                return Object.freeze([Object.freeze({
                  version: "deletion-cleanup-disposition-v1" as const,
                  surface: "legacy_generation_data" as const,
                  result,
                  receipt_digest: sha256({
                    version: "firestore-legacy-generation-disposition-v1",
                    coordinate,
                    operation_ref: operationRef,
                    eligibility_digest: eligibilityDigest,
                    registry_digest: registry.registry_digest,
                    observations,
                  }),
                })]);
              }, "disposal_failed"),
            });
            try {
              resultValue = await callback(heldSession);
            } catch (error) {
              callbackFailed = true;
              callbackError = error;
            } finally {
              sessionOpen = false;
              while (pending.size > 0) await Promise.allSettled([...pending]);
            }
            if (callbackFailed) throw callbackError;
            if (pendingFailed) throw pendingError;
            return resultToken;
          },
        );
      } catch (error) {
        if (callbackFailed) {
          if (callbackError instanceof FirestoreLegacyGenerationCleanupError) throw callbackError;
          fail("callback_failed");
        }
        if (error instanceof FirestoreLegacyGenerationCleanupError) throw error;
        fail("provider_fence_failed");
      } finally {
        open = false;
      }
      if (callbackCount !== 1 || outerResult !== resultToken) fail("provider_fence_failed");
      return resultValue as T;
    },
  });
};
