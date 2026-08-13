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

export const PINECONE_DELETION_INDEX_NAME = "memories-backend" as const;
export const PINECONE_DELETION_PAGE_SIZE = 10_000 as const;
export const PINECONE_DELETION_MAX_RECORDS_PER_NAMESPACE = 100_000 as const;
export const PINECONE_DELETION_NAMESPACES = Object.freeze([
  "ns1",
  "ns2",
  "ns3",
  "ns4",
  "ns_tchunks",
  "ns_x",
  "workstream-association-v1",
] as const);
/** Semantic roles are stable SQL-facing names; namespace names are provider coordinates. */
export const PINECONE_DELETION_COLLECTION_ROLES = Object.freeze([
  "conversation_vectors",
  "memory_vectors",
  "screen_activity_vectors",
  "action_item_vectors",
  "transcript_chunk_vectors",
  "x_post_vectors",
  "workstream_association_vectors",
] as const);
const PINECONE_DELETION_COLLECTIONS = Object.freeze([
  Object.freeze({ role: "conversation_vectors", namespace: "ns1" }),
  Object.freeze({ role: "memory_vectors", namespace: "ns2" }),
  Object.freeze({ role: "screen_activity_vectors", namespace: "ns3" }),
  Object.freeze({ role: "action_item_vectors", namespace: "ns4" }),
  Object.freeze({ role: "transcript_chunk_vectors", namespace: "ns_tchunks" }),
  Object.freeze({ role: "x_post_vectors", namespace: "ns_x" }),
  Object.freeze({ role: "workstream_association_vectors", namespace: "workstream-association-v1" }),
] as const);

export type PineconeDeletionNamespace = typeof PINECONE_DELETION_NAMESPACES[number];
export type PineconeDeletionCollectionRole = typeof PINECONE_DELETION_COLLECTION_ROLES[number];

export interface PineconeDeletionCollectionRegistry {
  readonly version: "pinecone-deletion-collection-registry-v1";
  readonly index_name: typeof PINECONE_DELETION_INDEX_NAME;
  readonly registry_digest: string;
  readonly collections: readonly Readonly<{
    readonly role: PineconeDeletionCollectionRole;
    readonly namespace: PineconeDeletionNamespace;
  }>[];
}

export interface PineconeAccountVectorScanRequest {
  readonly version: "pinecone-account-vector-scan-request-v1";
  readonly role: PineconeDeletionCollectionRole;
  readonly namespace: PineconeDeletionNamespace;
  readonly account_id: string;
  readonly limit: typeof PINECONE_DELETION_PAGE_SIZE;
  readonly pagination_token: string | null;
}

export interface PineconeAccountVectorScanPage {
  readonly version: "pinecone-account-vector-scan-page-v1";
  readonly role: PineconeDeletionCollectionRole;
  readonly namespace: PineconeDeletionNamespace;
  readonly account_id: string;
  readonly limit: typeof PINECONE_DELETION_PAGE_SIZE;
  readonly pagination_token: string | null;
  readonly vector_ids: readonly string[];
  readonly next_pagination_token: string | null;
}

export interface PineconeAccountVectorDeleteRequest {
  readonly version: "pinecone-account-vector-delete-request-v1";
  readonly role: PineconeDeletionCollectionRole;
  readonly namespace: PineconeDeletionNamespace;
  readonly account_id: string;
}

export interface PineconeAccountVectorDeleteResult {
  readonly version: "pinecone-account-vector-delete-result-v1";
  readonly role: PineconeDeletionCollectionRole;
  readonly namespace: PineconeDeletionNamespace;
  readonly account_id: string;
  readonly provider_receipt_digest: string;
}

/** The concrete adapter suppresses every writer for this account and owns provider auth. */
export interface HeldPineconeAccountDeletionFence {
  readonly source_generation_digest: string;
  readonly fence_receipt_digest: string;
  scanAccountVectors(
    request: PineconeAccountVectorScanRequest,
  ): Promise<PineconeAccountVectorScanPage>;
  deleteAccountVectors(
    request: PineconeAccountVectorDeleteRequest,
  ): Promise<PineconeAccountVectorDeleteResult>;
}

export interface PineconeAccountDeletionFence {
  withHeldAccountWriteFence<T>(
    coordinate: DeletionCleanupCoordinate,
    operationRef: string,
    eligibilityDigest: string,
    callback: (session: HeldPineconeAccountDeletionFence) => Promise<T>,
  ): Promise<T>;
}

