import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import {
  FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT,
  assertFirestoreLegacyGenerationCollectionRegistry,
  type FirestoreLegacyGenerationCollectionRegistry,
  type FirestoreLegacyGenerationDeleteRequest,
  type FirestoreLegacyGenerationDeleteResult,
  type FirestoreLegacyGenerationDocument,
  type FirestoreLegacyGenerationScanRequest,
  type FirestoreLegacyGenerationScanResult,
} from "../../apps/service/workers/firestore-legacy-generation-cleanup-participant";

export interface FirestoreAuthenticatedJsonRequest {
  readonly method: "GET" | "POST" | "DELETE";
  readonly path: string;
  readonly query: Readonly<Record<string, string>>;
  readonly body: Readonly<Record<string, unknown>> | null;
}

export interface FirestoreAuthenticatedJsonResponse {
  readonly status: number;
  readonly body: unknown;
}

/** Owns ADC/GCP authentication plus strict request, response-byte, and time bounds. */
export interface FirestoreAuthenticatedJsonTransport {
  request(
    request: FirestoreAuthenticatedJsonRequest,
  ): Promise<FirestoreAuthenticatedJsonResponse>;
}

export interface FirestoreLegacyGenerationDocumentClient {
  scanCollectionTree(
    request: FirestoreLegacyGenerationScanRequest,
  ): Promise<FirestoreLegacyGenerationScanResult>;
  deleteDocument(
    request: FirestoreLegacyGenerationDeleteRequest,
  ): Promise<FirestoreLegacyGenerationDeleteResult>;
}

export class FirestoreLegacyGenerationClientError extends Error {
  constructor(readonly code: "invalid_configuration" | "invalid_input" | "provider_failed") {
    super(code);
    this.name = "FirestoreLegacyGenerationClientError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OWNER_KEY = /^[\x20-\x2e\x30-\x7e]+$/;
const PAGE_TOKEN = /^[\x21-\x7e]{1,4096}$/;
const COLLECTION_ID = /^[A-Za-z0-9_-]{1,128}$/;
const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$/;
const MAX_DOCUMENT_PATH_BYTES = 6_144;
const PAGE_SIZE = 1_000;
const MAX_COLLECTION_IDS_PER_DOCUMENT = 1_000;
const MAX_DESCENDANT_DEPTH = 100;
const MAX_COORDINATE_BYTES_PER_COLLECTION = 32 * 1_024 * 1_024;
const FIELD_MASK = "omi_cleanup_coordinate_only_v1";

const fail = (code: FirestoreLegacyGenerationClientError["code"]): never => {
  throw new FirestoreLegacyGenerationClientError(code);
};
const sha256 = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");
const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);
const safeInt = (value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= maximum;

const dataRecord = (value: unknown): Record<string, unknown> => {
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

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: FirestoreLegacyGenerationClientError["code"],
): Record<string, unknown> => {
  const row = dataRecord(value);
  const actual = Object.keys(row);
  if (actual.length !== keys.length || keys.some((key) => !(key in row))) fail(code);
  return row;
};

const denseArray = (value: unknown, maximum: number): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum) fail("provider_failed");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(descriptors).length !== value.length + 1) fail("provider_failed");
  const result: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("provider_failed");
    result.push(descriptor.value);
  }
  return result;
};

const response = (value: unknown): FirestoreAuthenticatedJsonResponse => {
  const row = exactRecord(value, ["status", "body"], "provider_failed");
  if (!safeInt(row.status, 599)) fail("provider_failed");
  return Object.freeze({ status: row.status, body: row.body }) as FirestoreAuthenticatedJsonResponse;
};

const childPath = (parent: string, collectionId: string): string =>
  parent.length === 0 ? collectionId : `${parent}/${collectionId}`;
const wirePath = (path: string): string => path.split("/")
  .map((segment) => encodeURIComponent(segment)).join("/");

