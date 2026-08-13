import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import { isWellFormedAccountId } from "../../core/control/account-control";
import {
  TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION,
  TYPESENSE_DELETION_PAGE_SIZE,
  assertTypesenseDeletionCollectionRegistry,
  type TypesenseAccountDocumentDeleteRequest,
  type TypesenseAccountDocumentDeleteResult,
  type TypesenseAccountDocumentScanPage,
  type TypesenseAccountDocumentScanRequest,
  type TypesenseDeletionCollectionRole,
  type TypesenseDeletionCollectionRegistry,
} from "../../apps/service/workers/typesense-deletion-cleanup-participant";

export interface TypesenseAuthenticatedJsonRequest {
  readonly method: "GET" | "DELETE";
  readonly path: string;
  readonly query: Readonly<Record<string, string>>;
}

export interface TypesenseAuthenticatedJsonResponse {
  readonly status: number;
  readonly body: unknown;
}

/** The production transport owns the API key and response-byte/time limits. */
export interface TypesenseAuthenticatedJsonTransport {
  request(
    request: TypesenseAuthenticatedJsonRequest,
  ): Promise<TypesenseAuthenticatedJsonResponse>;
}

export interface TypesenseAccountDeletionDocumentClient {
  scanAccountDocuments(
    request: TypesenseAccountDocumentScanRequest,
  ): Promise<TypesenseAccountDocumentScanPage>;
  deleteAccountDocuments(
    request: TypesenseAccountDocumentDeleteRequest,
  ): Promise<TypesenseAccountDocumentDeleteResult>;
}

export class TypesenseAccountDeletionClientError extends Error {
  constructor(readonly code: "invalid_configuration" | "invalid_input" | "provider_failed") {
    super(code);
    this.name = "TypesenseAccountDeletionClientError";
  }
}

const COLLECTION = /^[A-Za-z0-9_-]{1,128}$/;
const MAX_DOCUMENT_ID_BYTES = 512;
const QUERY_BY: Readonly<Record<TypesenseDeletionCollectionRole, string>> = Object.freeze({
  legacy_conversations: "structured.overview,structured.title",
  canonical_memory_atoms: "content,entity_terms,predicate",
});

const fail = (code: TypesenseAccountDeletionClientError["code"]): never => {
  throw new TypesenseAccountDeletionClientError(code);
};

const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: TypesenseAccountDeletionClientError["code"],
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

const plainDataRecord = (
  value: unknown,
  requiredKeys: readonly string[],
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail("provider_failed");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string")
    || requiredKeys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) {
    fail("provider_failed");
  }
  const result: Record<string, unknown> = {};
  for (const key of keys as string[]) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("provider_failed");
    result[key] = descriptor.value;
  }
  return result;
};

const denseArray = (value: unknown, maximum: number): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum) fail("provider_failed");
  const array = value as unknown[];
  const descriptors = Object.getOwnPropertyDescriptors(array);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== array.length + 1) {
    fail("provider_failed");
  }
  const result: unknown[] = [];
  for (let index = 0; index < array.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("provider_failed");
    result.push(descriptor.value);
  }
  return result;
};

const safeInteger = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;

const role = (value: unknown): value is TypesenseDeletionCollectionRole =>
  value === "legacy_conversations" || value === "canonical_memory_atoms";

const parseCollectionCoordinate = (
  row: Record<string, unknown>,
): Readonly<{
  readonly role: TypesenseDeletionCollectionRole;
  readonly collection_name: string;
  readonly account_id: string;
}> => {
  if (!role(row.role) || typeof row.collection_name !== "string"
    || !COLLECTION.test(row.collection_name) || !isWellFormedAccountId(row.account_id)) {
    fail("invalid_input");
  }
  return Object.freeze({
    role: row.role as TypesenseDeletionCollectionRole,
    collection_name: row.collection_name as string,
    account_id: row.account_id as string,
  });
};

const filterLiteral = (value: string): string =>
  `\`${value.replaceAll("\\", "\\\\").replaceAll("`", "\\`")}\``;

const accountFilter = (accountId: string): string => `userId:=${filterLiteral(accountId)}`;

const parseResponse = (value: unknown): TypesenseAuthenticatedJsonResponse => {
  const row = exactRecord(value, ["status", "body"], "provider_failed");
  if (!safeInteger(row.status, 599) || row.status < 200 || row.status >= 300) {
    fail("provider_failed");
  }
  return Object.freeze({ status: row.status, body: row.body }) as TypesenseAuthenticatedJsonResponse;
};

