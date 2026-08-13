import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import type { DeletionCleanupDispositionReceipt } from "./account-deletion-cleanup";
import type {
  DeletionSurfaceParticipant,
  HeldDeletionSurfaceSession,
} from "./account-deletion-cleanup-composite";
import {
  createTypesenseDeletionCleanupParticipant,
  createTypesenseDeletionCollectionRegistry,
  TYPESENSE_DELETION_PAGE_SIZE,
  TypesenseDeletionCleanupError,
  type HeldTypesenseAccountDeletionFence,
  type TypesenseAccountDeletionFence,
  type TypesenseAccountDocumentDeleteRequest,
  type TypesenseAccountDocumentScanPage,
  type TypesenseAccountDocumentScanRequest,
  type TypesenseDeletionReceiptKey,
  type TypesenseDeletionReceiptLoad,
  type TypesenseDeletionReceiptRepository,
  type TypesenseStoredDeletionReceipt,
} from "./typesense-deletion-cleanup-participant";

const digest = (value: unknown): string => createHash("sha256")
  .update(JSON.stringify(value), "utf8").digest("hex");
const coordinate = Object.freeze({
  account_id: "account:typesense-cleanup",
  control_revision: 7,
  deletion_epoch: 3,
});
const operationRef = `opref1_${"a".repeat(64)}`;
const eligibilityDigest = "b".repeat(64);
const configuration = Object.freeze({
  legacy_conversations_collection: "conversations",
  canonical_memory_atoms_collection: "canonical_memory_atoms",
});
const registry = createTypesenseDeletionCollectionRegistry(configuration);

interface FixtureOptions {
  readonly scanOverride?: (
    request: TypesenseAccountDocumentScanRequest,
    normal: TypesenseAccountDocumentScanPage,
  ) => TypesenseAccountDocumentScanPage;
  readonly failDeleteRole?: "legacy_conversations" | "canonical_memory_atoms";
  readonly captureFenceCallback?: (
    callback: (session: HeldTypesenseAccountDeletionFence) => Promise<unknown>,
  ) => void;
  readonly returnWithoutCallback?: boolean;
}

const fixture = (
  legacyIds: readonly string[] = [],
  canonicalIds: readonly string[] = [],
  options: FixtureOptions = {},
) => {
  const documents = new Map([
    ["legacy_conversations", [...legacyIds]],
    ["canonical_memory_atoms", [...canonicalIds]],
  ] as const);
  const events: string[] = [];
  const stored = new Map<string, TypesenseStoredDeletionReceipt>();
  let fenceCalls = 0;
  let receiptLoads = 0;
  let receiptRecords = 0;
  const keyString = (key: TypesenseDeletionReceiptKey): string =>
    `${key.account_id}:${key.deletion_epoch}:${key.operation_ref}:${key.role}`;

  const repository: TypesenseDeletionReceiptRepository = {
    async load(key): Promise<TypesenseDeletionReceiptLoad> {
      receiptLoads += 1;
      events.push(`load:${key.role}`);
      const receipt = stored.get(keyString(key));
      return receipt === undefined
        ? Object.freeze({ kind: "missing" as const })
        : Object.freeze({ kind: "found" as const, receipt });
    },
    async record(receipt) {
      receiptRecords += 1;
      events.push(`record:${receipt.role}`);
      const key = keyString(receipt);
      const existing = stored.get(key);
      if (existing !== undefined) return existing;
      stored.set(key, receipt);
      return receipt;
    },
  };

  const session: HeldTypesenseAccountDeletionFence = {
    source_generation_digest: "c".repeat(64),
    fence_receipt_digest: "d".repeat(64),
    async scanAccountDocuments(request) {
      events.push(`scan:${request.role}:${request.page}:${request.per_page}`);
      const all = documents.get(request.role) ?? [];
      const start = (request.page - 1) * request.per_page;
      const normal: TypesenseAccountDocumentScanPage = Object.freeze({
        version: "typesense-account-document-scan-page-v1",
        role: request.role,
        collection_name: request.collection_name,
        account_id: request.account_id,
        page: request.page,
        found: all.length,
        document_ids: Object.freeze(all.slice(start, start + request.per_page)),
      });
      return options.scanOverride?.(request, normal) ?? normal;
    },
    async deleteAccountDocuments(request: TypesenseAccountDocumentDeleteRequest) {
      events.push(`delete:${request.role}`);
      if (options.failDeleteRole === request.role) throw new Error("provider secret response");
      const existing = documents.get(request.role) ?? [];
      documents.set(request.role, []);
      return Object.freeze({
        version: "typesense-account-document-delete-result-v1" as const,
        role: request.role,
        collection_name: request.collection_name,
        account_id: request.account_id,
        num_deleted: existing.length,
        provider_receipt_digest: digest({ request, count: existing.length }),
      });
    },
  };

  const fence: TypesenseAccountDeletionFence = {
    async withHeldAccountWriteFence(_coordinate, _operation, _eligibility, callback) {
      fenceCalls += 1;
      events.push("hold");
      options.captureFenceCallback?.(callback as (session: HeldTypesenseAccountDeletionFence) => Promise<unknown>);
      if (options.returnWithoutCallback) return Object.freeze({ forged: true }) as never;
      try {
        return await callback(session);
      } finally {
        events.push("release");
      }
    },
  };

  return {
    participant: createTypesenseDeletionCleanupParticipant(registry, fence, repository),
    documents,
    events,
    session,
    stored,
    counts: () => ({ fenceCalls, receiptLoads, receiptRecords }),
  };
};