export interface PineconeDeletionReceiptKey {
  readonly version: "pinecone-deletion-receipt-key-v1";
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly operation_ref: string;
  readonly eligibility_digest: string;
  readonly registry_digest: string;
  readonly role: PineconeDeletionCollectionRole;
  readonly index_name: typeof PINECONE_DELETION_INDEX_NAME;
  readonly namespace_name: PineconeDeletionNamespace;
}

export interface PineconeStoredDeletionReceipt extends PineconeDeletionReceiptKey {
  readonly result: "disposed" | "already_absent";
  readonly pre_delete_count: number;
  /** Hash of sorted provider IDs; no vector values or metadata are retained. */
  readonly pre_delete_content_hash: string;
  readonly provider_receipt_digest: string;
  readonly receipt_digest: string;
}

export type PineconeDeletionReceiptLoad =
  | Readonly<{ readonly kind: "missing" }>
  | Readonly<{ readonly kind: "found"; readonly receipt: PineconeStoredDeletionReceipt }>;

export interface PineconeDeletionReceiptRepository {
  load(key: PineconeDeletionReceiptKey): Promise<PineconeDeletionReceiptLoad>;
  record(receipt: PineconeStoredDeletionReceipt): Promise<PineconeStoredDeletionReceipt>;
}

export type PineconeDeletionCleanupErrorCode =
  | "invalid_configuration"
  | "invalid_input"
  | "provider_fence_failed"
  | "callback_failed"
  | "scan_failed"
  | "disposal_failed"
  | "receipt_failed";

export class PineconeDeletionCleanupError extends Error {
  constructor(readonly code: PineconeDeletionCleanupErrorCode) {
    super(code);
    this.name = "PineconeDeletionCleanupError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;
const PAGINATION_TOKEN = /^[\x21-\x7e]{1,4096}$/;
const MAX_VECTOR_ID_BYTES = 512;
const registryBrand = new WeakSet<object>();

const fail = (code: PineconeDeletionCleanupErrorCode): never => {
  throw new PineconeDeletionCleanupError(code);
};

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: PineconeDeletionCleanupErrorCode,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail(code);
  const result: Record<string, unknown> = {};
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
  code: PineconeDeletionCleanupErrorCode,
): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximumLength) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== value.length + 1
    || !Object.prototype.hasOwnProperty.call(descriptors, "length")) fail(code);
  const result: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    result.push(descriptor.value);
  }
  return result;
};

const safeInteger = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;

const namespace = (value: unknown): value is PineconeDeletionNamespace =>
  typeof value === "string"
  && (PINECONE_DELETION_NAMESPACES as readonly string[]).includes(value);
const role = (value: unknown): value is PineconeDeletionCollectionRole =>
  typeof value === "string"
  && (PINECONE_DELETION_COLLECTION_ROLES as readonly string[]).includes(value);

const digest = (value: unknown): value is string =>
  typeof value === "string" && DIGEST.test(value);

const token = (value: unknown): value is string =>
  typeof value === "string" && PAGINATION_TOKEN.test(value);

export const createPineconeDeletionCollectionRegistry = (): PineconeDeletionCollectionRegistry => {
  const collections = Object.freeze(PINECONE_DELETION_COLLECTIONS.map((collection) => Object.freeze({
    role: collection.role,
    namespace: collection.namespace,
  })));
  const registry = Object.freeze({
    version: "pinecone-deletion-collection-registry-v1" as const,
    index_name: PINECONE_DELETION_INDEX_NAME,
    registry_digest: sha256({
      version: "pinecone-deletion-collection-registry-v1",
      index_name: PINECONE_DELETION_INDEX_NAME,
      collections,
    }),
    collections,
  });
  registryBrand.add(registry);
  return registry;
};

export const assertPineconeDeletionCollectionRegistry = (
  value: unknown,
): PineconeDeletionCollectionRegistry => {
  if (value === null || typeof value !== "object" || !registryBrand.has(value)) {
    fail("invalid_configuration");
  }
  return value as PineconeDeletionCollectionRegistry;
};

const validateCoordinate = (value: DeletionCleanupCoordinate): DeletionCleanupCoordinate => {
  const row = exactRecord(value, ["account_id", "control_revision", "deletion_epoch"], "invalid_input");
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
  code: PineconeDeletionCleanupErrorCode,
): T => {
  const row = exactRecord(value, keys, code);
  if (typeof row[method] !== "function") fail(code);
  return (row[method] as (...args: never[]) => unknown).bind(value) as unknown as T;
};