const parseScan = (
  registry: FirestoreLegacyGenerationCollectionRegistry,
  value: unknown,
): FirestoreLegacyGenerationScanRequest => {
  const row = exactRecord(value, [
    "version", "project_id", "database_id", "role", "collection_id", "legacy_owner_key",
    "owner_mapping_digest", "maximum_documents",
  ], "invalid_input");
  const expected = registry.collections.find((entry) => entry.role === row.role);
  if (row.version !== "firestore-legacy-generation-scan-request-v1"
    || row.project_id !== registry.project_id || row.database_id !== registry.database_id
    || expected?.collection_id !== row.collection_id
    || typeof row.legacy_owner_key !== "string" || !OWNER_KEY.test(row.legacy_owner_key)
    || Buffer.byteLength(row.legacy_owner_key, "utf8") > 128
    || !digest(row.owner_mapping_digest)
    || row.maximum_documents !== FIRESTORE_LEGACY_GENERATION_MAX_DOCUMENTS_PER_ACCOUNT) {
    fail("invalid_input");
  }
  return Object.freeze({ ...row }) as unknown as FirestoreLegacyGenerationScanRequest;
};

const parseDelete = (
  registry: FirestoreLegacyGenerationCollectionRegistry,
  value: unknown,
): FirestoreLegacyGenerationDeleteRequest => {
  const row = exactRecord(value, [
    "version", "project_id", "database_id", "role", "collection_id", "legacy_owner_key",
    "owner_mapping_digest", "document_path", "update_time",
  ], "invalid_input");
  const expected = registry.collections.find((entry) => entry.role === row.role);
  if (row.version !== "firestore-legacy-generation-delete-request-v1"
    || row.project_id !== registry.project_id || row.database_id !== registry.database_id
    || expected?.collection_id !== row.collection_id
    || typeof row.legacy_owner_key !== "string" || !OWNER_KEY.test(row.legacy_owner_key)
    || Buffer.byteLength(row.legacy_owner_key, "utf8") > 128
    || typeof row.collection_id !== "string" || !COLLECTION_ID.test(row.collection_id)
    || !digest(row.owner_mapping_digest) || typeof row.document_path !== "string"
    || typeof row.update_time !== "string" || !RFC3339.test(row.update_time)) fail("invalid_input");
  const root = `users/${row.legacy_owner_key}`;
  if ((row.document_path !== root && !row.document_path.startsWith(`${root}/`))
    || row.document_path.includes("//")
    || Buffer.byteLength(row.document_path, "utf8") > MAX_DOCUMENT_PATH_BYTES) {
    fail("invalid_input");
  }
  return Object.freeze({ ...row }) as unknown as FirestoreLegacyGenerationDeleteRequest;
};

