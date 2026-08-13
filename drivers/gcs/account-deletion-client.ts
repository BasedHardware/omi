import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";

import {
  GCS_DELETION_PAGE_SIZE,
  assertGcsDeletionCollectionRegistry,
  type GcsAccountObject,
  type GcsAccountObjectDeleteRequest,
  type GcsAccountObjectDeleteResult,
  type GcsAccountObjectListPage,
  type GcsAccountObjectListRequest,
  type GcsDeletionCollectionRegistry,
  type GcsDeletionRole,
  type GcsObjectMode,
} from "../../apps/service/workers/gcs-deletion-cleanup-participant";

export interface GcsAuthenticatedJsonRequest {
  readonly api_version: "storage-json-v1";
  readonly method: "GET" | "DELETE";
  readonly path: string;
  readonly query: Readonly<Record<string, string>>;
}

export interface GcsAuthenticatedJsonResponse {
  readonly status: number;
  readonly body: unknown;
}

export interface GcsAuthenticatedJsonTransport {
  request(request: GcsAuthenticatedJsonRequest): Promise<GcsAuthenticatedJsonResponse>;
}

export interface GcsAccountDeletionObjectClient {
  listAccountObjects(request: GcsAccountObjectListRequest): Promise<GcsAccountObjectListPage>;
  deleteAccountObject(request: GcsAccountObjectDeleteRequest): Promise<GcsAccountObjectDeleteResult>;
}

export class GcsAccountDeletionClientError extends Error {
  constructor(readonly code: "invalid_configuration" | "invalid_input" | "provider_failed") {
    super(code);
    this.name = "GcsAccountDeletionClientError";
  }
}

const TOKEN = /^[\x21-\x7e]{1,4096}$/;
const GENERATION = /^[0-9]{1,30}$/;
const OBJECT_NAME_MAX_BYTES = 1024;
const bucketName = (value: unknown): value is string => {
  if (typeof value !== "string" || value.length < 3 || value.length > 222 || !/^[a-z0-9][a-z0-9._-]*[a-z0-9]$/.test(value)) return false;
  return value.split(".").every((part) => part.length <= 63 && /^[a-z0-9](?:[a-z0-9_-]{0,61}[a-z0-9])?$/.test(part));
};
const fail = (code: GcsAccountDeletionClientError["code"]): never => { throw new GcsAccountDeletionClientError(code); };
const sha256 = (value: unknown): string => createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (value: unknown, keys: readonly string[], code: GcsAccountDeletionClientError["code"]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value); const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail(code);
  const out: Record<string, unknown> = {};
  for (const key of keys) { const descriptor = descriptors[key]; if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code); out[key] = descriptor.value; }
  return out;
};
const plainRecord = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Object.prototype) fail("provider_failed");
  const descriptors = Object.getOwnPropertyDescriptors(value); const out: Record<string, unknown> = {};
  for (const key of Reflect.ownKeys(descriptors)) { if (typeof key !== "string") fail("provider_failed"); const descriptor = descriptors[key]; if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("provider_failed"); out[key] = descriptor.value; }
  return out;
};
const dense = (value: unknown, max: number): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype || value.length > max) fail("provider_failed");
  const descriptors = Object.getOwnPropertyDescriptors(value); if (Reflect.ownKeys(descriptors).length !== value.length + 1) fail("provider_failed");
  const out: unknown[] = []; for (let i = 0; i < value.length; i += 1) { const descriptor = descriptors[String(i)]; if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail("provider_failed"); out.push(descriptor.value); } return out;
};
const safeInt = (value: unknown, max = Number.MAX_SAFE_INTEGER): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= max;
const parseNonNegativeInt = (value: unknown): number | null => {
  if (safeInt(value)) return value;
  if (typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value)) {
    const parsed = Number(value);
    return safeInt(parsed) ? parsed : null;
  }
  return null;
};
const parseResponse = (value: unknown): GcsAuthenticatedJsonResponse => { const row = exactRecord(value, ["status", "body"], "provider_failed"); if (!safeInt(row.status, 599) || row.status < 200 || row.status >= 300) fail("provider_failed"); return Object.freeze({ status: row.status, body: row.body }); };
const encode = (value: string): string => encodeURIComponent(value);
const parseObject = (value: unknown, mode: GcsObjectMode): GcsAccountObject => {
  const row = plainRecord(value);
  const size = parseNonNegativeInt(row.size);
  if ((row.eventBasedHold !== undefined && typeof row.eventBasedHold !== "boolean")
    || (row.temporaryHold !== undefined && typeof row.temporaryHold !== "boolean")
    || (row.retentionExpirationTime !== undefined && typeof row.retentionExpirationTime !== "string")) fail("provider_failed");
  if (typeof row.name !== "string" || row.name.length === 0 || Buffer.byteLength(row.name) > OBJECT_NAME_MAX_BYTES || typeof row.generation !== "string" || !GENERATION.test(row.generation)
    || typeof row.metageneration !== "string" || !GENERATION.test(row.metageneration) || size === null
    || typeof row.updated !== "string" || row.updated.length === 0) fail("provider_failed");
  const soft = mode === "soft_deleted";
  return Object.freeze({ name: row.name, generation: row.generation, metageneration: row.metageneration, size, updated: row.updated, mode, soft_deleted: soft, retention_held: row.eventBasedHold === true || row.temporaryHold === true, retention_expiration: typeof row.retentionExpirationTime === "string" ? row.retentionExpirationTime : null });
};

