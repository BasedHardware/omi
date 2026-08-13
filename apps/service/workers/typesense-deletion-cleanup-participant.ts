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

export const TYPESENSE_DELETION_SCANNER_VERSION =
  "typesense-account-search-documents-v1" as const;
export const TYPESENSE_DELETION_PAGE_SIZE = 250 as const;
export const TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION = 100_000 as const;

export const TYPESENSE_DELETION_COLLECTION_ROLES = Object.freeze([
  "legacy_conversations",
  "canonical_memory_atoms",
] as const);

export type TypesenseDeletionCollectionRole =
  typeof TYPESENSE_DELETION_COLLECTION_ROLES[number];

export interface TypesenseDeletionCollectionConfiguration {
  readonly legacy_conversations_collection: string;
  readonly canonical_memory_atoms_collection: string;
}

export interface TypesenseDeletionCollectionRegistry {
  readonly version: "typesense-deletion-collection-registry-v1";
  readonly registry_digest: string;
  readonly collections: readonly Readonly<{
    readonly role: TypesenseDeletionCollectionRole;
    readonly collection_name: string;
  }>[];
}

export interface TypesenseAccountDocumentScanRequest {
  readonly version: "typesense-account-document-scan-request-v1";
  readonly role: TypesenseDeletionCollectionRole;
  readonly collection_name: string;
  readonly account_id: string;
  readonly page: number;
  readonly per_page: typeof TYPESENSE_DELETION_PAGE_SIZE;
}

export interface TypesenseAccountDocumentScanPage {
  readonly version: "typesense-account-document-scan-page-v1";
  readonly role: TypesenseDeletionCollectionRole;
  readonly collection_name: string;
  readonly account_id: string;
  readonly page: number;
  readonly found: number;
  readonly document_ids: readonly string[];
}

export interface TypesenseAccountDocumentDeleteRequest {
  readonly version: "typesense-account-document-delete-request-v1";
  readonly role: TypesenseDeletionCollectionRole;
  readonly collection_name: string;
  readonly account_id: string;
}

export interface TypesenseAccountDocumentDeleteResult {
  readonly version: "typesense-account-document-delete-result-v1";
  readonly role: TypesenseDeletionCollectionRole;
  readonly collection_name: string;
  readonly account_id: string;
  readonly num_deleted: number;
  readonly provider_receipt_digest: string;
}

/**
 * The concrete adapter owns provider authentication, exact `userId` filter
 * escaping, and suppression of legacy writers while this session is held.
 * It must await and drain every callback operation before releasing the fence.
 */
export interface HeldTypesenseAccountDeletionFence {
  readonly source_generation_digest: string;
  readonly fence_receipt_digest: string;
  scanAccountDocuments(
    request: TypesenseAccountDocumentScanRequest,
  ): Promise<TypesenseAccountDocumentScanPage>;
  deleteAccountDocuments(
    request: TypesenseAccountDocumentDeleteRequest,
  ): Promise<TypesenseAccountDocumentDeleteResult>;
}

export interface TypesenseAccountDeletionFence {
  withHeldAccountWriteFence<T>(
    coordinate: DeletionCleanupCoordinate,
    operationRef: string,
    eligibilityDigest: string,
    callback: (session: HeldTypesenseAccountDeletionFence) => Promise<T>,
  ): Promise<T>;
}

export interface TypesenseDeletionReceiptKey {
  readonly version: "typesense-deletion-receipt-key-v1";
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly operation_ref: string;
  readonly eligibility_digest: string;
  readonly registry_digest: string;
  readonly role: TypesenseDeletionCollectionRole;
  readonly collection_name: string;
}

export interface TypesenseStoredDeletionReceipt extends TypesenseDeletionReceiptKey {
  readonly result: "disposed" | "already_absent";
  readonly affected_count: number;
  readonly provider_receipt_digest: string;
  readonly receipt_digest: string;
}

export type TypesenseDeletionReceiptLoad =
  | Readonly<{ readonly kind: "missing" }>
  | Readonly<{
    readonly kind: "found";
    readonly receipt: TypesenseStoredDeletionReceipt;
  }>;

