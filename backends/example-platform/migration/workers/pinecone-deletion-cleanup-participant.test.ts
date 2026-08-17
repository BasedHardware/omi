import { describe, expect, test } from "bun:test";

import {
  PINECONE_DELETION_INDEX_NAME,
  PINECONE_DELETION_NAMESPACES,
  createPineconeDeletionCleanupParticipant,
  createPineconeDeletionCollectionRegistry,
  PineconeDeletionCleanupError,
  type HeldPineconeAccountDeletionFence,
  type PineconeAccountDeletionFence,
  type PineconeAccountVectorDeleteRequest,
  type PineconeAccountVectorDeleteResult,
  type PineconeAccountVectorScanPage,
  type PineconeAccountVectorScanRequest,
  type PineconeDeletionReceiptKey,
  type PineconeDeletionReceiptRepository,
  type PineconeStoredDeletionReceipt,
} from "./pinecone-deletion-cleanup-participant";

const coordinate = Object.freeze({ account_id: "account:pinecone-cleanup", control_revision: 7, deletion_epoch: 3 });
const operationRef = `opref1_${"a".repeat(64)}`;
const eligibilityDigest = "b".repeat(64);
const digest = (value: unknown): string => {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  let hash = 0;
  for (const byte of bytes) hash = (hash * 33 + byte) >>> 0;
  return hash.toString(16).padStart(64, "0");
};

const makeFixture = (initial: readonly string[] = [], failDeleteOnceRole?: string) => {
  const registry = createPineconeDeletionCollectionRegistry();
  const docs = new Map(registry.collections.map((entry, index) => [
    entry.namespace, index === 1 ? ["memproj:" + "f".repeat(64), "uid-memory-stale"] : [...initial],
  ]));
  const receipts = new Map<string, PineconeStoredDeletionReceipt>();
  const deletes: string[] = [];
  let failedDelete = false;
  const keyOf = (key: PineconeDeletionReceiptKey): string =>
    `${key.account_id}:${key.deletion_epoch}:${key.operation_ref}:${key.role}`;
  const repository: PineconeDeletionReceiptRepository = {
    async load(key) {
      const found = receipts.get(keyOf(key));
      return found === undefined ? { kind: "missing" } : { kind: "found", receipt: found };
    },
    async record(receipt) {
      const key = keyOf(receipt);
      const found = receipts.get(key);
      if (found !== undefined) return found;
      receipts.set(key, receipt);
      return receipt;
    },
  };
  const session: HeldPineconeAccountDeletionFence = {
    source_generation_digest: "c".repeat(64),
    fence_receipt_digest: "d".repeat(64),
    async scanAccountVectors(request: PineconeAccountVectorScanRequest): Promise<PineconeAccountVectorScanPage> {
      const values = docs.get(request.namespace) ?? [];
      const page = request.pagination_token === null ? values.slice(0, 2) : values.slice(2);
      return Object.freeze({
        version: "pinecone-account-vector-scan-page-v1",
        role: request.role,
        namespace: request.namespace,
        account_id: request.account_id,
        limit: request.limit,
        pagination_token: request.pagination_token,
        vector_ids: Object.freeze(page),
        next_pagination_token: request.pagination_token === null && values.length > 2 ? "next" : null,
      });
    },
    async deleteAccountVectors(request: PineconeAccountVectorDeleteRequest): Promise<PineconeAccountVectorDeleteResult> {
      if (!failedDelete && failDeleteOnceRole === request.namespace) {
        failedDelete = true;
        throw new Error("provider failure");
      }
      deletes.push(request.namespace);
      docs.set(request.namespace, []);
      return Object.freeze({
        version: "pinecone-account-vector-delete-result-v1",
        role: request.role,
        namespace: request.namespace,
        account_id: request.account_id,
        provider_receipt_digest: "e".repeat(64),
      });
    },
  };
  const fence: PineconeAccountDeletionFence = {
    async withHeldAccountWriteFence(_coordinate, _operation, _eligibility, callback) {
      return callback(session);
    },
  };
  return { registry, repository, fence, docs, receipts, deletes };
};

