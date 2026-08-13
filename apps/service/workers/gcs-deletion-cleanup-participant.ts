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

export const GCS_DELETION_MAX_OBJECTS_PER_ROLE = 100_000 as const;
export const GCS_DELETION_MAX_BYTES_PER_ROLE = 1_099_511_627_776 as const;
export const GCS_DELETION_PAGE_SIZE = 1_000 as const;
export const GCS_DELETION_ROLES = Object.freeze([
  "speech_profiles", "conversation_recordings", "private_sync_chunks", "private_sync_audio",
  "private_sync_merged", "private_sync_playback", "temporal_sync", "chat_files",
] as const);
export type GcsDeletionRole = typeof GCS_DELETION_ROLES[number];
export type GcsObjectMode = "live" | "versions" | "soft_deleted";

export interface GcsDeletionRoleConfiguration {
  readonly role: GcsDeletionRole;
  readonly bucket_name: string;
  readonly prefix_family: "account_uid_v1";
  readonly policy_digest: string;
  readonly coverage_digest: string;
  readonly enumerate_versions: true;
  readonly enumerate_soft_deleted: true;
}

export interface GcsDeletionCollectionConfiguration {
  readonly roles: readonly GcsDeletionRoleConfiguration[];
}

export interface GcsDeletionCollectionRegistry {
  readonly version: "gcs-deletion-collection-registry-v1";
  readonly registry_digest: string;
  readonly roles: readonly Readonly<GcsDeletionRoleConfiguration>[];
}

export interface GcsAccountObjectListRequest {
  readonly version: "gcs-account-object-list-request-v1";
  readonly role: GcsDeletionRole;
  readonly bucket_name: string;
  readonly prefix: string;
  readonly owner_mapping_digest: string;
  readonly mode: GcsObjectMode;
  readonly page_token: string | null;
  readonly limit: typeof GCS_DELETION_PAGE_SIZE;
}

export interface GcsAccountObject {
  readonly name: string;
  readonly generation: string;
  readonly metageneration: string;
  readonly size: number;
  readonly updated: string;
  readonly mode: GcsObjectMode;
  readonly soft_deleted: boolean;
  readonly retention_held: boolean;
  readonly retention_expiration: string | null;
}

export interface GcsAccountObjectListPage {
  readonly version: "gcs-account-object-list-page-v1";
  readonly role: GcsDeletionRole;
  readonly bucket_name: string;
  readonly prefix: string;
  readonly mode: GcsObjectMode;
  readonly page_token: string | null;
  readonly objects: readonly GcsAccountObject[];
  readonly next_page_token: string | null;
}

export interface GcsAccountObjectDeleteRequest {
  readonly version: "gcs-account-object-delete-request-v1";
  readonly role: GcsDeletionRole;
  readonly bucket_name: string;
  readonly name: string;
  readonly generation: string;
  readonly metageneration: string;
  readonly owner_mapping_digest: string;
}

export interface GcsAccountObjectDeleteResult {
  readonly version: "gcs-account-object-delete-result-v1";
  readonly role: GcsDeletionRole;
  readonly bucket_name: string;
  readonly name: string;
  readonly generation: string;
  readonly status: "deleted" | "already_absent";
  readonly provider_receipt_digest: string;
}

export interface HeldGcsAccountDeletionFence {
  readonly source_generation_digest: string;
  readonly fence_receipt_digest: string;
  /** Sealed legacy Firebase-owner mapping; raw keys never cross the participant boundary. */
  readonly owner_mapping_digest: string;
  readonly legacy_owner_keys: readonly string[];
  listAccountObjects(request: GcsAccountObjectListRequest): Promise<GcsAccountObjectListPage>;
  deleteAccountObject(request: GcsAccountObjectDeleteRequest): Promise<GcsAccountObjectDeleteResult>;
}

export interface GcsAccountDeletionFence {
  withHeldAccountWriteFence<T>(
    coordinate: DeletionCleanupCoordinate,
    operationRef: string,
    eligibilityDigest: string,
    callback: (session: HeldGcsAccountDeletionFence) => Promise<T>,
  ): Promise<T>;
}