const receiptDigest = (receipt: Omit<PineconeStoredDeletionReceipt, "receipt_digest">): string =>
  sha256({ contract_version: "pinecone-deletion-stored-receipt-v1", receipt });

const validateReceipt = (
  value: unknown,
  key: PineconeDeletionReceiptKey,
): PineconeStoredDeletionReceipt => {
  const row = exactRecord(value, [
    "version", "account_id", "control_revision", "deletion_epoch", "operation_ref",
    "eligibility_digest", "registry_digest", "role", "index_name", "namespace_name", "result",
    "pre_delete_count", "pre_delete_content_hash", "provider_receipt_digest", "receipt_digest",
  ], "receipt_failed");
  if (row.version !== key.version || row.account_id !== key.account_id
    || row.control_revision !== key.control_revision || row.deletion_epoch !== key.deletion_epoch
    || row.operation_ref !== key.operation_ref || row.eligibility_digest !== key.eligibility_digest
    || row.registry_digest !== key.registry_digest || row.role !== key.role
    || row.index_name !== key.index_name || row.namespace_name !== key.namespace_name
    || !role(row.role) || !namespace(row.namespace_name)
    || (row.result !== "disposed" && row.result !== "already_absent")
    || !safeInteger(row.pre_delete_count, PINECONE_DELETION_MAX_RECORDS_PER_NAMESPACE)
    || (row.result === "disposed" && row.pre_delete_count === 0)
    || (row.result === "already_absent" && row.pre_delete_count !== 0)
    || !digest(row.pre_delete_content_hash) || !digest(row.provider_receipt_digest)
    || !digest(row.receipt_digest)) fail("receipt_failed");
  const copy = Object.freeze({ ...row }) as unknown as PineconeStoredDeletionReceipt;
  const { receipt_digest: ignored, ...core } = copy;
  void ignored;
  if (receiptDigest(core) !== copy.receipt_digest) fail("receipt_failed");
  return copy;
};

const validateLoad = (
  value: unknown,
  key: PineconeDeletionReceiptKey,
): PineconeStoredDeletionReceipt | null => {
  if (value === null || typeof value !== "object" || isProxy(value)) fail("receipt_failed");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const kind = descriptors.kind;
  if (!kind || !kind.enumerable || !("value" in kind)) fail("receipt_failed");
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
  request: PineconeAccountVectorScanRequest,
): Readonly<{ readonly vector_ids: readonly string[]; readonly next_pagination_token: string | null }> => {
  const row = exactRecord(value, [
    "version", "role", "namespace", "account_id", "limit", "pagination_token",
    "vector_ids", "next_pagination_token",
  ], "scan_failed");
  if (row.version !== "pinecone-account-vector-scan-page-v1"
    || row.role !== request.role || row.namespace !== request.namespace
    || row.account_id !== request.account_id || row.limit !== request.limit
    || row.pagination_token !== request.pagination_token
    || (row.next_pagination_token !== null && !token(row.next_pagination_token))) fail("scan_failed");
  const values = exactArray(row.vector_ids, PINECONE_DELETION_PAGE_SIZE, "scan_failed");
  const ids: string[] = values.map((id): string => {
    if (typeof id !== "string" || id.length === 0
      || Buffer.byteLength(id, "utf8") > MAX_VECTOR_ID_BYTES) fail("scan_failed");
    return id;
  });
  if (new Set(ids).size !== ids.length) fail("scan_failed");
  return Object.freeze({
    vector_ids: Object.freeze(ids),
    next_pagination_token: row.next_pagination_token as string | null,
  });
};

const parseDeleteResult = (
  value: unknown,
  request: PineconeAccountVectorDeleteRequest,
): PineconeAccountVectorDeleteResult => {
  const row = exactRecord(value, [
    "version", "role", "namespace", "account_id", "provider_receipt_digest",
  ], "disposal_failed");
  if (row.version !== "pinecone-account-vector-delete-result-v1"
    || row.role !== request.role || row.namespace !== request.namespace
    || row.account_id !== request.account_id || !digest(row.provider_receipt_digest)) {
    fail("disposal_failed");
  }
  return Object.freeze({ ...row }) as unknown as PineconeAccountVectorDeleteResult;
};