describe("Pinecone account-deletion cleanup participant", () => {
  test("owns the fixed index and all seven semantic collections; scans canonical and stale IDs", async () => {
    const fixture = makeFixture(["uid-conversation-1"]);
    const participant = createPineconeDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository);
    expect(participant.owned_surfaces).toEqual(["vector_embeddings"]);
    let receipts: readonly unknown[] = [];
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, async (session) => {
      receipts = await session.scanOwned();
    });
    expect(receipts).toHaveLength(1);
    expect((receipts[0] as { remaining_count: number }).remaining_count).toBe(8);
    expect(fixture.registry.index_name).toBe(PINECONE_DELETION_INDEX_NAME);
    expect(fixture.registry.collections.map((entry) => entry.namespace)).toEqual([...PINECONE_DELETION_NAMESPACES]);
  });

  test("deletes every namespace, records per-namespace receipts, and replay deletes resurrection", async () => {
    const fixture = makeFixture(["uid-one"]);
    const participant = createPineconeDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository);
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest,
      (session) => session.disposeOwned(["vector_embeddings"]));
    expect(fixture.deletes).toHaveLength(7);
    expect(fixture.receipts.size).toBe(7);
    fixture.docs.get("ns2")?.push("resurrected");
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest,
      (session) => session.disposeOwned(["vector_embeddings"]));
    expect(fixture.deletes).toHaveLength(14);
  });

  test("retains partial receipts and repairs the failed namespace on retry", async () => {
    const fixture = makeFixture(["uid-one"], "ns3");
    const participant = createPineconeDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository);
    await expect(participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest,
      (session) => session.disposeOwned(["vector_embeddings"]))).rejects.toMatchObject({ code: "disposal_failed" });
    expect(fixture.receipts.size).toBe(2);
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest,
      (session) => session.disposeOwned(["vector_embeddings"]));
    expect(fixture.receipts.size).toBe(7);
  });

  test("rejects duplicate IDs and token cycles closed", async () => {
    const fixture = makeFixture(["a", "b", "c"]);
    const badFence: PineconeAccountDeletionFence = {
      async withHeldAccountWriteFence(c, o, e, callback) {
        return callback({
          source_generation_digest: "c".repeat(64),
          fence_receipt_digest: "d".repeat(64),
          async scanAccountVectors(request: PineconeAccountVectorScanRequest) {
            return Object.freeze({ version: "pinecone-account-vector-scan-page-v1", role: request.role, namespace: request.namespace,
              account_id: request.account_id, limit: request.limit, pagination_token: request.pagination_token,
              vector_ids: Object.freeze(["dup"]), next_pagination_token: request.pagination_token === null ? "same" : "same" });
          },
          async deleteAccountVectors(_request: PineconeAccountVectorDeleteRequest) {
            throw new Error("unused");
          },
        } as HeldPineconeAccountDeletionFence);
      },
    };
    const participant = createPineconeDeletionCleanupParticipant(fixture.registry, badFence, fixture.repository);
    await expect(participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest,
      (s) => s.scanOwned())).rejects.toMatchObject({ code: "scan_failed" });
  });

  test("rejects an empty page with a continuation token", async () => {
    const fixture = makeFixture();
    const badFence: PineconeAccountDeletionFence = {
      async withHeldAccountWriteFence(c, o, e, callback) {
        return callback({
          source_generation_digest: "c".repeat(64), fence_receipt_digest: "d".repeat(64),
          async scanAccountVectors(request: PineconeAccountVectorScanRequest) {
            return Object.freeze({ version: "pinecone-account-vector-scan-page-v1", role: request.role,
              namespace: request.namespace, account_id: request.account_id, limit: request.limit,
              pagination_token: request.pagination_token, vector_ids: Object.freeze([]), next_pagination_token: "more" });
          },
          async deleteAccountVectors(_request: PineconeAccountVectorDeleteRequest) {
            throw new Error("unused");
          },
        } as HeldPineconeAccountDeletionFence);
      },
    };
    const participant = createPineconeDeletionCleanupParticipant(fixture.registry, badFence, fixture.repository);
    await expect(participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest,
      (s) => s.scanOwned())).rejects.toMatchObject({ code: "scan_failed" });
  });


  test("maps arbitrary callback failures to a content-safe error and rejects forged registry", async () => {
    const fixture = makeFixture();
    const participant = createPineconeDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository);
    await expect(participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest,
      async () => { throw new Error("vector secret"); })).rejects.toBeInstanceOf(PineconeDeletionCleanupError);
    await expect(participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest,
      async () => { throw new Error("vector secret"); })).rejects.toMatchObject({ code: "callback_failed" });
    expect(() => createPineconeDeletionCleanupParticipant(
      { ...fixture.registry }, fixture.fence, fixture.repository,
    )).toThrow(PineconeDeletionCleanupError);
  });

  test("drains callback work and denies late ignored provider I/O after fence release", async () => {
    const fixture = makeFixture();
    let late: Promise<unknown> | undefined;
    const participant = createPineconeDeletionCleanupParticipant(fixture.registry, fixture.fence, fixture.repository);
    await participant.withHeldSurfaceFence(coordinate, operationRef, eligibilityDigest, async (session) => {
      late = new Promise((resolve, reject) => {
        setTimeout(() => {
          try {
            session.scanOwned().then(resolve, reject);
          } catch (error) {
            reject(error);
          }
        }, 0);
      });
      return "done";
    });
    await expect(late).rejects.toMatchObject({ code: "provider_fence_failed" });
    expect(fixture.deletes).toHaveLength(0);
  });
});