export interface GcsDeletionReceiptKey {
  readonly version: "gcs-deletion-receipt-key-v1";
  readonly account_id: string;
  readonly control_revision: number;
  readonly deletion_epoch: number;
  readonly operation_ref: string;
  readonly eligibility_digest: string;
  readonly registry_digest: string;
  readonly policy_digest: string;
  readonly owner_mapping_digest: string;
  readonly role: GcsDeletionRole;
  readonly bucket_name: string;
  readonly prefix_digest: string;
}

export interface GcsStoredDeletionReceipt extends GcsDeletionReceiptKey {
  readonly result: "disposed" | "already_absent";
  readonly pre_delete_count: number;
  readonly pre_delete_set_digest: string;
  readonly provider_receipt_digest: string;
  readonly receipt_digest: string;
}

export type GcsDeletionReceiptLoad =
  | Readonly<{ readonly kind: "missing" }>
  | Readonly<{ readonly kind: "found"; readonly receipt: GcsStoredDeletionReceipt }>;

export interface GcsDeletionReceiptRepository {
  load(key: GcsDeletionReceiptKey): Promise<GcsDeletionReceiptLoad>;
  record(receipt: GcsStoredDeletionReceipt): Promise<GcsStoredDeletionReceipt>;
}

export type GcsDeletionCleanupErrorCode =
  | "invalid_configuration" | "invalid_input" | "provider_fence_failed" | "callback_failed"
  | "scan_failed" | "disposal_failed" | "receipt_failed";

export class GcsDeletionCleanupError extends Error {
  constructor(readonly code: GcsDeletionCleanupErrorCode) {
    super(code);
    this.name = "GcsDeletionCleanupError";
  }
}

const DIGEST = /^[0-9a-f]{64}$/;
const OPERATION_REF = /^opref1_[0-9a-f]{64}$/;
const OWNER_KEY = /^[\x20-\x7e]+$/;
const bucketName = (value: unknown): value is string => {
  if (typeof value !== "string" || value.length < 3 || value.length > 222 || !/^[a-z0-9][a-z0-9._-]*[a-z0-9]$/.test(value)) return false;
  return value.split(".").every((part) => part.length <= 63 && /^[a-z0-9](?:[a-z0-9_-]{0,61}[a-z0-9])?$/.test(part));
};
const TOKEN = /^[\x21-\x7e]{1,4096}$/;
const GENERATION = /^[0-9]{1,30}$/;
const OBJECT_NAME_MAX_BYTES = 1024;
const registryBrand = new WeakSet<object>();
type Plain = Record<string, unknown>;

const fail = (code: GcsDeletionCleanupErrorCode): never => { throw new GcsDeletionCleanupError(code); };
const sha256 = (value: unknown): string => createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex");

const exactRecord = (value: unknown, keys: readonly string[], code: GcsDeletionCleanupErrorCode): Plain => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actual = Reflect.ownKeys(descriptors);
  if (actual.some((key) => typeof key !== "string") || actual.length !== keys.length
    || keys.some((key) => !Object.prototype.hasOwnProperty.call(descriptors, key))) fail(code);
  const out: Plain = {};
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    out[key] = descriptor.value;
  }
  return out;
};

const exactArray = (value: unknown, max: number, code: GcsDeletionCleanupErrorCode): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype || value.length > max) fail(code);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== value.length + 1) fail(code);
  const out: unknown[] = [];
  for (let i = 0; i < value.length; i += 1) {
    const descriptor = descriptors[String(i)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) fail(code);
    out.push(descriptor.value);
  }
  return out;
};

const digest = (value: unknown): value is string => typeof value === "string" && DIGEST.test(value);
const safeInt = (value: unknown, max = Number.MAX_SAFE_INTEGER): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= max;
const role = (value: unknown): value is GcsDeletionRole =>
  typeof value === "string" && (GCS_DELETION_ROLES as readonly string[]).includes(value);
const mode = (value: unknown): value is GcsObjectMode => value === "live" || value === "versions" || value === "soft_deleted";
const objectName = (value: unknown): value is string => typeof value === "string" && value.length > 0 && Buffer.byteLength(value) <= OBJECT_NAME_MAX_BYTES;

