import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import type { DeletionCleanupCoordinate } from "./account-deletion-cleanup-composite";
import {
  GCS_DELETION_PAGE_SIZE,
  GCS_DELETION_ROLES,
  GcsDeletionCleanupError,
  createGcsDeletionCleanupParticipant,
  createGcsDeletionCollectionRegistry,
  type GcsAccountDeletionFence,
  type GcsAccountObjectDeleteRequest,
  type GcsAccountObjectListRequest,
  type GcsAccountObjectListPage,
  type GcsDeletionReceiptKey,
  type GcsDeletionReceiptRepository,
  type GcsStoredDeletionReceipt,
  type HeldGcsAccountDeletionFence,
} from "./gcs-deletion-cleanup-participant";

const hash = (value: unknown): string => createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex");
const digest = (letter: string): string => letter.repeat(64);
const coordinate: DeletionCleanupCoordinate = Object.freeze({ account_id: "account:gcs-cleanup", control_revision: 2, deletion_epoch: 3 });
const operationRef = `opref1_${"a".repeat(64)}`;
const eligibilityDigest = digest("b");

const makeRegistry = () => createGcsDeletionCollectionRegistry({ roles: GCS_DELETION_ROLES.flatMap((role, index) => [
  { role, bucket_name: `gcs-${index}-objects`, prefix_family: "account_uid_v1" as const, policy_digest: digest("c"), coverage_digest: digest("d"), enumerate_versions: true as const, enumerate_soft_deleted: true as const },
  ...(role === "speech_profiles" ? [{ role, bucket_name: "gcs-speech-legacy-objects", prefix_family: "account_uid_v1" as const, policy_digest: digest("4"), coverage_digest: digest("5"), enumerate_versions: true as const, enumerate_soft_deleted: true as const }] : []),
] )});

interface FixtureOptions { readonly softDeleted?: boolean; readonly emptyNext?: boolean; readonly failDeleteRole?: string; readonly ownerMismatch?: boolean; }
const makeFixture = (options: FixtureOptions = {}) => {
  const registry = makeRegistry();
  const deleted: string[] = []; const listModes: string[] = []; const objects = new Map<string, boolean>(); const receipts = new Map<string, GcsStoredDeletionReceipt>(); let failed = false;
  const keyOf = (key: GcsDeletionReceiptKey): string => `${key.account_id}:${key.deletion_epoch}:${key.operation_ref}:${key.role}:${key.bucket_name}`;
  const repository: GcsDeletionReceiptRepository = { async load(key) { const value = receipts.get(keyOf(key)); return value ? { kind: "found", receipt: value } : { kind: "missing" }; }, async record(receipt) { const prior = receipts.get(keyOf(receipt)); if (prior) return prior; receipts.set(keyOf(receipt), receipt); return receipt; } };
  const session: HeldGcsAccountDeletionFence = {
    source_generation_digest: digest("e"), fence_receipt_digest: digest("f"),
    owner_mapping_digest: options.ownerMismatch ? digest("8") : hash({ version: "gcs-legacy-owner-mapping-v1", account_id: coordinate.account_id, legacy_owner_keys: ["account:gcs-cleanup"] }),
    legacy_owner_keys: Object.freeze(["account:gcs-cleanup"]),
    async listAccountObjects(request: GcsAccountObjectListRequest): Promise<GcsAccountObjectListPage> {
      listModes.push(request.mode);
      const objectKey = `${request.role}:${request.bucket_name}:${request.prefix}`;
      const isTarget = request.role === "speech_profiles" && request.prefix.endsWith("speech_profile.wav");
      const present = objects.get(objectKey) ?? isTarget;
      if (isTarget) objects.set(objectKey, present);
      const include = present && ((options.softDeleted && request.mode === "soft_deleted") || (!options.softDeleted && request.mode === "versions"));
      const item = include ? [{ name: request.prefix, generation: "100", metageneration: "2", size: 12, updated: "2026-01-01T00:00:00Z", soft_deleted: request.mode === "soft_deleted", retention_held: false, retention_expiration: null }] : [];
      return Object.freeze({ version: "gcs-account-object-list-page-v1", role: request.role, bucket_name: request.bucket_name, prefix: request.prefix, mode: request.mode, page_token: request.page_token, objects: Object.freeze(item), next_page_token: options.emptyNext && request.page_token === null ? "more" : null });
    },
    async deleteAccountObject(request: GcsAccountObjectDeleteRequest) {
      if (!failed && options.failDeleteRole === request.role) { failed = true; throw new Error("provider failure"); }
      deleted.push(`${request.role}:${request.name}:${request.generation}`); objects.set(`${request.role}:${request.bucket_name}:${request.name}`, false);
      return Object.freeze({ version: "gcs-account-object-delete-result-v1" as const, role: request.role, bucket_name: request.bucket_name, name: request.name, generation: request.generation, status: "deleted" as const, provider_receipt_digest: digest("1") });
    },
  };
  const fence: GcsAccountDeletionFence = { async withHeldAccountWriteFence(_coordinate, _operation, _eligibility, callback) { return callback(session); } };
  return { registry, repository, fence, receipts, deleted, listModes, objects };
};