export const createGcsAccountDeletionObjectClient = (
  registryValue: GcsDeletionCollectionRegistry,
  transportValue: GcsAuthenticatedJsonTransport,
): GcsAccountDeletionObjectClient => {
  const registry = assertGcsDeletionCollectionRegistry(registryValue);
  const coordinates = new Set(registry.roles.map((entry) => `${entry.role}\0${entry.bucket_name}`));
  const transport = exactRecord(transportValue, ["request"], "invalid_configuration");
  if (typeof transport.request !== "function") fail("invalid_configuration");
  const requestJson = (transport.request as Function).bind(transportValue) as GcsAuthenticatedJsonTransport["request"];
  const coordinate = (value: unknown): Readonly<{ role: GcsDeletionRole; bucket_name: string }> => {
    const row = exactRecord(value, ["role", "bucket_name"], "invalid_input");
    if (typeof row.role !== "string" || !bucketName(row.bucket_name) || !coordinates.has(`${row.role}\0${row.bucket_name}`)) fail("invalid_input");
    return Object.freeze({ role: row.role as GcsDeletionRole, bucket_name: row.bucket_name });
  };
  return Object.freeze({
    async listAccountObjects(requestValue: GcsAccountObjectListRequest): Promise<GcsAccountObjectListPage> {
      const row = exactRecord(requestValue, ["version", "role", "bucket_name", "prefix", "owner_mapping_digest", "mode", "page_token", "limit"], "invalid_input");
      if (row.version !== "gcs-account-object-list-request-v1" || typeof row.prefix !== "string" || row.prefix.length === 0 || Buffer.byteLength(row.prefix) > OBJECT_NAME_MAX_BYTES || row.limit !== GCS_DELETION_PAGE_SIZE || (row.page_token !== null && (typeof row.page_token !== "string" || !TOKEN.test(row.page_token))) || (row.mode !== "live" && row.mode !== "versions" && row.mode !== "soft_deleted")) fail("invalid_input");
      if (typeof row.owner_mapping_digest !== "string" || !/^[0-9a-f]{64}$/.test(row.owner_mapping_digest)) fail("invalid_input");
      const point = coordinate({ role: row.role, bucket_name: row.bucket_name }); const query: Record<string, string> = { prefix: row.prefix as string, maxResults: String(GCS_DELETION_PAGE_SIZE) };
      if (row.page_token !== null) query.pageToken = row.page_token as string;
      if (row.mode === "versions") query.versions = "true";
      if (row.mode === "soft_deleted") query.softDeleted = "true";
      const wire: GcsAuthenticatedJsonRequest = Object.freeze({ api_version: "storage-json-v1", method: "GET", path: `/storage/v1/b/${encode(point.bucket_name)}/o`, query: Object.freeze(query) });
      let response: GcsAuthenticatedJsonResponse; try { response = parseResponse(await requestJson(wire)); } catch (error) { if (error instanceof GcsAccountDeletionClientError) throw error; fail("provider_failed"); }
      const body = plainRecord(response.body); const items = body.items === undefined ? [] : dense(body.items, GCS_DELETION_PAGE_SIZE); const objects = items.map((item) => parseObject(item, row.mode as GcsObjectMode));
      const next = body.nextPageToken === undefined ? null : body.nextPageToken; if (next !== null && (typeof next !== "string" || !TOKEN.test(next))) fail("provider_failed");
      return Object.freeze({ version: "gcs-account-object-list-page-v1", role: point.role, bucket_name: point.bucket_name, prefix: row.prefix as string, mode: row.mode as GcsObjectMode, page_token: row.page_token as string | null, objects: Object.freeze(objects), next_page_token: next as string | null });
    },
    async deleteAccountObject(requestValue: GcsAccountObjectDeleteRequest): Promise<GcsAccountObjectDeleteResult> {
      const row = exactRecord(requestValue, ["version", "role", "bucket_name", "name", "generation", "metageneration", "owner_mapping_digest"], "invalid_input");
      if (row.version !== "gcs-account-object-delete-request-v1" || typeof row.name !== "string" || row.name.length === 0 || Buffer.byteLength(row.name) > OBJECT_NAME_MAX_BYTES || typeof row.generation !== "string" || !GENERATION.test(row.generation) || typeof row.metageneration !== "string" || !GENERATION.test(row.metageneration)) fail("invalid_input");
      if (typeof row.owner_mapping_digest !== "string" || !/^[0-9a-f]{64}$/.test(row.owner_mapping_digest)) fail("invalid_input");
      const point = coordinate({ role: row.role, bucket_name: row.bucket_name }); const query = Object.freeze({ generation: row.generation as string, ifGenerationMatch: row.generation as string, ifMetagenerationMatch: row.metageneration as string });
      const wire: GcsAuthenticatedJsonRequest = Object.freeze({ api_version: "storage-json-v1", method: "DELETE", path: `/storage/v1/b/${encode(point.bucket_name)}/o/${encode(row.name as string)}`, query });
      let response: GcsAuthenticatedJsonResponse;
      try { response = await requestJson(wire); const parsed = exactRecord(response, ["status", "body"], "provider_failed"); if (!safeInt(parsed.status, 599) || (parsed.status !== 404 && (parsed.status < 200 || parsed.status >= 300))) fail("provider_failed"); response = Object.freeze({ status: parsed.status, body: parsed.body }); } catch (error) { if (error instanceof GcsAccountDeletionClientError) throw error; fail("provider_failed"); }
      if (response.body !== undefined && response.body !== null) plainRecord(response.body);
      return Object.freeze({ version: "gcs-account-object-delete-result-v1", role: point.role, bucket_name: point.bucket_name, name: row.name as string, generation: row.generation as string, status: response.status === 404 ? "already_absent" as const : "deleted" as const, provider_receipt_digest: sha256({ version: "gcs-provider-delete-receipt-v1", request: wire, status: response.status }) });
    },
  });
};
