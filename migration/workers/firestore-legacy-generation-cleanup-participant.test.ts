import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import type { DeletionCleanupCoordinate } from "./account-deletion-cleanup-composite";
import {
  FIRESTORE_LEGACY_GENERATION_COLLECTIONS,
  FirestoreLegacyGenerationCleanupError,
  createFirestoreLegacyGenerationCleanupParticipant,
  createFirestoreLegacyGenerationCollectionRegistry,
  type FirestoreLegacyGenerationDeleteRequest,
  type FirestoreLegacyGenerationFence,
  type FirestoreLegacyGenerationReceiptKey,
  type FirestoreLegacyGenerationReceiptRepository,
  type FirestoreStoredLegacyGenerationReceipt,
  type HeldFirestoreLegacyGenerationFence,
} from "./firestore-legacy-generation-cleanup-participant";

const hash = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");
const digest = (character: string): string => character.repeat(64);
const coordinate: DeletionCleanupCoordinate = Object.freeze({
  account_id: "account:firestore-cleanup",
  control_revision: 4,
  deletion_epoch: 7,
});
const operationRef = `opref1_${"a".repeat(64)}`;
const eligibilityDigest = digest("b");

interface FixtureOptions {
  readonly ownerMismatch?: boolean;
  readonly failDeleteOnce?: boolean;
}

const makeFixture = (options: FixtureOptions = {}) => {
  const registry = createFirestoreLegacyGenerationCollectionRegistry({
    project_id: "based-hardware",
    database_id: "(default)",
    policy_digest: digest("c"),
  });
  const ownerKeys = Object.freeze(["firebase-uid"]);
  const ownerDigest = hash({
    version: "firestore-legacy-owner-mapping-v1",
    account_id: coordinate.account_id,
    legacy_owner_keys: ownerKeys,
  });
  const present = new Map<string, string>([[
    "users/firebase-uid/memories/legacy-memory",
    "2026-08-13T12:00:00.000000Z",
  ]]);
  const scanRoles: string[] = [];
  const deleted: string[] = [];
  const receipts = new Map<string, FirestoreStoredLegacyGenerationReceipt>();
  let deleteFailed = false;
  const key = (value: FirestoreLegacyGenerationReceiptKey): string =>
    `${value.operation_ref}:${value.role}:${value.collection_id}`;
  const repository: FirestoreLegacyGenerationReceiptRepository = {
    async load(value) {
      const receipt = receipts.get(key(value));
      return receipt ? { kind: "found", receipt } : { kind: "missing" };
    },
    async record(receipt) {
      const prior = receipts.get(key(receipt));
      if (prior) return prior;
      receipts.set(key(receipt), receipt);
      return receipt;
    },
  };
  const held: HeldFirestoreLegacyGenerationFence = {
    source_generation_digest: digest("d"),
    fence_receipt_digest: digest("e"),
    owner_mapping_digest: options.ownerMismatch ? digest("f") : ownerDigest,
    legacy_owner_keys: ownerKeys,
    async scanCollectionTree(request) {
      scanRoles.push(request.role);
      const root = `users/${request.legacy_owner_key}`;
      const documents = [...present.entries()]
        .filter(([path]) => path === root || path.startsWith(`${root}/`))
        .map(([document_path, update_time]) => Object.freeze({ document_path, update_time }));
      return Object.freeze({
        version: "firestore-legacy-generation-scan-result-v1" as const,
        project_id: request.project_id,
        database_id: request.database_id,
        role: request.role,
        collection_id: request.collection_id,
        legacy_owner_key: request.legacy_owner_key,
        owner_mapping_digest: request.owner_mapping_digest,
        descendant_complete: true as const,
        provider_frontier_digest: hash({ request, documents }),
        documents: Object.freeze(documents),
      });
    },
    async deleteDocument(request: FirestoreLegacyGenerationDeleteRequest) {
      if (options.failDeleteOnce && !deleteFailed) {
        deleteFailed = true;
        throw new Error("provider detail must not escape");
      }
      const prior = present.get(request.document_path);
      if (prior === request.update_time) present.delete(request.document_path);
      deleted.push(request.document_path);
      return Object.freeze({
        version: "firestore-legacy-generation-delete-result-v1" as const,
        document_path: request.document_path,
        update_time: request.update_time,
        result: prior === undefined ? "already_absent" as const : "deleted" as const,
        provider_receipt_digest: hash(request),
      });
    },
  };
  const fence: FirestoreLegacyGenerationFence = {
    async withHeldAccountWriteFence(_coordinate, _operation, _eligibility, callback) {
      return callback(held);
    },
  };
  return { registry, repository, fence, present, scanRoles, deleted, receipts };
};