export interface TypesenseDeletionReceiptRepository {
  load(key: TypesenseDeletionReceiptKey): Promise<TypesenseDeletionReceiptLoad>;
  record(receipt: TypesenseStoredDeletionReceipt): Promise<TypesenseStoredDeletionReceipt>;
}

export type TypesenseDeletionCleanupErrorCode =
  | "invalid_configuration"
  | "invalid_input"
  | "provider_fence_failed"
  | "callback_failed"
  | "scan_failed"
  | "disposal_failed"
  | "receipt_failed";

export class TypesenseDeletionCleanupError extends Error {
  constructor(readonly code: TypesenseDeletionCleanupErrorCode) {
    super(code);
    this.name = "TypesenseDeletionCleanupError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;
const COLLECTION_NAME = /^[A-Za-z0-9_-]{1,128}$/;
const MAX_DOCUMENT_ID_BYTES = 512;
const registryBrand = new WeakSet<object>();

type PlainRecord = Record<string, unknown>;

const fail = (code: TypesenseDeletionCleanupErrorCode): never => {
  throw new TypesenseDeletionCleanupError(code);
};

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: TypesenseDeletionCleanupErrorCode,
): PlainRecord => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail(code);
  const result: PlainRecord = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    result[key] = descriptor.value;
  }
  return result;
};

const exactArray = (
  value: unknown,
  maximumLength: number,
  code: TypesenseDeletionCleanupErrorCode,
): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximumLength) fail(code);
  const array = value as unknown[];
  const descriptors = Object.getOwnPropertyDescriptors(array);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== array.length + 1
    || !Object.prototype.hasOwnProperty.call(descriptors, "length")) fail(code);
  const result: unknown[] = [];
  for (let index = 0; index < array.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    result.push(descriptor.value);
  }
  return result;
};

const safeInteger = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;

const digest = (value: unknown): value is string =>
  typeof value === "string" && DIGEST.test(value);

const role = (value: unknown): value is TypesenseDeletionCollectionRole =>
  typeof value === "string"
  && (TYPESENSE_DELETION_COLLECTION_ROLES as readonly string[]).includes(value);

const collectionName = (value: unknown): value is string =>
  typeof value === "string" && COLLECTION_NAME.test(value);

export const createTypesenseDeletionCollectionRegistry = (
  value: TypesenseDeletionCollectionConfiguration,
): TypesenseDeletionCollectionRegistry => {
  const row = exactRecord(value, [
    "legacy_conversations_collection", "canonical_memory_atoms_collection",
  ], "invalid_configuration");
  if (row.legacy_conversations_collection !== "conversations"
    || !collectionName(row.legacy_conversations_collection)
    || !collectionName(row.canonical_memory_atoms_collection)
    || row.legacy_conversations_collection === row.canonical_memory_atoms_collection) {
    fail("invalid_configuration");
  }
  const legacyCollection = row.legacy_conversations_collection as string;
  const canonicalCollection = row.canonical_memory_atoms_collection as string;
  const collections = Object.freeze([
    Object.freeze({
      role: "legacy_conversations" as const,
      collection_name: legacyCollection,
    }),
    Object.freeze({
      role: "canonical_memory_atoms" as const,
      collection_name: canonicalCollection,
    }),
  ]);
  const registry = Object.freeze({
    version: "typesense-deletion-collection-registry-v1" as const,
    registry_digest: sha256({ version: "typesense-deletion-collection-registry-v1", collections }),
    collections,
  });
  registryBrand.add(registry);
  return registry;
};

export const assertTypesenseDeletionCollectionRegistry = (
  value: unknown,
): TypesenseDeletionCollectionRegistry => {
  if (value === null || typeof value !== "object" || !registryBrand.has(value)) {
    fail("invalid_configuration");
  }
  return value as TypesenseDeletionCollectionRegistry;
};

