import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  PINECONE_DELETION_INDEX_NAME,
  PINECONE_DELETION_PAGE_SIZE,
  assertPineconeDeletionCollectionRegistry,
  type PineconeAccountVectorDeleteRequest,
  type PineconeAccountVectorDeleteResult,
  type PineconeAccountVectorScanPage,
  type PineconeAccountVectorScanRequest,
  type PineconeDeletionCollectionRegistry,
  type PineconeDeletionCollectionRole,
} from "../../apps/service/workers/pinecone-deletion-cleanup-participant";

export interface PineconeAuthenticatedJsonRequest {
  readonly api_version: "2025-10";
  readonly method: "POST";
  readonly path: "/vectors/fetch_by_metadata" | "/vectors/delete";
  readonly body: Readonly<Record<string, unknown>>;
}

export interface PineconeAuthenticatedJsonResponse {
  readonly status: number;
  readonly body: unknown;
}

/** The production transport owns host, authentication, byte/time limits, and TLS. */
export interface PineconeAuthenticatedJsonTransport {
  request(request: PineconeAuthenticatedJsonRequest): Promise<PineconeAuthenticatedJsonResponse>;
}

export interface PineconeAccountDeletionVectorClient {
  scanAccountVectors(request: PineconeAccountVectorScanRequest): Promise<PineconeAccountVectorScanPage>;
  deleteAccountVectors(request: PineconeAccountVectorDeleteRequest): Promise<PineconeAccountVectorDeleteResult>;
}

export class PineconeAccountDeletionClientError extends Error {
  constructor(readonly code: "invalid_configuration" | "invalid_input" | "provider_failed") {
    super(code);
    this.name = "PineconeAccountDeletionClientError";
  }
}

const TOKEN = /^[\x21-\x7e]{1,4096}$/;
const MAX_VECTOR_ID_BYTES = 512;
const fail = (code: PineconeAccountDeletionClientError["code"]): never => {
  throw new PineconeAccountDeletionClientError(code);
};

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: PineconeAccountDeletionClientError["code"],
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

const plainRecord = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("provider_failed");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const result: Record<string, unknown> = {};
  for (const key of Reflect.ownKeys(descriptors)) {
    if (typeof key !== "string") fail("provider_failed");
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("provider_failed");
    result[key] = descriptor.value;
  }
  return result;
};

const safeStatus = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 200 && value < 300;
const role = (value: unknown): value is PineconeDeletionCollectionRole =>
  typeof value === "string" && [
    "conversation_vectors", "memory_vectors", "screen_activity_vectors", "action_item_vectors",
    "transcript_chunk_vectors", "x_post_vectors", "workstream_association_vectors",
  ].includes(value);

const parseResponse = (value: unknown): PineconeAuthenticatedJsonResponse => {
  const row = exactRecord(value, ["status", "body"], "provider_failed");
  if (!safeStatus(row.status)) fail("provider_failed");
  return Object.freeze({ status: row.status, body: row.body }) as PineconeAuthenticatedJsonResponse;
};

const parseCoordinate = (
  row: Record<string, unknown>,
  collections: ReadonlyMap<PineconeDeletionCollectionRole, Readonly<{ role: PineconeDeletionCollectionRole; namespace: string }>>,
): Readonly<{ role: PineconeDeletionCollectionRole; namespace: string; account_id: string }> => {
  if (!role(row.role) || typeof row.namespace !== "string" || collections.get(row.role)?.namespace !== row.namespace
    || !isWellFormedAccountId(row.account_id)) fail("invalid_input");
  return Object.freeze({ role: row.role, namespace: row.namespace, account_id: row.account_id });
};