const scanNamespace = async (
  collection: Readonly<{ role: PineconeDeletionCollectionRole; namespace: PineconeDeletionNamespace }>,
  accountId: string,
  scan: HeldPineconeAccountDeletionFence["scanAccountVectors"],
  assertOpen: () => void,
): Promise<Readonly<{ role: PineconeDeletionCollectionRole; namespace: PineconeDeletionNamespace; count: number; set_digest: string }>> => {
  const ids = new Set<string>();
  const seenTokens = new Set<string>();
  let paginationToken: string | null = null;
  let pageCount = 0;
  while (true) {
    pageCount += 1;
    if (pageCount > Math.ceil(PINECONE_DELETION_MAX_RECORDS_PER_NAMESPACE / PINECONE_DELETION_PAGE_SIZE)) {
      fail("scan_failed");
    }
    const request: PineconeAccountVectorScanRequest = Object.freeze({
      version: "pinecone-account-vector-scan-request-v1",
      ...collection,
      account_id: accountId,
      limit: PINECONE_DELETION_PAGE_SIZE,
      pagination_token: paginationToken,
    });
    const result = parseScanPage(await scan(request), request);
    assertOpen();
    if (result.vector_ids.length === 0 && result.next_pagination_token !== null) fail("scan_failed");
    for (const id of result.vector_ids) {
      if (ids.has(id)) fail("scan_failed");
      ids.add(id);
    }
    if (ids.size > PINECONE_DELETION_MAX_RECORDS_PER_NAMESPACE) fail("scan_failed");
    if (result.next_pagination_token === null) break;
    if (seenTokens.has(result.next_pagination_token)) fail("scan_failed");
    seenTokens.add(result.next_pagination_token);
    paginationToken = result.next_pagination_token;
  }
  const sortedIds = [...ids].sort();
  return Object.freeze({
    role: collection.role,
    namespace: collection.namespace,
    count: sortedIds.length,
    set_digest: sha256({
      version: "pinecone-account-vector-set-v1",
      ...collection,
      account_id: accountId,
      vector_ids: sortedIds,
    }),
  });
};