const validateCoordinate = (value: DeletionCleanupCoordinate): DeletionCleanupCoordinate => {
  const row = exactRecord(
    value, ["account_id", "control_revision", "deletion_epoch"], "invalid_input",
  );
  if (!isWellFormedAccountId(row.account_id) || !safeInteger(row.control_revision)
    || !safeInteger(row.deletion_epoch)) fail("invalid_input");
  return Object.freeze({
    account_id: row.account_id,
    control_revision: row.control_revision,
    deletion_epoch: row.deletion_epoch,
  }) as DeletionCleanupCoordinate;
};

const captureMethod = <T extends (...args: never[]) => unknown>(
  value: unknown,
  keys: readonly string[],
  method: string,
  code: TypesenseDeletionCleanupErrorCode,
): T => {
  const row = exactRecord(value, keys, code);
  if (typeof row[method] !== "function") fail(code);
  return (row[method] as (...args: never[]) => unknown).bind(value) as unknown as T;
};

const receiptDigest = (receipt: Omit<TypesenseStoredDeletionReceipt, "receipt_digest">): string =>
  sha256({ contract_version: "typesense-deletion-stored-receipt-v1", receipt });

const validateReceipt = (
  value: unknown,
  key: TypesenseDeletionReceiptKey,
): TypesenseStoredDeletionReceipt => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "role", "collection_name", "result",
    "affected_count", "provider_receipt_digest", "receipt_digest",
  ], "receipt_failed");
  if (row.version !== key.version || row.account_id !== key.account_id
    || row.control_revision !== key.control_revision || row.deletion_epoch !== key.deletion_epoch
    || row.operation_ref !== key.operation_ref || row.eligibility_digest !== key.eligibility_digest
    || row.registry_digest !== key.registry_digest || row.role !== key.role
    || row.collection_name !== key.collection_name
    || (row.result !== "disposed" && row.result !== "already_absent")
    || !safeInteger(row.affected_count, TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION)
    || (row.result === "disposed" && row.affected_count === 0)
    || (row.result === "already_absent" && row.affected_count !== 0)
    || !digest(row.provider_receipt_digest) || !digest(row.receipt_digest)) fail("receipt_failed");
  const copy = Object.freeze({ ...row }) as unknown as TypesenseStoredDeletionReceipt;
  const { receipt_digest: ignored, ...core } = copy;
  void ignored;
  if (receiptDigest(core) !== copy.receipt_digest) fail("receipt_failed");
  return copy;
};

const validateLoad = (
  value: unknown,
  key: TypesenseDeletionReceiptKey,
): TypesenseStoredDeletionReceipt | null => {
  if (value === null || typeof value !== "object" || isProxy(value)) fail("receipt_failed");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const kind = descriptors.kind;
  if (!kind || !("value" in kind) || !kind.enumerable) fail("receipt_failed");
  if (kind.value === "missing") {
    exactRecord(value, ["kind"], "receipt_failed");
    return null;
  }
  const row = exactRecord(value, ["kind", "receipt"], "receipt_failed");
  if (row.kind !== "found") fail("receipt_failed");
  return validateReceipt(row.receipt, key);
};

const parseScanPage = (
  value: unknown,
  request: TypesenseAccountDocumentScanRequest,
): Readonly<{ readonly found: number; readonly document_ids: readonly string[] }> => {
  const row = exactRecord(value, [
    "version", "role", "collection_name", "account_id", "page", "found", "document_ids",
  ], "scan_failed");
  if (row.version !== "typesense-account-document-scan-page-v1"
    || row.role !== request.role || row.collection_name !== request.collection_name
    || row.account_id !== request.account_id || row.page !== request.page
    || !safeInteger(row.found, TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION)) {
    fail("scan_failed");
  }
  const values = exactArray(row.document_ids, TYPESENSE_DELETION_PAGE_SIZE, "scan_failed");
  const ids: string[] = values.map((id): string => {
    if (typeof id !== "string" || id.length === 0
      || Buffer.byteLength(id, "utf8") > MAX_DOCUMENT_ID_BYTES) fail("scan_failed");
    return id as string;
  });
  if (new Set(ids).size !== ids.length) fail("scan_failed");
  const found = row.found as number;
  return Object.freeze({ found, document_ids: Object.freeze(ids) });
};