const prefixesFor = (roleValue: GcsDeletionRole, uid: string): readonly string[] => {
  switch (roleValue) {
    case "speech_profiles": return [`${uid}/speech_profile.wav`, `${uid}/additional_profile_recordings/`, `${uid}/people_profiles/`];
    case "conversation_recordings": return [`${uid}/`];
    case "private_sync_chunks": return [`chunks/${uid}/`];
    case "private_sync_audio": return [`audio/${uid}/`];
    case "private_sync_merged": return [`merged/${uid}/`];
    case "private_sync_playback": return [`playback/${uid}/`];
    case "temporal_sync": return [`syncing/${uid}/`];
    case "chat_files": return [`${uid}/`];
  }
};

const ownerMapping = (value: unknown, accountId: string): Readonly<{ digest: string; keys: readonly string[]; prefixes: ReadonlyMap<GcsDeletionRole, readonly string[]> }> => {
  const keys = exactArray(value, 32, "provider_fence_failed");
  if (keys.length === 0 || keys.some((key) => typeof key !== "string" || !OWNER_KEY.test(key) || Buffer.byteLength(key) > 128)
    || keys.some((key, index) => index > 0 && (key as string).localeCompare(keys[index - 1] as string) <= 0)) fail("provider_fence_failed");
  const normalized = Object.freeze(keys as string[]);
  const computed = sha256({ version: "gcs-legacy-owner-mapping-v1", account_id: accountId, legacy_owner_keys: normalized });
  const prefixes = new Map<GcsDeletionRole, readonly string[]>();
  for (const ownerRole of GCS_DELETION_ROLES) {
    const deduped = [...new Set(normalized.flatMap((key) => prefixesFor(ownerRole, key)))].sort((a, b) => a.localeCompare(b));
    if (deduped.length === 0 || deduped.length > 128) fail("provider_fence_failed");
    prefixes.set(ownerRole, Object.freeze(deduped));
  }
  return Object.freeze({ digest: computed, keys: normalized, prefixes });
};

export const createGcsDeletionCollectionRegistry = (
  value: GcsDeletionCollectionConfiguration,
): GcsDeletionCollectionRegistry => {
  const row = exactRecord(value, ["roles"], "invalid_configuration");
  const entries = exactArray(row.roles, 32, "invalid_configuration");
  if (entries.length < GCS_DELETION_ROLES.length) fail("invalid_configuration");
  const parsed = entries.map((entry): GcsDeletionRoleConfiguration => {
    const item = exactRecord(entry, ["role", "bucket_name", "prefix_family", "policy_digest", "coverage_digest", "enumerate_versions", "enumerate_soft_deleted"], "invalid_configuration");
    if (!role(item.role) || !bucketName(item.bucket_name) || item.prefix_family !== "account_uid_v1"
      || !digest(item.policy_digest) || !digest(item.coverage_digest)
      || item.enumerate_versions !== true || item.enumerate_soft_deleted !== true) fail("invalid_configuration");
    return Object.freeze({ role: item.role, bucket_name: item.bucket_name, prefix_family: item.prefix_family, policy_digest: item.policy_digest, coverage_digest: item.coverage_digest, enumerate_versions: true as const, enumerate_soft_deleted: true as const });
  });
  if (new Set(parsed.map((item) => `${item.role}\0${item.bucket_name}`)).size !== parsed.length
    || !GCS_DELETION_ROLES.every((item) => parsed.some((entry) => entry.role === item))) fail("invalid_configuration");
  const roles = Object.freeze([...parsed].sort((a, b) => a.role.localeCompare(b.role) || a.bucket_name.localeCompare(b.bucket_name)));
  const registry = Object.freeze({
    version: "gcs-deletion-collection-registry-v1" as const,
    registry_digest: sha256({ version: "gcs-deletion-collection-registry-v1", roles }),
    roles,
  });
  registryBrand.add(registry);
  return registry;
};

export const assertGcsDeletionCollectionRegistry = (value: unknown): GcsDeletionCollectionRegistry => {
  if (value === null || typeof value !== "object" || !registryBrand.has(value)) fail("invalid_configuration");
  return value as GcsDeletionCollectionRegistry;
};