const runHeld = <T>(
  participant: DeletionSurfaceParticipant,
  callback: (session: HeldDeletionSurfaceSession) => Promise<T>,
): Promise<T> => participant.withHeldSurfaceFence(
  coordinate, operationRef, eligibilityDigest, callback,
) as Promise<T>;

describe("Typesense account-deletion cleanup participant", () => {
  test("owns both legacy and canonical collections under one honest fence and zero-rescans", async () => {
    const f = fixture(["conversation-2", "conversation-1"], ["memory-1"]);
    const result = await runHeld<readonly DeletionCleanupDispositionReceipt[]>(
      f.participant,
      async (session) => {
        const before = await session.scanOwned();
        expect(before).toHaveLength(1);
        expect(before[0]).toMatchObject({
          surface: "search_documents",
          remaining_count: 3,
          scan_fence_state: "held",
          source_authorization_digest: eligibilityDigest,
        });
        const receipts = await session.disposeOwned(["search_documents"]);
        expect((await session.scanOwned())[0]?.remaining_count).toBe(0);
        return receipts;
      },
    );

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ surface: "search_documents", result: "disposed" });
    expect(f.documents.get("legacy_conversations")).toEqual([]);
    expect(f.documents.get("canonical_memory_atoms")).toEqual([]);
    expect(f.counts()).toEqual({ fenceCalls: 1, receiptLoads: 2, receiptRecords: 2 });
    expect(f.events).toEqual([
      "hold",
      `scan:legacy_conversations:1:${TYPESENSE_DELETION_PAGE_SIZE}`,
      `scan:canonical_memory_atoms:1:${TYPESENSE_DELETION_PAGE_SIZE}`,
      "load:legacy_conversations", "delete:legacy_conversations", "record:legacy_conversations",
      "load:canonical_memory_atoms", "delete:canonical_memory_atoms", "record:canonical_memory_atoms",
      `scan:legacy_conversations:1:${TYPESENSE_DELETION_PAGE_SIZE}`,
      `scan:canonical_memory_atoms:1:${TYPESENSE_DELETION_PAGE_SIZE}`,
      "release",
    ]);
  });

  test("bounds pages, detects exact-page truncation with a sentinel, and canonicalizes IDs", async () => {
    const ids = Array.from({ length: TYPESENSE_DELETION_PAGE_SIZE }, (_, index) =>
      `conversation-${String(index).padStart(3, "0")}`).reverse();
    const f = fixture(ids);
    const receipts = await runHeld(f.participant, (session) => session.scanOwned());
    expect(receipts[0]?.remaining_count).toBe(TYPESENSE_DELETION_PAGE_SIZE);
    expect(f.events.filter((event) => event.startsWith("scan:legacy"))).toEqual([
      `scan:legacy_conversations:1:${TYPESENSE_DELETION_PAGE_SIZE}`,
      `scan:legacy_conversations:2:${TYPESENSE_DELETION_PAGE_SIZE}`,
    ]);

    const ordered = fixture([...ids].sort());
    const orderedReceipt = await runHeld(ordered.participant, (session) => session.scanOwned());
    expect(orderedReceipt[0]?.remaining_set_digest).toBe(receipts[0]?.remaining_set_digest);
  });

  test("replays durable per-collection receipts while still deleting any resurrected documents", async () => {
    const f = fixture(["conversation-1"], ["memory-1"]);
    const first = await runHeld(f.participant, (session) =>
      session.disposeOwned(["search_documents"]));
    expect(first[0]?.result).toBe("disposed");

    f.documents.set("legacy_conversations", ["late-write"]);
    const second = await runHeld(f.participant, (session) =>
      session.disposeOwned(["search_documents"]));
    expect(second[0]?.result).toBe("disposed");
    expect(f.documents.get("legacy_conversations")).toEqual([]);
    expect(f.counts()).toEqual({ fenceCalls: 2, receiptLoads: 4, receiptRecords: 2 });
    expect(f.events.filter((event) => event === "delete:legacy_conversations")).toHaveLength(2);
  });

  test("rejects a digest-valid but semantically impossible durable receipt", async () => {
    const f = fixture(["conversation-1"]);
    await runHeld(f.participant, (session) => session.disposeOwned(["search_documents"]));
    const stored = [...f.stored.values()][0]!;
    const { receipt_digest: ignored, ...existingCore } = stored;
    void ignored;
    const forgedCore = Object.freeze({ ...existingCore, result: "disposed" as const, affected_count: 0 });
    const forged = Object.freeze({
      ...forgedCore,
      receipt_digest: digest({
        contract_version: "typesense-deletion-stored-receipt-v1",
        receipt: forgedCore,
      }),
    });
    const key = [...f.stored.keys()][0]!;
    f.stored.set(key, forged);
    await expect(runHeld(f.participant, (session) =>
      session.disposeOwned(["search_documents"]))).rejects
      .toEqual(new TypesenseDeletionCleanupError("receipt_failed"));
  });

  test("partial provider failure never fabricates a surface receipt and retry repairs it", async () => {
    let failCanonical = true;
    const base = fixture(["conversation-1"], ["memory-1"], {
      get failDeleteRole() {
        return failCanonical ? "canonical_memory_atoms" as const : undefined;
      },
    });
    await expect(runHeld(base.participant, (session) =>
      session.disposeOwned(["search_documents"]))).rejects
      .toEqual(new TypesenseDeletionCleanupError("disposal_failed"));
    expect(base.stored.size).toBe(1);
    expect(base.documents.get("legacy_conversations")).toEqual([]);
    expect(base.documents.get("canonical_memory_atoms")).toEqual(["memory-1"]);

    failCanonical = false;
    await expect(runHeld(base.participant, (session) =>
      session.disposeOwned(["search_documents"]))).resolves.toMatchObject([
        { surface: "search_documents", result: "disposed" },
      ]);
    expect(base.documents.get("canonical_memory_atoms")).toEqual([]);
    expect(base.stored.size).toBe(2);
  });

  test("rejects malformed, duplicate, cross-coordinate, and drifting scan pages closed", async () => {
    const cases = [
      (request: TypesenseAccountDocumentScanRequest, normal: TypesenseAccountDocumentScanPage) =>
        Object.freeze({ ...normal, account_id: `${request.account_id}-other` }),
      (_request: TypesenseAccountDocumentScanRequest, normal: TypesenseAccountDocumentScanPage) =>
        Object.freeze({ ...normal, found: 2, document_ids: Object.freeze(["same", "same"]) }),
      (request: TypesenseAccountDocumentScanRequest, normal: TypesenseAccountDocumentScanPage) =>
        request.page === 2 ? Object.freeze({ ...normal, found: normal.found + 1 }) : normal,
    ] as const;
    for (const scanOverride of cases) {
      const ids = scanOverride === cases[2]
        ? Array.from({ length: TYPESENSE_DELETION_PAGE_SIZE }, (_, index) => `id-${index}`)
        : ["id-1"];
      const f = fixture(ids, [], { scanOverride });
      await expect(runHeld(f.participant, (session) => session.scanOwned())).rejects
        .toEqual(new TypesenseDeletionCleanupError("scan_failed"));
      expect(f.counts().receiptRecords).toBe(0);
    }
  });

  test("rejects hostile configuration and input before any dependency call", async () => {
    const f = fixture();
    expect(() => createTypesenseDeletionCollectionRegistry(
      { ...configuration, canonical_memory_atoms_collection: "conversations" },
    )).toThrow(new TypesenseDeletionCleanupError("invalid_configuration"));

    expect(() => createTypesenseDeletionCleanupParticipant(
      { ...registry } as never,
      { withHeldAccountWriteFence: async () => "no" as never },
      { load: async () => ({ kind: "missing" }), record: async (value) => value },
    )).toThrow(new TypesenseDeletionCleanupError("invalid_configuration"));

    await expect(f.participant.withHeldSurfaceFence(
      { ...coordinate, control_revision: -1 }, operationRef, eligibilityDigest, async () => "no",
    )).rejects.toEqual(new TypesenseDeletionCleanupError("invalid_input"));
    expect(f.counts().fenceCalls).toBe(0);

    let getterCalls = 0;
    const hostile = Object.defineProperty({}, "legacy_conversations_collection", {
      enumerable: true,
      get() { getterCalls += 1; return "conversations"; },
    });
    Object.defineProperty(hostile, "canonical_memory_atoms_collection", {
      enumerable: true, value: "canonical_memory_atoms",
    });
    expect(() => createTypesenseDeletionCollectionRegistry(hostile as never))
      .toThrow(new TypesenseDeletionCleanupError("invalid_configuration"));
    expect(getterCalls).toBe(0);
  });

  test("rejects a skipped or late fence callback and performs no late provider I/O", async () => {
    const skipped = fixture([], [], { returnWithoutCallback: true });
    await expect(runHeld(skipped.participant, async () => "forged")).rejects
      .toEqual(new TypesenseDeletionCleanupError("provider_fence_failed"));

    let captured: ((session: HeldTypesenseAccountDeletionFence) => Promise<unknown>) | null = null;
    const late = fixture([], [], {
      returnWithoutCallback: true,
      captureFenceCallback(callback) { captured = callback; },
    });
    await expect(runHeld(late.participant, async (session) => session.scanOwned())).rejects
      .toEqual(new TypesenseDeletionCleanupError("provider_fence_failed"));
    await expect(captured!(late.session)).rejects
      .toEqual(new TypesenseDeletionCleanupError("provider_fence_failed"));
    expect(late.events.some((event) => event.startsWith("scan:"))).toBe(false);
  });

  test("rejects a fence adapter that invokes the held callback more than once", async () => {
    const base = fixture();
    const dishonest: TypesenseAccountDeletionFence = {
      async withHeldAccountWriteFence(_coordinate, _operation, _eligibility, callback) {
        const first = await callback(base.session);
        try {
          await callback(base.session);
        } catch {
          // A dishonest adapter cannot hide the second invocation by swallowing it.
        }
        return first;
      },
    };
    const participant = createTypesenseDeletionCleanupParticipant(
      registry,
      dishonest,
      {
        load: async () => Object.freeze({ kind: "missing" as const }),
        record: async (receipt) => receipt,
      },
    );
    await expect(runHeld(participant, async () => "first")).rejects
      .toEqual(new TypesenseDeletionCleanupError("provider_fence_failed"));
  });

  test("maps arbitrary callback errors to a content-safe closed code", async () => {
    const f = fixture();
    const sentinel = "private-provider-and-memory-content";
    let failure: unknown;
    try {
      await runHeld(f.participant, async () => { throw new Error(sentinel); });
    } catch (error) {
      failure = error;
    }
    expect(failure).toEqual(new TypesenseDeletionCleanupError("callback_failed"));
    expect(String(failure)).not.toContain(sentinel);
  });

  test("drains ignored operations and keeps dependency methods captured after construction", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const f = fixture(["id-1"], [], {
      scanOverride(request, normal) {
        if (request.role === "legacy_conversations") {
          return new Proxy(normal, {}) as TypesenseAccountDocumentScanPage;
        }
        return normal;
      },
    });
    // Replace the captured provider session method after construction; the participant
    // snapshots it only when the held session is acquired, so mutation before acquisition
    // is intentionally visible and must still be validated closed.
    const original = f.session.scanAccountDocuments;
    f.session.scanAccountDocuments = async (request) => {
      await gate;
      return original(request);
    };
    let settled = false;
    const completion = runHeld(f.participant, async (session) => {
      void session.scanOwned();
      return "returned";
    }).finally(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);
    release();
    await expect(completion).rejects.toEqual(new TypesenseDeletionCleanupError("scan_failed"));
    expect(settled).toBe(true);
  });
});