const parseDeleteResult = (
  value: unknown,
  request: TypesenseAccountDocumentDeleteRequest,
): TypesenseAccountDocumentDeleteResult => {
  const row = exactRecord(value, [
    "version", "role", "collection_name", "account_id", "num_deleted",
    "provider_receipt_digest",
  ], "disposal_failed");
  if (row.version !== "typesense-account-document-delete-result-v1"
    || row.role !== request.role || row.collection_name !== request.collection_name
    || row.account_id !== request.account_id
    || !safeInteger(row.num_deleted, TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION)
    || !digest(row.provider_receipt_digest)) fail("disposal_failed");
  return Object.freeze({ ...row }) as unknown as TypesenseAccountDocumentDeleteResult;
};

const scanCollection = async (
  collection: Readonly<{ role: TypesenseDeletionCollectionRole; collection_name: string }>,
  accountId: string,
  scan: HeldTypesenseAccountDeletionFence["scanAccountDocuments"],
  assertOpen: () => void,
): Promise<Readonly<{ role: TypesenseDeletionCollectionRole; count: number; set_digest: string }>> => {
  const ids = new Set<string>();
  let expectedFound: number | null = null;
  let page = 1;
  while (true) {
    const request: TypesenseAccountDocumentScanRequest = Object.freeze({
      version: "typesense-account-document-scan-request-v1",
      ...collection,
      account_id: accountId,
      page,
      per_page: TYPESENSE_DELETION_PAGE_SIZE,
    });
    const result = parseScanPage(await scan(request), request);
    assertOpen();
    if (expectedFound === null) expectedFound = result.found;
    if (result.found !== expectedFound) fail("scan_failed");
    for (const id of result.document_ids) {
      if (ids.has(id)) fail("scan_failed");
      ids.add(id);
    }
    if (ids.size > expectedFound) fail("scan_failed");
    if (ids.size === expectedFound) {
      if (result.document_ids.length === TYPESENSE_DELETION_PAGE_SIZE
        && expectedFound > 0) {
        const sentinelRequest = Object.freeze({ ...request, page: page + 1 });
        const sentinel = parseScanPage(await scan(sentinelRequest), sentinelRequest);
        assertOpen();
        if (sentinel.found !== expectedFound || sentinel.document_ids.length !== 0) {
          fail("scan_failed");
        }
      }
      break;
    }
    if (result.document_ids.length !== TYPESENSE_DELETION_PAGE_SIZE) fail("scan_failed");
    page += 1;
    if (page > Math.ceil(TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION
      / TYPESENSE_DELETION_PAGE_SIZE)) fail("scan_failed");
  }
  const sortedIds = [...ids].sort();
  return Object.freeze({
    role: collection.role,
    count: sortedIds.length,
    set_digest: sha256({
      version: "typesense-account-document-set-v1",
      ...collection,
      account_id: accountId,
      document_ids: sortedIds,
    }),
  });
};