describe("GCS external-object deletion participant", () => {
  test("scans all eight explicit role families under the held fence", async () => {
    const fixture = makeFixture(); const participant = createGcsDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository); let receiptCount = 0;
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, async (session) => { receiptCount = (await session.scanOwned()).length; });
    expect(receiptCount).toBe(1);
    expect(fixture.registry.roles).toHaveLength(9);
    expect(new Set(fixture.listModes)).toEqual(new Set(["versions", "soft_deleted"]));
  });

  test("rejects an owner mapping digest mismatch before provider listing", async () => {
    const fixture = makeFixture({ ownerMismatch: true }); const participant = createGcsDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository);
    await expect(participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, (session) => session.scanOwned())).rejects.toMatchObject({ code: "provider_fence_failed" });
    expect(fixture.listModes).toHaveLength(0);
  });

  test("deletes exact live generations, persists per-role receipts, and replays resurrection", async () => {
    const fixture = makeFixture(); const participant = createGcsDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository);
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, (session) => session.disposeOwned(["external_objects"]));
    expect(fixture.receipts.size).toBe(9); expect(fixture.deleted).toHaveLength(2);
    fixture.objects.set("speech_profiles:gcs-0-objects:account:gcs-cleanup/speech_profile.wav", true);
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, (session) => session.disposeOwned(["external_objects"]));
    expect(fixture.deleted).toHaveLength(3);
  });

  test("blocks physical disposal when soft-deleted inventory exists", async () => {
    const fixture = makeFixture({ softDeleted: true }); const participant = createGcsDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository);
    await expect(participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, (session) => session.disposeOwned(["external_objects"]))).rejects.toMatchObject({ code: "disposal_failed" });
    expect(fixture.deleted).toHaveLength(0);
  });

  test("rejects empty continuation pages and repairs a partial delete on retry", async () => {
    const bad = makeFixture({ emptyNext: true }); const badParticipant = createGcsDeletionCleanupParticipant(bad.registry, bad.fence, bad.repository);
    await expect(badParticipant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, (session) => session.scanOwned())).rejects.toMatchObject({ code: "scan_failed" });
    const partial = makeFixture({ failDeleteRole: "speech_profiles" }); const participant = createGcsDeletionCleanupParticipant(partial.registry, partial.fence, partial.repository);
    await expect(participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, (session) => session.disposeOwned(["external_objects"]))).rejects.toMatchObject({ code: "disposal_failed" });
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, (session) => session.disposeOwned(["external_objects"]));
    expect(partial.receipts.size).toBe(9);
  });

  test("drains and denies late callback work without provider I/O", async () => {
    const fixture = makeFixture(); const participant = createGcsDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository); let late: Promise<unknown> | undefined;
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, async (session) => {
      late = new Promise((resolve, reject) => setTimeout(() => { try { session.scanOwned().then(resolve, reject); } catch (error) { reject(error); } }, 0));
    });
    await expect(late).rejects.toMatchObject({ code: "provider_fence_failed" }); expect(fixture.deleted).toHaveLength(0);
  });
});