export const createPineconeAccountDeletionVectorClient = (
  registryValue: PineconeDeletionCollectionRegistry,
  transportValue: PineconeAuthenticatedJsonTransport,
): PineconeAccountDeletionVectorClient => {
  const registry = assertPineconeDeletionCollectionRegistry(registryValue);
  const collectionByRole = new Map(registry.collections.map((entry) => [entry.role, entry]));
  const transport = exactRecord(transportValue, ["request"], "invalid_configuration");
  if (typeof transport.request !== "function") fail("invalid_configuration");
  const requestJson = (transport.request as Function).bind(transportValue) as PineconeAuthenticatedJsonTransport["request"];

  return Object.freeze({
    async scanAccountVectors(requestValue: PineconeAccountVectorScanRequest): Promise<PineconeAccountVectorScanPage> {
      const row = exactRecord(requestValue, [
        "version", "role", "namespace", "account_id", "limit", "pagination_token",
      ], "invalid_input");
      if (row.version !== "pinecone-account-vector-scan-request-v1" || row.limit !== PINECONE_DELETION_PAGE_SIZE
        || (row.pagination_token !== null && (typeof row.pagination_token !== "string" || !TOKEN.test(row.pagination_token)))) {
        fail("invalid_input");
      }
      const coordinate = parseCoordinate(row, collectionByRole);
      const accountFilter = Object.freeze({ uid: Object.freeze({ $eq: coordinate.account_id }) });
      const body: Record<string, unknown> = {
        namespace: coordinate.namespace,
        filter: accountFilter,
        limit: PINECONE_DELETION_PAGE_SIZE,
      };
      if (row.pagination_token !== null) body.paginationToken = row.pagination_token;
      const wireRequest: PineconeAuthenticatedJsonRequest = Object.freeze({
        api_version: "2025-10",
        method: "POST",
        path: "/vectors/fetch_by_metadata",
        body: Object.freeze(body),
      });
      let response: PineconeAuthenticatedJsonResponse;
      try {
        response = parseResponse(await requestJson(wireRequest));
      } catch (error) {
        if (error instanceof PineconeAccountDeletionClientError) throw error;
        fail("provider_failed");
      }
      const responseBody = plainRecord(response.body);
      if (typeof responseBody.namespace !== "string" || responseBody.namespace !== coordinate.namespace) {
        fail("provider_failed");
      }
      const vectors = plainRecord(responseBody.vectors);
      const vectorKeys = Object.keys(vectors);
      if (vectorKeys.length > PINECONE_DELETION_PAGE_SIZE) fail("provider_failed");
      const ids = vectorKeys.map((vectorId): string => {
        const vector = vectors[vectorId];
        const vectorRow = plainRecord(vector);
        if (typeof vectorRow.id !== "string" || vectorRow.id.length === 0
          || vectorRow.id !== vectorId
          || Buffer.byteLength(vectorRow.id, "utf8") > MAX_VECTOR_ID_BYTES) fail("provider_failed");
        return vectorRow.id;
      });
      let next: string | null = null;
      if (responseBody.pagination !== undefined) {
        const pagination = plainRecord(responseBody.pagination);
        if (!("next" in pagination) || (pagination.next !== null
          && (typeof pagination.next !== "string" || !TOKEN.test(pagination.next)))) fail("provider_failed");
        next = pagination.next as string | null;
      }
      return Object.freeze({
        version: "pinecone-account-vector-scan-page-v1",
        role: coordinate.role,
        namespace: coordinate.namespace,
        account_id: coordinate.account_id,
        limit: PINECONE_DELETION_PAGE_SIZE,
        pagination_token: row.pagination_token as string | null,
        vector_ids: Object.freeze(ids),
        next_pagination_token: next,
      });
    },

    async deleteAccountVectors(requestValue: PineconeAccountVectorDeleteRequest): Promise<PineconeAccountVectorDeleteResult> {
      const row = exactRecord(requestValue, ["version", "role", "namespace", "account_id"], "invalid_input");
      if (row.version !== "pinecone-account-vector-delete-request-v1") fail("invalid_input");
      const coordinate = parseCoordinate(row, collectionByRole);
      const accountFilter = Object.freeze({ uid: Object.freeze({ $eq: coordinate.account_id }) });
      const wireRequest: PineconeAuthenticatedJsonRequest = Object.freeze({
        api_version: "2025-10",
        method: "POST",
        path: "/vectors/delete",
        body: Object.freeze({
          namespace: coordinate.namespace,
          filter: accountFilter,
        }),
      });
      let response: PineconeAuthenticatedJsonResponse;
      try {
        response = parseResponse(await requestJson(wireRequest));
      } catch (error) {
        if (error instanceof PineconeAccountDeletionClientError) throw error;
        fail("provider_failed");
      }
      // Delete responses are intentionally not retained. Parse only as a plain object to reject accessors/proxies.
      if (response.body !== undefined && response.body !== null) plainRecord(response.body);
      return Object.freeze({
        version: "pinecone-account-vector-delete-result-v1",
        role: coordinate.role,
        namespace: coordinate.namespace,
        account_id: coordinate.account_id,
        provider_receipt_digest: sha256({
          version: "pinecone-account-vector-delete-provider-receipt-v1",
          index_name: PINECONE_DELETION_INDEX_NAME,
          request: wireRequest,
          status: response.status,
        }),
      });
    },
  });
};