export const createTypesenseDeletionCleanupParticipant = (
  registryValue: TypesenseDeletionCollectionRegistry,
  providerFenceValue: TypesenseAccountDeletionFence,
  receiptRepositoryValue: TypesenseDeletionReceiptRepository,
): DeletionSurfaceParticipant => {
  const registry = assertTypesenseDeletionCollectionRegistry(registryValue);
  const withHeldAccountWriteFence = captureMethod<TypesenseAccountDeletionFence["withHeldAccountWriteFence"]>(
    providerFenceValue, ["withHeldAccountWriteFence"], "withHeldAccountWriteFence",
    "invalid_configuration",
  );
  const loadReceipt = captureMethod<TypesenseDeletionReceiptRepository["load"]>(
    receiptRepositoryValue, ["load", "record"], "load", "invalid_configuration",
  );
  const recordReceipt = captureMethod<TypesenseDeletionReceiptRepository["record"]>(
    receiptRepositoryValue, ["load", "record"], "record", "invalid_configuration",
  );

  return Object.freeze({
    participant_id: "typesense_search_documents",
    owned_surfaces: Object.freeze(["search_documents"] as const),
    async withHeldSurfaceFence<T>(
      coordinateValue: DeletionCleanupCoordinate,
      operationRef: string,
      eligibilityDigest: string,
      callback: (session: HeldDeletionSurfaceSession) => Promise<T>,
    ): Promise<T> {
      const coordinate = validateCoordinate(coordinateValue);
      if (!OPERATION_REF.test(operationRef) || !DIGEST.test(eligibilityDigest)
        || typeof callback !== "function" || isProxy(callback)) fail("invalid_input");

      let callbackOpen = true;
      let callbackCount = 0;
      let callbackFailure: unknown;
      let hasCallbackFailure = false;
      const resultToken = Object.freeze({ token: Symbol("typesense-cleanup-result") });
      let resultValue: T | undefined;
      let outerResult: unknown;
      try {
        outerResult = await withHeldAccountWriteFence(
          coordinate, operationRef, eligibilityDigest, async (providerSessionValue) => {
            callbackCount += 1;
            if (!callbackOpen || callbackCount !== 1) fail("provider_fence_failed");
            const provider = exactRecord(providerSessionValue, [
              "source_generation_digest", "fence_receipt_digest",
              "scanAccountDocuments", "deleteAccountDocuments",
            ], "provider_fence_failed");
            if (!digest(provider.source_generation_digest) || !digest(provider.fence_receipt_digest)
              || typeof provider.scanAccountDocuments !== "function"
              || typeof provider.deleteAccountDocuments !== "function") {
              fail("provider_fence_failed");
            }
            const sourceGenerationDigest = provider.source_generation_digest as string;
            const fenceReceiptDigest = provider.fence_receipt_digest as string;
            const scanMethod = provider.scanAccountDocuments as Function;
            const disposeMethod = provider.deleteAccountDocuments as Function;
            const scan = scanMethod.bind(providerSessionValue) as
              HeldTypesenseAccountDeletionFence["scanAccountDocuments"];
            const dispose = disposeMethod.bind(providerSessionValue) as
              HeldTypesenseAccountDeletionFence["deleteAccountDocuments"];
            const pending = new Set<Promise<unknown>>();
            let pendingFailure: unknown;
            let hasPendingFailure = false;
            let sessionOpen = true;
            const assertOpen = (): void => {
              if (!callbackOpen || !sessionOpen) fail("provider_fence_failed");
            };
            const track = <R>(
              operation: () => Promise<R>,
              failureCode: "scan_failed" | "disposal_failed",
            ): Promise<R> => {
              assertOpen();
              const promise = operation().catch((error: unknown) => {
                if (error instanceof TypesenseDeletionCleanupError) throw error;
                return fail(failureCode);
              });
              pending.add(promise);
              void promise.catch((error: unknown) => {
                if (!hasPendingFailure) pendingFailure = error;
                hasPendingFailure = true;
              }).finally(() => pending.delete(promise));
              return promise;
            };
            const session: HeldDeletionSurfaceSession = Object.freeze({
              scanOwned: () => track(async () => {
                const scans = [];
                for (const collection of registry.collections) {
                  scans.push(await scanCollection(collection, coordinate.account_id, scan, assertOpen));
                  assertOpen();
                }
                const remainingCount = scans.reduce((sum, item) => sum + item.count, 0);
                const remainingSetDigest = sha256({
                  version: "typesense-search-documents-set-v1",
                  registry_digest: registry.registry_digest,
                  account_id: coordinate.account_id,
                  collections: scans,
                });
                const receipt: DeletionInventorySourceReceipt = Object.freeze({
                  version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
                  inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION,
                  scanner_contract_version: TYPESENSE_DELETION_SCANNER_VERSION,
                  ...coordinate,
                  surface: "search_documents",
                  source_frontier_digest: sha256({
                    version: "typesense-search-documents-frontier-v1",
                    source_generation_digest: sourceGenerationDigest,
                    registry_digest: registry.registry_digest,
                    remaining_set_digest: remainingSetDigest,
                  }),
                  source_authorization_digest: eligibilityDigest,
                  scan_fence_state: "held",
                  scan_fence_receipt_digest: fenceReceiptDigest,
                  remaining_count: remainingCount,
                  remaining_set_digest: remainingSetDigest,
                });
                return Object.freeze([receipt]);
              }, "scan_failed"),
              disposeOwned: (surfaces: readonly DeletionCleanupSurface[]) => track(async () => {
                const requested = exactArray(surfaces, 1, "disposal_failed");
                if (requested.length !== 1 || requested[0] !== "search_documents") {
                  fail("disposal_failed");
                }
                const observations = [];
                for (const collection of registry.collections) {
                  const key: TypesenseDeletionReceiptKey = Object.freeze({
                    version: "typesense-deletion-receipt-key-v1",
                    ...coordinate,
                    operation_ref: operationRef,
                    eligibility_digest: eligibilityDigest,
                    registry_digest: registry.registry_digest,
                    ...collection,
                  });
                  let stored: TypesenseStoredDeletionReceipt | null = null;
                  try {
                    stored = validateLoad(await loadReceipt(key), key);
                  } catch (error) {
                    if (error instanceof TypesenseDeletionCleanupError) throw error;
                    fail("receipt_failed");
                  }
                  assertOpen();
                  const request: TypesenseAccountDocumentDeleteRequest = Object.freeze({
                    version: "typesense-account-document-delete-request-v1",
                    ...collection,
                    account_id: coordinate.account_id,
                  });
                  const deleted = parseDeleteResult(await dispose(request), request);
                  assertOpen();
                  if (stored === null) {
                    const core = Object.freeze({
                      ...key,
                      result: deleted.num_deleted > 0 ? "disposed" as const : "already_absent" as const,
                      affected_count: deleted.num_deleted,
                      provider_receipt_digest: deleted.provider_receipt_digest,
                    });
                    const candidate: TypesenseStoredDeletionReceipt = Object.freeze({
                      ...core,
                      receipt_digest: receiptDigest(core),
                    });
                    try {
                      stored = validateReceipt(await recordReceipt(candidate), key);
                    } catch (error) {
                      if (error instanceof TypesenseDeletionCleanupError) throw error;
                      fail("receipt_failed");
                    }
                    assertOpen();
                  }
                  if (stored === null) fail("receipt_failed");
                  const durableReceipt = stored as TypesenseStoredDeletionReceipt;
                  observations.push(Object.freeze({
                    role: collection.role,
                    current_deleted: deleted.num_deleted,
                    current_provider_receipt_digest: deleted.provider_receipt_digest,
                    stored_receipt_digest: durableReceipt.receipt_digest,
                    stored_result: durableReceipt.result,
                  }));
                }
                const result = observations.some((item) =>
                  item.current_deleted > 0 || item.stored_result === "disposed")
                  ? "disposed" as const : "already_absent" as const;
                const receipt: DeletionCleanupDispositionReceipt = Object.freeze({
                  version: "deletion-cleanup-disposition-v1",
                  surface: "search_documents",
                  result,
                  receipt_digest: sha256({
                    version: "typesense-search-documents-disposition-v1",
                    coordinate, operationRef, eligibilityDigest,
                    registry_digest: registry.registry_digest,
                    observations,
                  }),
                });
                return Object.freeze([receipt]);
              }, "disposal_failed"),
            });
            try {
              resultValue = await callback(session);
            } catch (error) {
              callbackFailure = error;
              hasCallbackFailure = true;
            } finally {
              sessionOpen = false;
              while (pending.size > 0) await Promise.allSettled([...pending]);
            }
            if (hasCallbackFailure) throw callbackFailure;
            if (hasPendingFailure) throw pendingFailure;
            return resultToken;
          },
        );
      } catch (error) {
        if (hasCallbackFailure) {
          if (callbackFailure instanceof TypesenseDeletionCleanupError) throw callbackFailure;
          fail("callback_failed");
        }
        if (error instanceof TypesenseDeletionCleanupError) throw error;
        fail("provider_fence_failed");
      } finally {
        callbackOpen = false;
      }
      if (callbackCount !== 1 || outerResult !== resultToken) fail("provider_fence_failed");
      return resultValue as T;
    },
  });
};