const coordinate = (value: DeletionCleanupCoordinate): DeletionCleanupCoordinate => {
  const row = exactRecord(value, ["account_id", "control_revision", "deletion_epoch"], "invalid_input");
  if (!isWellFormedAccountId(row.account_id) || !safeInt(row.control_revision) || !safeInt(row.deletion_epoch)) fail("invalid_input");
  return Object.freeze({ account_id: row.account_id, control_revision: row.control_revision, deletion_epoch: row.deletion_epoch }) as DeletionCleanupCoordinate;
};

const capture = <T extends (...args: never[]) => unknown>(value: unknown, keys: readonly string[], name: string, code: GcsDeletionCleanupErrorCode): T => {
  const row = exactRecord(value, keys, code);
  if (typeof row[name] !== "function") fail(code);
  return (row[name] as (...args: never[]) => unknown).bind(value) as unknown as T;
};

const receiptDigest = (receipt: Omit<GcsStoredDeletionReceipt, "receipt_digest">): string =>
  sha256({ contract_version: "gcs-deletion-stored-receipt-v1", receipt });

const validateReceipt = (value: unknown, key: GcsDeletionReceiptKey): GcsStoredDeletionReceipt => {
  const row = exactRecord(value, ["version", "account_id", "control_revision", "deletion_epoch", "operation_ref", "eligibility_digest", "registry_digest", "policy_digest", "owner_mapping_digest", "role", "bucket_name", "prefix_digest", "result", "pre_delete_count", "pre_delete_set_digest", "provider_receipt_digest", "receipt_digest"], "receipt_failed");
  if (row.version !== key.version || row.account_id !== key.account_id || row.control_revision !== key.control_revision
    || row.deletion_epoch !== key.deletion_epoch || row.operation_ref !== key.operation_ref || row.eligibility_digest !== key.eligibility_digest
    || row.registry_digest !== key.registry_digest || row.policy_digest !== key.policy_digest || row.owner_mapping_digest !== key.owner_mapping_digest || row.role !== key.role
    || row.bucket_name !== key.bucket_name || row.prefix_digest !== key.prefix_digest
    || (row.result !== "disposed" && row.result !== "already_absent") || !safeInt(row.pre_delete_count, GCS_DELETION_MAX_OBJECTS_PER_ROLE)
    || (row.result === "disposed" && row.pre_delete_count === 0) || (row.result === "already_absent" && row.pre_delete_count !== 0)
    || !digest(row.pre_delete_set_digest) || !digest(row.provider_receipt_digest) || !digest(row.receipt_digest)) fail("receipt_failed");
  const copy = Object.freeze({ ...row }) as unknown as GcsStoredDeletionReceipt;
  const { receipt_digest: ignored, ...core } = copy;
  void ignored;
  if (receiptDigest(core) !== copy.receipt_digest) fail("receipt_failed");
  return copy;
};

const validateLoad = (value: unknown, key: GcsDeletionReceiptKey): GcsStoredDeletionReceipt | null => {
  if (value === null || typeof value !== "object" || isProxy(value)) fail("receipt_failed");
  const kindDescriptor = Object.getOwnPropertyDescriptor(value, "kind");
  if (!kindDescriptor || !kindDescriptor.enumerable || !("value" in kindDescriptor)) fail("receipt_failed");
  const row = exactRecord(value, kindDescriptor.value === "found" ? ["kind", "receipt"] : ["kind"], "receipt_failed");
  if (row.kind === "missing") return null;
  if (row.kind !== "found") fail("receipt_failed");
  return validateReceipt(row.receipt, key);
};

const parseObject = (value: unknown, request: GcsAccountObjectListRequest): GcsAccountObject => {
  const row = exactRecord(value, ["name", "generation", "metageneration", "size", "updated", "soft_deleted", "retention_held", "retention_expiration"], "scan_failed");
  if (!objectName(row.name) || typeof row.generation !== "string" || !GENERATION.test(row.generation)
    || typeof row.metageneration !== "string" || !GENERATION.test(row.metageneration) || !safeInt(row.size)
    || row.size > GCS_DELETION_MAX_BYTES_PER_ROLE || typeof row.updated !== "string" || row.updated.length === 0
    || row.soft_deleted !== (request.mode === "soft_deleted") || typeof row.retention_held !== "boolean"
    || (row.retention_expiration !== null && typeof row.retention_expiration !== "string")) fail("scan_failed");
  return Object.freeze({ ...row, mode: request.mode }) as unknown as GcsAccountObject;
};