describe("Firestore legacy-generation deletion participant", () => {
  test("scans the exact source registry under one held legacy writer fence", async () => {
    const fixture = makeFixture();
    const participant = createFirestoreLegacyGenerationCleanupParticipant(
      fixture.registry, fixture.fence, fixture.repository,
    );
    let scanCount = 0;
    await participant.withHeldSurfaceFence(
      coordinate, operationRef, eligibilityDigest, async (session) => {
        const receipts = await session.scanOwned();
        scanCount = receipts[0]?.remaining_count ?? -1;
      },
    );
    expect(scanCount).toBe(1);
    expect(fixture.scanRoles).toEqual([FIRESTORE_LEGACY_GENERATION_COLLECTIONS[0][0]]);
  });

  test("rejects a stale owner mapping before any provider scan", async () => {
    const fixture = makeFixture({ ownerMismatch: true });
    const participant = createFirestoreLegacyGenerationCleanupParticipant(
      fixture.registry, fixture.fence, fixture.repository,
    );
    await expect(participant.withHeldSurfaceFence(
      coordinate, operationRef, eligibilityDigest, (session) => session.scanOwned(),
    )).rejects.toBeInstanceOf(FirestoreLegacyGenerationCleanupError);
    expect(fixture.scanRoles).toHaveLength(0);
  });

  test("deletes exact update-time coordinates and rechecks resurrection on replay", async () => {
    const fixture = makeFixture();
    const participant = createFirestoreLegacyGenerationCleanupParticipant(
      fixture.registry, fixture.fence, fixture.repository,
    );
    await participant.withHeldSurfaceFence(
      coordinate, operationRef, eligibilityDigest,
      (session) => session.disposeOwned(["legacy_generation_data"]),
    );
    expect(fixture.deleted).toEqual(["users/firebase-uid/memories/legacy-memory"]);
    expect(fixture.receipts.size).toBe(FIRESTORE_LEGACY_GENERATION_COLLECTIONS.length);
    fixture.present.set(
      "users/firebase-uid/memories/recreated",
      "2026-08-13T12:01:00.000000Z",
    );
    await participant.withHeldSurfaceFence(
      coordinate, operationRef, eligibilityDigest,
      (session) => session.disposeOwned(["legacy_generation_data"]),
    );
    expect(fixture.deleted.at(-1)).toBe("users/firebase-uid/memories/recreated");
  });

  test("repairs a partial provider failure on retry without leaking provider details", async () => {
    const fixture = makeFixture({ failDeleteOnce: true });
    const participant = createFirestoreLegacyGenerationCleanupParticipant(
      fixture.registry, fixture.fence, fixture.repository,
    );
    await expect(participant.withHeldSurfaceFence(
      coordinate, operationRef, eligibilityDigest,
      (session) => session.disposeOwned(["legacy_generation_data"]),
    )).rejects.toMatchObject({ code: "disposal_failed", message: "disposal_failed" });
    await participant.withHeldSurfaceFence(
      coordinate, operationRef, eligibilityDigest,
      (session) => session.disposeOwned(["legacy_generation_data"]),
    );
    expect(fixture.present.size).toBe(0);
  });

  test("denies work captured beyond the provider callback lifetime", async () => {
    const fixture = makeFixture();
    const participant = createFirestoreLegacyGenerationCleanupParticipant(
      fixture.registry, fixture.fence, fixture.repository,
    );
    let late: Promise<unknown> | undefined;
    await participant.withHeldSurfaceFence(
      coordinate, operationRef, eligibilityDigest, async (session) => {
        late = new Promise((resolve, reject) => setTimeout(() => {
          try {
            session.scanOwned().then(resolve, reject);
          } catch (error) {
            reject(error);
          }
        }, 0));
      },
    );
    await expect(late).rejects.toMatchObject({ code: "provider_fence_failed" });
  });
});