export const createTypesenseAccountDeletionDocumentClient = (
  registryValue: TypesenseDeletionCollectionRegistry,
  transportValue: TypesenseAuthenticatedJsonTransport,
): TypesenseAccountDeletionDocumentClient => {
  const registry = assertTypesenseDeletionCollectionRegistry(registryValue);
  const collectionByRole = new Map(registry.collections.map((entry) => [entry.role, entry.collection_name]));
  const transport = exactRecord(transportValue, ["request"], "invalid_configuration");
  if (typeof transport.request !== "function") fail("invalid_configuration");
  const requestJson = (transport.request as Function).bind(transportValue) as
    TypesenseAuthenticatedJsonTransport["request"];

  return Object.freeze({
    async scanAccountDocuments(
      requestValue: TypesenseAccountDocumentScanRequest,
    ): Promise<TypesenseAccountDocumentScanPage> {
      const row = exactRecord(requestValue, [
        "version", "role", "collection_name", "account_id", "page", "per_page",
      ], "invalid_input");
      const coordinate = parseCollectionCoordinate(row);
      if (collectionByRole.get(coordinate.role) !== coordinate.collection_name) fail("invalid_input");
      const maximumPage = Math.ceil(TYPESENSE_DELETION_MAX_DOCUMENTS_PER_COLLECTION
        / TYPESENSE_DELETION_PAGE_SIZE) + 1;
      if (row.version !== "typesense-account-document-scan-request-v1"
        || !safeInteger(row.page, maximumPage) || row.page < 1
        || row.per_page !== TYPESENSE_DELETION_PAGE_SIZE) fail("invalid_input");
      const request = Object.freeze({
        method: "GET" as const,
        path: `/collections/${encodeURIComponent(coordinate.collection_name)}/documents/search`,
        query: Object.freeze({
          q: "*",
          query_by: QUERY_BY[coordinate.role],
          filter_by: accountFilter(coordinate.account_id),
          include_fields: "id",
          highlight_fields: "none",
          page: String(row.page),
          per_page: String(TYPESENSE_DELETION_PAGE_SIZE),
          use_cache: "false",
        }),
      });
      let response!: TypesenseAuthenticatedJsonResponse;
      try {
        response = parseResponse(await requestJson(request));
      } catch (error) {
        if (error instanceof TypesenseAccountDeletionClientError) throw error;
        fail("provider_failed");
      }
      const body = plainDataRecord(response.body, ["found", "hits"]);
      if (!safeInteger(body.found)) fail("provider_failed");
      const hits = denseArray(body.hits, TYPESENSE_DELETION_PAGE_SIZE);
      const ids = hits.map((hit): string => {
        const hitRow = plainDataRecord(hit, ["document"]);
        const document = plainDataRecord(hitRow.document, ["id"]);
        if (typeof document.id !== "string" || document.id.length === 0
          || Buffer.byteLength(document.id, "utf8") > MAX_DOCUMENT_ID_BYTES) {
          fail("provider_failed");
        }
        return document.id as string;
      });
      return Object.freeze({
        version: "typesense-account-document-scan-page-v1",
        role: coordinate.role,
        collection_name: coordinate.collection_name,
        account_id: coordinate.account_id,
        page: row.page as number,
        found: body.found as number,
        document_ids: Object.freeze(ids),
      });
    },

    async deleteAccountDocuments(
      requestValue: TypesenseAccountDocumentDeleteRequest,
    ): Promise<TypesenseAccountDocumentDeleteResult> {
      const row = exactRecord(requestValue, [
        "version", "role", "collection_name", "account_id",
      ], "invalid_input");
      const coordinate = parseCollectionCoordinate(row);
      if (collectionByRole.get(coordinate.role) !== coordinate.collection_name) fail("invalid_input");
      if (row.version !== "typesense-account-document-delete-request-v1") fail("invalid_input");
      const request = Object.freeze({
        method: "DELETE" as const,
        path: `/collections/${encodeURIComponent(coordinate.collection_name)}/documents`,
        query: Object.freeze({
          filter_by: accountFilter(coordinate.account_id),
          batch_size: "100",
        }),
      });
      let response!: TypesenseAuthenticatedJsonResponse;
      try {
        response = parseResponse(await requestJson(request));
      } catch (error) {
        if (error instanceof TypesenseAccountDeletionClientError) throw error;
        fail("provider_failed");
      }
      const body = plainDataRecord(response.body, ["num_deleted"]);
      if (!safeInteger(body.num_deleted)) fail("provider_failed");
      return Object.freeze({
        version: "typesense-account-document-delete-result-v1",
        role: coordinate.role,
        collection_name: coordinate.collection_name,
        account_id: coordinate.account_id,
        num_deleted: body.num_deleted as number,
        provider_receipt_digest: sha256({
          version: "typesense-account-document-delete-provider-receipt-v1",
          request,
          num_deleted: body.num_deleted,
        }),
      });
    },
  });
};