const scanRole = async (
  entry: GcsDeletionRoleConfiguration, accountId: string, ownerMappingDigest: string, prefixes: readonly string[], provider: HeldGcsAccountDeletionFence["listAccountObjects"], assertOpen: () => void,
): Promise<Readonly<{ role: GcsDeletionRole; bucket_name: string; count: number; set_digest: string; blocked: boolean; objects: readonly GcsAccountObject[] }>> => {
  const objects: GcsAccountObject[] = [];
  const seen = new Set<string>();
  let totalBytes = 0;
  for (const prefix of prefixes) {
    // `versions=true` includes the live generation and every noncurrent
    // generation. A separate soft-deleted listing is required; listing live
    // and versions would double-count and double-delete the live object.
    for (const currentMode of ["versions", "soft_deleted"] as const) {
      let pageToken: string | null = null;
      let pages = 0;
      const seenTokens = new Set<string>();
      while (true) {
        pages += 1;
        if (pages > Math.ceil(GCS_DELETION_MAX_OBJECTS_PER_ROLE / GCS_DELETION_PAGE_SIZE)) fail("scan_failed");
        const request: GcsAccountObjectListRequest = Object.freeze({ version: "gcs-account-object-list-request-v1", role: entry.role, bucket_name: entry.bucket_name, prefix, owner_mapping_digest: ownerMappingDigest, mode: currentMode, page_token: pageToken, limit: GCS_DELETION_PAGE_SIZE });
        const page = await provider(request);
        assertOpen();
        const row = exactRecord(page, ["version", "role", "bucket_name", "prefix", "mode", "page_token", "objects", "next_page_token"], "scan_failed");
        if (row.version !== "gcs-account-object-list-page-v1" || row.role !== entry.role || row.bucket_name !== entry.bucket_name || row.prefix !== prefix || row.mode !== currentMode || row.page_token !== pageToken || (row.next_page_token !== null && (typeof row.next_page_token !== "string" || !TOKEN.test(row.next_page_token)))) fail("scan_failed");
        const values = exactArray(row.objects, GCS_DELETION_PAGE_SIZE, "scan_failed");
        for (const value of values) {
          const item = parseObject(value, request);
          const id = `${item.mode}\0${item.name}\0${item.generation}`;
          if (seen.has(id)) fail("scan_failed");
          seen.add(id); objects.push(item); totalBytes += item.size;
          if (objects.length > GCS_DELETION_MAX_OBJECTS_PER_ROLE || totalBytes > GCS_DELETION_MAX_BYTES_PER_ROLE) fail("scan_failed");
        }
        if (row.next_page_token === null) break;
        if (values.length === 0 || pageToken === row.next_page_token || seenTokens.has(row.next_page_token as string)) fail("scan_failed");
        seenTokens.add(row.next_page_token as string);
        pageToken = row.next_page_token as string;
      }
    }
  }
  const sorted = [...objects].sort((a, b) => `${a.mode}\0${a.name}\0${a.generation}`.localeCompare(`${b.mode}\0${b.name}\0${b.generation}`));
  return Object.freeze({ role: entry.role, bucket_name: entry.bucket_name, count: sorted.length, blocked: sorted.some((item) => item.soft_deleted || item.retention_held || item.retention_expiration !== null), set_digest: sha256({ version: "gcs-account-object-set-v1", role: entry.role, bucket_name: entry.bucket_name, account_id: accountId, owner_mapping_digest: ownerMappingDigest, objects: sorted.map((item) => ({ mode: item.mode, name: item.name, generation: item.generation, metageneration: item.metageneration, size: item.size })) }), objects: Object.freeze(sorted) });
};