export const createPineconeDeletionCleanupParticipant = (
  registryValue: PineconeDeletionCollectionRegistry,
  providerFenceValue: PineconeAccountDeletionFence,
  receiptRepositoryValue: PineconeDeletionReceiptRepository,
): DeletionSurfaceParticipant => {
  const registry = assertPineconeDeletionCollectionRegistry(registryValue);
  const withHeldAccountWriteFence = captureMethod<PineconeAccountDeletionFence["withHeldAccountWriteFence"]>(
    providerFenceValue, ["withHeldAccountWriteFence"], "withHeldAccountWriteFence", "invalid_configuration",
  );
  const loadReceipt = captureMethod<PineconeDeletionReceiptRepository["load"]>(
    receiptRepositoryValue, ["load", "record"], "load", "invalid_configuration",
  );
  const recordReceipt = captureMethod<PineconeDeletionReceiptRepository["record"]>(
    receiptRepositoryValue, ["load", "record"], "record", "invalid_configuration",
  );

  return Object.freeze({
    participant_id: "pinecone_vector_embeddings",
    owned_surfaces: Object.freeze(["vector_embeddings"] as const),
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
      const resultToken = Object.freeze({ token: Symbol("pinecone-cleanup-result") });
      let resultValue: T | undefined;
      let outerResult: unknown;
      try {
        outerResult = await withHeldAccountWriteFence(
          coordinate, operationRef, eligibilityDigest, async (providerSessionValue) => {
            callbackCount += 1;
            if (!callbackOpen || callbackCount !== 1) fail("provider_fence_failed");
            const provider = exactRecord(providerSessionValue, [
              "source_generation_digest", "fence_receipt_digest", "scanAccountVectors", "deleteAccountVectors",
            ], "provider_fence_failed");
            if (!digest(provider.source_generation_digest) || !digest(provider.fence_receipt_digest)
              || typeof provider.scanAccountVectors !== "function"
              || typeof provider.deleteAccountVectors !== "function") fail("provider_fence_failed");
            const sourceGenerationDigest = provider.source_generation_digest as string;
            const fenceReceiptDigest = provider.fence_receipt_digest as string;
            const scan = (provider.scanAccountVectors as Function).bind(providerSessionValue) as
              HeldPineconeAccountDeletionFence["scanAccountVectors"];
            const dispose = (provider.deleteAccountVectors as Function).bind(providerSessionValue) as
              HeldPineconeAccountDeletionFence["deleteAccountVectors"];
            const pending = new Set<Promise<unknown>>();
            let pendingFailure: unknown;
            let hasPendingFailure = false;
            let sessionOpen = true;
            const assertOpen = (): void => {
              if (!callbackOpen || !sessionOpen) fail("provider_fence_failed");
            };
            const track = <R>(operation: () => Promise<R>, failureCode: "scan_failed" | "disposal_failed"):
              Promise<R> => {
              assertOpen();
              const promise = operation().catch((error: unknown) => {
                if (error instanceof PineconeDeletionCleanupError) throw error;
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
                  scans.push(await scanNamespace(collection, coordinate.account_id, scan, assertOpen));
                  assertOpen();
                }
                const remainingCount = scans.reduce((sum, item) => sum + item.count, 0);
                const remainingSetDigest = sha256({
                  version: "pinecone-vector-embeddings-set-v1",
                  registry_digest: registry.registry_digest,
                  account_id: coordinate.account_id,
                  collections: scans,
                });
                const receipt: DeletionInventorySourceReceipt = Object.freeze({
                  version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION,
                  inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION,
                  scanner_contract_version: "pinecone-account-vector-fetch-by-metadata-v1",
                  ...coordinate,
                  surface: "vector_embeddings",
                  source_frontier_digest: sha256({
                    version: "pinecone-vector-embeddings-frontier-v1",
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
                if (requested.length !== 1 || requested[0] !== "vector_embeddings") fail("disposal_failed");
                const observations = [];
                for (const collection of registry.collections) {
                  const key: PineconeDeletionReceiptKey = Object.freeze({
                    version: "pinecone-deletion-receipt-key-v1",
                    ...coordinate,
                    operation_ref: operationRef,
                    eligibility_digest: eligibilityDigest,
                    registry_digest: registry.registry_digest,
                    role: collection.role,
                    index_name: registry.index_name,
                    namespace_name: collection.namespace,
                  });
                  const stored = validateLoad(await loadReceipt(key), key);
                  assertOpen();
                  // Pinecone delete-by-filter has no deleted-count response. Scan immediately
                  // before delete to bind the durable receipt to the exact pre-delete set.
                  const before = await scanNamespace(collection, coordinate.account_id, scan, assertOpen);
                  assertOpen();
                  const request: PineconeAccountVectorDeleteRequest = Object.freeze({
                    version: "pinecone-account-vector-delete-request-v1",
                    ...collection,
                    account_id: coordinate.account_id,
                  });
                  const deleted = parseDeleteResult(await dispose(request), request);
                  assertOpen();
                  let durable = stored;
                  if (durable === null) {
                    const core = Object.freeze({
                      ...key,
                      result: before.count > 0 ? "disposed" as const : "already_absent" as const,
                      pre_delete_count: before.count,
                      pre_delete_content_hash: before.set_digest,
                      provider_receipt_digest: deleted.provider_receipt_digest,
                    });
                    const candidate: PineconeStoredDeletionReceipt = Object.freeze({
                      ...core,
                      receipt_digest: receiptDigest(core),
                    });
                    try {
                      durable = validateReceipt(await recordReceipt(candidate), key);
                    } catch (error) {
                      if (error instanceof PineconeDeletionCleanupError) throw error;
                      fail("receipt_failed");
                    }
                    assertOpen();
                  }
                  if (durable === null) fail("receipt_failed");
                  observations.push(Object.freeze({
                    role: collection.role,
                    current_count: before.count,
                    current_set_digest: before.set_digest,
                    current_provider_receipt_digest: deleted.provider_receipt_digest,
                    stored_receipt_digest: durable.receipt_digest,
                    stored_result: durable.result,
                  }));
                }
                const result = observations.some((item) => item.current_count > 0 || item.stored_result === "disposed")
                  ? "disposed" as const : "already_absent" as const;
                return Object.freeze([Object.freeze({
                  version: "deletion-cleanup-disposition-v1" as const,
                  surface: "vector_embeddings" as const,
                  result,
                  receipt_digest: sha256({
                    version: "pinecone-vector-embeddings-disposition-v1",
                    coordinate, operationRef, eligibilityDigest,
                    registry_digest: registry.registry_digest,
                    observations,
                  }),
                })]);
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
          if (callbackFailure instanceof PineconeDeletionCleanupError) throw callbackFailure;
          fail("callback_failed");
        }
        if (error instanceof PineconeDeletionCleanupError) throw error;
        fail("provider_fence_failed");
      } finally {
        callbackOpen = false;
      }
      if (callbackCount !== 1 || outerResult !== resultToken) fail("provider_fence_failed");
      return resultValue as T;
    },
  });
};