export const createFirestoreLegacyGenerationDocumentClient = (
  registryValue: FirestoreLegacyGenerationCollectionRegistry,
  transportValue: FirestoreAuthenticatedJsonTransport,
): FirestoreLegacyGenerationDocumentClient => {
  const registry = assertFirestoreLegacyGenerationCollectionRegistry(registryValue);
  const transport = exactRecord(transportValue, ["request"], "invalid_configuration");
  if (typeof transport.request !== "function") fail("invalid_configuration");
  const requestJson = (transport.request as Function).bind(transportValue) as
    FirestoreAuthenticatedJsonTransport["request"];
  const databaseRoot = `/v1/projects/${encodeURIComponent(registry.project_id)}`
    + `/databases/${encodeURIComponent(registry.database_id)}/documents`;

  const call = async (
    request: FirestoreAuthenticatedJsonRequest,
  ): Promise<FirestoreAuthenticatedJsonResponse> => {
    try {
      return response(await requestJson(request));
    } catch (error) {
      if (error instanceof FirestoreLegacyGenerationClientError) throw error;
      fail("provider_failed");
    }
  };

  return Object.freeze({
    async scanCollectionTree(
      requestValue: FirestoreLegacyGenerationScanRequest,
    ): Promise<FirestoreLegacyGenerationScanResult> {
      const request = parseScan(registry, requestValue);
      const documents: FirestoreLegacyGenerationDocument[] = [];
      const seenCollections = new Set<string>();
      const frontierHash = createHash("sha256");
      frontierHash.update(`${JSON.stringify({
        version: "firestore-recursive-list-frontier-v1",
        project_id: registry.project_id,
        database_id: registry.database_id,
      })}\n`, "utf8");
      let visitedDocumentNodes = 0;
      let coordinateBytes = 0;
      const consumeCoordinateBytes = (...values: readonly string[]): void => {
        coordinateBytes += values.reduce((sum, value) => sum + Buffer.byteLength(value, "utf8"), 0);
        if (coordinateBytes > MAX_COORDINATE_BYTES_PER_COLLECTION) fail("provider_failed");
      };
      const recordFrontier = (value: unknown): void => {
        frontierHash.update(`${JSON.stringify(value)}\n`, "utf8");
      };
      const parseProviderDocument = (
        value: unknown,
      ): Readonly<{ readonly relative: string; readonly updateTime: string | null }> => {
        visitedDocumentNodes += 1;
        if (visitedDocumentNodes > request.maximum_documents) fail("provider_failed");
        const document = dataRecord(value);
        const documentKeys = Object.keys(document);
        if (documentKeys.some((key) => !["name", "fields", "createTime", "updateTime"].includes(key))) {
          fail("provider_failed");
        }
        if (document.fields !== undefined && Object.keys(dataRecord(document.fields)).length !== 0) {
          fail("provider_failed");
        }
        if (typeof document.name !== "string") fail("provider_failed");
        const prefix = `projects/${registry.project_id}/databases/${registry.database_id}/documents/`;
        if (!document.name.startsWith(prefix)) fail("provider_failed");
        const relative = document.name.slice(prefix.length);
        if (relative.includes("//") || Buffer.byteLength(relative, "utf8") > MAX_DOCUMENT_PATH_BYTES) {
          fail("provider_failed");
        }
        consumeCoordinateBytes(relative);
        if (document.updateTime === undefined) {
          return Object.freeze({ relative, updateTime: null });
        }
        if (typeof document.updateTime !== "string" || !RFC3339.test(document.updateTime)) {
          fail("provider_failed");
        }
        consumeCoordinateBytes(document.updateTime);
        return Object.freeze({ relative, updateTime: document.updateTime });
      };

      const listCollectionIds = async (documentPath: string): Promise<readonly string[]> => {
        const ids: string[] = [];
        let pageToken: string | null = null;
        const seenTokens = new Set<string>();
        let pageCount = 0;
        do {
          pageCount += 1;
          if (pageCount > Math.ceil(MAX_COLLECTION_IDS_PER_DOCUMENT / PAGE_SIZE) + 1) {
            fail("provider_failed");
          }
          const result = await call(Object.freeze({
            method: "POST" as const,
            path: `${databaseRoot}/${wirePath(documentPath)}:listCollectionIds`,
            query: Object.freeze({}),
            body: Object.freeze({ pageSize: PAGE_SIZE, ...(pageToken ? { pageToken } : {}) }),
          }));
          if (result.status < 200 || result.status >= 300) fail("provider_failed");
          const body = dataRecord(result.body);
          const values = body.collectionIds === undefined
            ? [] : denseArray(body.collectionIds, PAGE_SIZE);
          for (const value of values) {
            if (typeof value !== "string" || !COLLECTION_ID.test(value)) fail("provider_failed");
            consumeCoordinateBytes(value);
            ids.push(value);
            if (ids.length > MAX_COLLECTION_IDS_PER_DOCUMENT) fail("provider_failed");
          }
          const next = body.nextPageToken ?? null;
          if (next !== null && (typeof next !== "string" || !PAGE_TOKEN.test(next)
            || next === pageToken || seenTokens.has(next))) fail("provider_failed");
          recordFrontier({ operation: "list_collection_ids", documentPath, pageToken, ids: values, next });
          if (next !== null) seenTokens.add(next);
          pageToken = next as string | null;
        } while (pageToken !== null);
        return Object.freeze(ids);
      };

      const listTree = async (
        parentPath: string,
        collectionId: string,
        depth: number,
      ): Promise<void> => {
        if (depth > MAX_DESCENDANT_DEPTH) fail("provider_failed");
        const collectionPath = childPath(parentPath, collectionId);
        if (seenCollections.has(collectionPath)) fail("provider_failed");
        consumeCoordinateBytes(collectionPath);
        seenCollections.add(collectionPath);
        if (seenCollections.size > request.maximum_documents) fail("provider_failed");
        let pageToken: string | null = null;
        const seenTokens = new Set<string>();
        let pageCount = 0;
        do {
          pageCount += 1;
          if (pageCount > Math.ceil(request.maximum_documents / PAGE_SIZE) + 1) {
            fail("provider_failed");
          }
          const result = await call(Object.freeze({
            method: "GET" as const,
            path: `${databaseRoot}/${wirePath(collectionPath)}`,
            query: Object.freeze({
              pageSize: String(PAGE_SIZE),
              showMissing: "true",
              "mask.fieldPaths": FIELD_MASK,
              ...(pageToken ? { pageToken } : {}),
            }),
            body: null,
          }));
          if (result.status < 200 || result.status >= 300) fail("provider_failed");
          const body = dataRecord(result.body);
          const values = body.documents === undefined
            ? [] : denseArray(body.documents, PAGE_SIZE);
          const pagePaths: string[] = [];
          for (const value of values) {
            const { relative, updateTime } = parseProviderDocument(value);
            if (!relative.startsWith(`${collectionPath}/`)) fail("provider_failed");
            pagePaths.push(relative);
            if (updateTime !== null) {
              documents.push(Object.freeze({
                document_path: relative,
                update_time: updateTime,
              }));
              if (documents.length > request.maximum_documents) fail("provider_failed");
            }
            for (const childCollection of await listCollectionIds(relative)) {
              await listTree(relative, childCollection, depth + 1);
            }
          }
          const next = body.nextPageToken ?? null;
          if (next !== null && (typeof next !== "string" || !PAGE_TOKEN.test(next)
            || next === pageToken || seenTokens.has(next))) fail("provider_failed");
          recordFrontier({ operation: "list_documents", collectionPath, pageToken, pagePaths, next });
          if (next !== null) seenTokens.add(next);
          pageToken = next as string | null;
        } while (pageToken !== null);
      };

      const ownerRoot = `users/${request.legacy_owner_key}`;
      const rootResult = await call(Object.freeze({
        method: "GET" as const,
        path: `${databaseRoot}/${wirePath(ownerRoot)}`,
        query: Object.freeze({ "mask.fieldPaths": FIELD_MASK }),
        body: null,
      }));
      if (rootResult.status !== 404 && (rootResult.status < 200 || rootResult.status >= 300)) {
        fail("provider_failed");
      }
      if (rootResult.status !== 404) {
        const root = parseProviderDocument(rootResult.body);
        if (root.relative !== ownerRoot || root.updateTime === null) fail("provider_failed");
        documents.push(Object.freeze({ document_path: root.relative, update_time: root.updateTime }));
        recordFrontier({ operation: "get_owner_root", documentPath: ownerRoot, updateTime: root.updateTime });
      } else {
        recordFrontier({ operation: "get_owner_root", documentPath: ownerRoot, updateTime: null });
      }
      for (const topLevelCollection of await listCollectionIds(ownerRoot)) {
        await listTree(ownerRoot, topLevelCollection, 0);
      }
      documents.sort((left, right) => left.document_path.localeCompare(right.document_path));
      if (documents.some((document, index) => index > 0
        && document.document_path === documents[index - 1]?.document_path)) fail("provider_failed");
      return Object.freeze({
        version: "firestore-legacy-generation-scan-result-v1",
        project_id: registry.project_id,
        database_id: registry.database_id,
        role: request.role,
        collection_id: request.collection_id,
        legacy_owner_key: request.legacy_owner_key,
        owner_mapping_digest: request.owner_mapping_digest,
        descendant_complete: true,
        provider_frontier_digest: frontierHash.digest("hex"),
        documents: Object.freeze(documents),
      });
    },

    async deleteDocument(
      requestValue: FirestoreLegacyGenerationDeleteRequest,
    ): Promise<FirestoreLegacyGenerationDeleteResult> {
      const request = parseDelete(registry, requestValue);
      const result = await call(Object.freeze({
        method: "DELETE" as const,
        path: `${databaseRoot}/${wirePath(request.document_path)}`,
        query: Object.freeze({ "currentDocument.updateTime": request.update_time }),
        body: null,
      }));
      if (result.status !== 404 && (result.status < 200 || result.status >= 300)) {
        fail("provider_failed");
      }
      const outcome = result.status === 404 ? "already_absent" as const : "deleted" as const;
      return Object.freeze({
        version: "firestore-legacy-generation-delete-result-v1",
        document_path: request.document_path,
        update_time: request.update_time,
        result: outcome,
        provider_receipt_digest: sha256({
          version: "firestore-legacy-generation-delete-provider-receipt-v1",
          project_id: registry.project_id,
          database_id: registry.database_id,
          document_path: request.document_path,
          update_time: request.update_time,
          result: outcome,
        }),
      });
    },
  });
};