export const createGcsDeletionCleanupParticipant = (
  registryValue: GcsDeletionCollectionRegistry, providerFenceValue: GcsAccountDeletionFence, receiptRepositoryValue: GcsDeletionReceiptRepository,
): DeletionSurfaceParticipant => {
  const registry = assertGcsDeletionCollectionRegistry(registryValue);
  const withFence = capture<GcsAccountDeletionFence["withHeldAccountWriteFence"]>(providerFenceValue, ["withHeldAccountWriteFence"], "withHeldAccountWriteFence", "invalid_configuration");
  const load = capture<GcsDeletionReceiptRepository["load"]>(receiptRepositoryValue, ["load", "record"], "load", "invalid_configuration");
  const record = capture<GcsDeletionReceiptRepository["record"]>(receiptRepositoryValue, ["load", "record"], "record", "invalid_configuration");
  return Object.freeze({
    participant_id: "gcs_external_objects",
    owned_surfaces: Object.freeze(["external_objects"] as const),
    async withHeldSurfaceFence<T>(coordinateValue: DeletionCleanupCoordinate, operationRef: string, eligibilityDigest: string, callback: (session: HeldDeletionSurfaceSession) => Promise<T>): Promise<T> {
      const coord = coordinate(coordinateValue);
      if (!OPERATION_REF.test(operationRef) || !DIGEST.test(eligibilityDigest) || typeof callback !== "function" || isProxy(callback)) fail("invalid_input");
      let open = true; let callbackCount = 0; let callbackError: unknown; let callbackFailed = false; const resultToken = {};
      let resultValue: T | undefined; let outerResult: unknown;
      try {
        outerResult = await withFence(coord, operationRef, eligibilityDigest, async (providerSessionValue) => {
          callbackCount += 1; if (!open || callbackCount !== 1) fail("provider_fence_failed");
          const provider = exactRecord(providerSessionValue, ["source_generation_digest", "fence_receipt_digest", "owner_mapping_digest", "legacy_owner_keys", "listAccountObjects", "deleteAccountObject"], "provider_fence_failed");
          if (!digest(provider.source_generation_digest) || !digest(provider.fence_receipt_digest) || !digest(provider.owner_mapping_digest) || typeof provider.listAccountObjects !== "function" || typeof provider.deleteAccountObject !== "function") fail("provider_fence_failed");
          const owners = ownerMapping(provider.legacy_owner_keys, coord.account_id);
          if (owners.digest !== provider.owner_mapping_digest) fail("provider_fence_failed");
          const list = (provider.listAccountObjects as Function).bind(providerSessionValue) as HeldGcsAccountDeletionFence["listAccountObjects"];
          const dispose = (provider.deleteAccountObject as Function).bind(providerSessionValue) as HeldGcsAccountDeletionFence["deleteAccountObject"];
          const pending = new Set<Promise<unknown>>(); let pendingError: unknown; let pendingFailed = false; let sessionOpen = true;
          const assertOpen = (): void => { if (!open || !sessionOpen) fail("provider_fence_failed"); };
          const track = <R>(operation: () => Promise<R>, errorCode: "scan_failed" | "disposal_failed"): Promise<R> => { assertOpen(); const promise = operation().catch((error) => { if (error instanceof GcsDeletionCleanupError) throw error; fail(errorCode); }); pending.add(promise); void promise.catch((error) => { if (!pendingFailed) pendingError = error; pendingFailed = true; }).finally(() => pending.delete(promise)); return promise; };
          const session: HeldDeletionSurfaceSession = Object.freeze({
            scanOwned: () => track(async () => {
              const scans = []; for (const entry of registry.roles) { scans.push(await scanRole(entry, coord.account_id, owners.digest, owners.prefixes.get(entry.role)!, list, assertOpen)); assertOpen(); }
              const remaining = scans.reduce((sum, item) => sum + item.count, 0);
              const remainingDigest = sha256({ version: "gcs-external-object-set-v1", registry_digest: registry.registry_digest, account_id: coord.account_id, roles: scans });
              const receipts: DeletionInventorySourceReceipt[] = [Object.freeze({ version: DELETION_INVENTORY_SOURCE_RECEIPT_VERSION, inventory_contract_version: DELETION_INVENTORY_CONTRACT_VERSION, scanner_contract_version: "gcs-json-api-object-list-v1", ...coord, surface: "external_objects", source_frontier_digest: sha256({ version: "gcs-external-object-frontier-v1", source_generation_digest: provider.source_generation_digest, registry_digest: registry.registry_digest, remaining_digest: remainingDigest }), source_authorization_digest: eligibilityDigest, scan_fence_state: "held", scan_fence_receipt_digest: provider.fence_receipt_digest, remaining_count: remaining, remaining_set_digest: remainingDigest })];
              return Object.freeze(receipts);
            }, "scan_failed"),
            disposeOwned: (surfaces: readonly DeletionCleanupSurface[]) => track(async () => {
              const requested = exactArray(surfaces, 1, "disposal_failed"); if (requested.length !== 1 || requested[0] !== "external_objects") fail("disposal_failed");
              const observations = [];
              for (const entry of registry.roles) {
                const prefixes = owners.prefixes.get(entry.role)!;
                const key: GcsDeletionReceiptKey = Object.freeze({ version: "gcs-deletion-receipt-key-v1", ...coord, operation_ref: operationRef, eligibility_digest: eligibilityDigest, registry_digest: registry.registry_digest, policy_digest: entry.policy_digest, owner_mapping_digest: owners.digest, role: entry.role, bucket_name: entry.bucket_name, prefix_digest: sha256({ version: "gcs-account-prefix-set-v1", role: entry.role, bucket_name: entry.bucket_name, owner_mapping_digest: owners.digest, prefixes }) });
                const stored = validateLoad(await load(key), key); assertOpen();
                const before = await scanRole(entry, coord.account_id, owners.digest, prefixes, list, assertOpen); assertOpen();
                if (before.blocked) fail("disposal_failed");
                const deletedDigests: string[] = [];
                const identities = new Set<string>();
                for (const item of before.objects) {
                  if (item.soft_deleted || item.retention_held || item.retention_expiration !== null) fail("disposal_failed");
                  const identity = `${item.name}\0${item.generation}`;
                  if (identities.has(identity)) fail("disposal_failed");
                  identities.add(identity);
                  const deletion: GcsAccountObjectDeleteRequest = Object.freeze({ version: "gcs-account-object-delete-request-v1", role: entry.role, bucket_name: entry.bucket_name, name: item.name, generation: item.generation, metageneration: item.metageneration, owner_mapping_digest: owners.digest });
                  const outcome = await dispose(deletion); assertOpen();
                  if (outcome.role !== entry.role || outcome.bucket_name !== entry.bucket_name || outcome.name !== item.name || outcome.generation !== item.generation || !digest(outcome.provider_receipt_digest)) fail("disposal_failed");
                  deletedDigests.push(outcome.provider_receipt_digest);
                }
                let durable = stored;
                if (durable === null) { const core = Object.freeze({ ...key, result: before.count > 0 ? "disposed" as const : "already_absent" as const, pre_delete_count: before.count, pre_delete_set_digest: before.set_digest, provider_receipt_digest: sha256({ version: "gcs-provider-delete-set-v1", role: entry.role, bucket_name: entry.bucket_name, digests: deletedDigests }) }); const candidate = Object.freeze({ ...core, receipt_digest: receiptDigest(core) }) as GcsStoredDeletionReceipt; durable = validateReceipt(await record(candidate), key); assertOpen(); }
                if (durable === null) fail("receipt_failed"); observations.push(Object.freeze({ role: entry.role, bucket_name: entry.bucket_name, count: before.count, stored_result: durable.result, receipt_digest: durable.receipt_digest }));
              }
              const result = observations.some((item) => item.count > 0 || item.stored_result === "disposed") ? "disposed" as const : "already_absent" as const;
              return Object.freeze([Object.freeze({ version: "deletion-cleanup-disposition-v1" as const, surface: "external_objects" as const, result, receipt_digest: sha256({ version: "gcs-external-object-disposition-v1", coordinate: coord, operationRef, eligibilityDigest, registry_digest: registry.registry_digest, observations }) })]);
            }, "disposal_failed"),
          });
          try { resultValue = await callback(session); } catch (error) { callbackError = error; callbackFailed = true; } finally { sessionOpen = false; while (pending.size > 0) await Promise.allSettled([...pending]); }
          if (callbackFailed) throw callbackError; if (pendingFailed) throw pendingError; return resultToken;
        });
      } catch (error) { if (callbackFailed) { if (callbackError instanceof GcsDeletionCleanupError) throw callbackError; fail("callback_failed"); } if (error instanceof GcsDeletionCleanupError) throw error; fail("provider_fence_failed"); } finally { open = false; }
      if (callbackCount !== 1 || outerResult !== resultToken) fail("provider_fence_failed"); return resultValue as T;
    },
  });
};
