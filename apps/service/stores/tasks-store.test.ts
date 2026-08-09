/**
 * The server tasks store's invariants — the ones the write door and the tasks
 * read route BOTH depend on, which is why they are pinned here rather than in
 * either consumer.
 *
 * Every assertion below carries a red-proof that was applied to the real source
 * and observed red, then reverted. An assertion never seen red does not count.
 */

import { describe, expect, test } from "bun:test";

import { createInMemoryTasksStore, isStoreRevision } from "./tasks-store";

const ACCOUNT = "acct-store-fixture";
const OTHER_ACCOUNT = "acct-store-other";

describe("revisions", () => {
  /**
   * red-proof: truncate `nextRevision`'s digest to 8 hex.
   * APPLIED AND OBSERVED RED.
   */
  test("every applied revision is 64 lowercase hex, the ratified grammar", () => {
    const store = createInMemoryTasksStore();
    const created = store.apply(ACCOUNT, { op: "create", record_id: "task-1", content: { title: "a" } });
    expect(created.applied).toBe(true);
    if (!created.applied) return;
    expect(isStoreRevision(created.revision)).toBe(true);
  });

  /**
   * THE CHAIN PROPERTY, and the reason it is a chain and not a content digest.
   *
   * A -> B -> A must not return to A's first revision. Under a pure content
   * digest it would, and a `base_revision` taken at the first A would then be
   * satisfied at the second A — silently discarding the concurrent edit that
   * produced B, which is the lost-update blind spot the ratified contract says
   * `base_revision` exists to cover.
   *
   * red-proof: make `nextRevision` hash only `[recordId, content]` — drop the
   * previous link. APPLIED AND OBSERVED RED.
   */
  test("editing a record back to an earlier state does not reuse the earlier revision", () => {
    const store = createInMemoryTasksStore();
    const first = store.apply(ACCOUNT, { op: "create", record_id: "task-1", content: { done: false } });
    store.apply(ACCOUNT, { op: "patch", record_id: "task-1", patch: { done: true } });
    const back = store.apply(ACCOUNT, { op: "patch", record_id: "task-1", patch: { done: false } });

    expect(first.applied && back.applied).toBe(true);
    if (!first.applied || !back.applied) return;
    expect(store.readRecord(ACCOUNT, "task-1")?.content).toEqual({ done: false });
    expect(back.revision).not.toBe(first.revision);
  });

  /**
   * Hermetic: same envelopes, same revisions, on any machine and any run. A
   * clock or a random nonce in the revision would make a conformance corpus
   * unpinnable.
   *
   * red-proof: mix `Math.random()` into `nextRevision`'s input.
   * APPLIED AND OBSERVED RED.
   */
  test("the same sequence of ops produces the same revisions in a fresh store", () => {
    const run = () => {
      const store = createInMemoryTasksStore();
      store.apply(ACCOUNT, { op: "create", record_id: "task-1", content: { title: "a" } });
      return store.apply(ACCOUNT, { op: "patch", record_id: "task-1", patch: { title: "b" } });
    };
    const left = run();
    const right = run();
    expect(left).toEqual(right);
  });
});

describe("base_revision is a precondition, and it is the ONLY precondition", () => {
  /**
   * red-proof: in `preconditionHolds`, `return true` unconditionally.
   * APPLIED AND OBSERVED RED.
   */
  test("a patch whose base_revision does not match the record is a conflict", () => {
    const store = createInMemoryTasksStore();
    const created = store.apply(ACCOUNT, { op: "create", record_id: "task-1", content: { n: 1 } });
    expect(created.applied).toBe(true);
    if (!created.applied || created.revision === null) return;

    store.apply(ACCOUNT, { op: "patch", record_id: "task-1", patch: { n: 2 } });
    const stale = store.apply(ACCOUNT, {
      op: "patch", record_id: "task-1", patch: { n: 3 }, base_revision: created.revision,
    });
    expect(stale).toEqual({ applied: false, reason: "conflict" });
    // The record is untouched — a refused precondition applies nothing.
    expect(store.readRecord(ACCOUNT, "task-1")?.content).toEqual({ n: 2 });
  });

  /**
   * "As I last saw it" is false of a record that is not there. Answering
   * `applied` would let a delete-then-recreate race overwrite the recreation.
   *
   * red-proof: in `preconditionHolds`, treat `current === undefined` as
   * satisfied. APPLIED AND OBSERVED RED.
   */
  test("a base_revision against an absent record is a conflict, not an upsert", () => {
    const store = createInMemoryTasksStore();
    const outcome = store.apply(ACCOUNT, {
      op: "patch",
      record_id: "task-gone",
      patch: { n: 1 },
      base_revision: "0".repeat(64),
    });
    expect(outcome).toEqual({ applied: false, reason: "conflict" });
    expect(store.readRecord(ACCOUNT, "task-gone")).toBeNull();
  });

  /**
   * The ruled case, recorded so a future reader sees it was decided rather than
   * fallen into: a patch with NO precondition upserts. The alternative refusal
   * vocabulary the contract offers is `conflict`, whose documented meaning is a
   * failed `base_revision` — answering it to a request that carried none would
   * tell the client something false about its own op.
   */
  test("a patch with no base_revision against an absent record upserts", () => {
    const store = createInMemoryTasksStore();
    const outcome = store.apply(ACCOUNT, { op: "patch", record_id: "task-new", patch: { n: 1 } });
    expect(outcome.applied).toBe(true);
    expect(store.readRecord(ACCOUNT, "task-new")?.content).toEqual({ n: 1 });
  });
});

describe("deletes", () => {
  /**
   * The corpus pins this: "delete of an already-absent record is accepted with
   * a null revision". A deleted record has no current revision, and minting one
   * would hand a client a precondition token for something that is not there.
   *
   * red-proof: return the record's previous revision instead of null on delete.
   * APPLIED AND OBSERVED RED.
   */
  test("a delete answers a null revision and removes the record from the read side", () => {
    const store = createInMemoryTasksStore();
    store.apply(ACCOUNT, { op: "create", record_id: "task-1", content: { title: "a" } });
    const deleted = store.apply(ACCOUNT, { op: "delete", record_id: "task-1" });

    expect(deleted).toEqual({ applied: true, record_id: "task-1", revision: null });
    expect(store.readRecord(ACCOUNT, "task-1")).toBeNull();
    expect(store.listRecords(ACCOUNT)).toEqual([]);
  });

  /**
   * FOUND BY A DELEGATED PROBE, VERIFIED INDEPENDENTLY, AND IT WAS A REAL
   * DEFECT — the sharpest kind, because the module header claimed the opposite.
   *
   * The first version of `apply` dropped the record on delete, so a recreate
   * began a SECOND GENESIS and minted the original revision again. Two writes,
   * one revision. The chain's whole promise — that a revision names a point in
   * one record's history — was false across a delete.
   *
   * red-proof: remove the `buried.set(...)` block from the delete branch.
   * APPLIED AND OBSERVED RED.
   */
  test("recreating a deleted record with identical content does NOT reuse its old revision", () => {
    const store = createInMemoryTasksStore();
    const first = store.apply(ACCOUNT, { op: "create", record_id: "bounce", content: { title: "same" } });
    store.apply(ACCOUNT, { op: "delete", record_id: "bounce" });
    const again = store.apply(ACCOUNT, { op: "create", record_id: "bounce", content: { title: "same" } });

    expect(first.applied && again.applied).toBe(true);
    if (!first.applied || !again.applied) return;
    expect(again.revision).not.toBe(first.revision);
  });

  /**
   * THE CONSEQUENCE, and the reason the collision mattered rather than being a
   * curiosity: a `base_revision` captured before the delete satisfied a
   * precondition on the record that REPLACED it. A lost-update token from a
   * dead history authorised a write on a new one — exactly what `base_revision`
   * exists to prevent.
   *
   * red-proof: same mutation. APPLIED AND OBSERVED RED — the patch applied.
   */
  test("a base_revision from before a delete cannot authorise a write after the recreate", () => {
    const store = createInMemoryTasksStore();
    const created = store.apply(ACCOUNT, { op: "create", record_id: "ghost", content: { n: 1 } });
    expect(created.applied).toBe(true);
    if (!created.applied || created.revision === null) return;

    store.apply(ACCOUNT, { op: "delete", record_id: "ghost" });
    store.apply(ACCOUNT, { op: "create", record_id: "ghost", content: { n: 1 } });

    const stale = store.apply(ACCOUNT, {
      op: "patch", record_id: "ghost", patch: { n: 99 }, base_revision: created.revision,
    });
    expect(stale).toEqual({ applied: false, reason: "conflict" });
    expect(store.readRecord(ACCOUNT, "ghost")?.content).toEqual({ n: 1 });
  });

  test("deleting an absent record is accepted", () => {
    const store = createInMemoryTasksStore();
    expect(store.apply(ACCOUNT, { op: "delete", record_id: "task-0000" }))
      .toEqual({ applied: true, record_id: "task-0000", revision: null });
  });
});

describe("the read interface the tasks read route consumes", () => {
  /**
   * ACCOUNT ISOLATION. The read route pages over one account's records; a store
   * that leaked another account's row would publish it under a reader-scoped
   * opaque id and look entirely correct doing it.
   *
   * red-proof: in `listRecords`, ignore the account and merge every account's
   * map. APPLIED AND OBSERVED RED.
   */
  test("one account never sees another account's records", () => {
    const store = createInMemoryTasksStore();
    store.apply(ACCOUNT, { op: "create", record_id: "mine", content: {} });
    store.apply(OTHER_ACCOUNT, { op: "create", record_id: "theirs", content: {} });

    expect(store.listRecords(ACCOUNT).map((row) => row.record_id)).toEqual(["mine"]);
    expect(store.readRecord(ACCOUNT, "theirs")).toBeNull();
  });

  /**
   * A STABLE TOTAL ORDER is what a cursor pages over. If the order could move
   * under an unrelated edit, a cursor taken mid-page would skip or repeat rows
   * and the completeness envelope would be a true statement about a page that
   * lost a record.
   *
   * red-proof: in `apply`, set `first_seen_seq: sequence` unconditionally
   * rather than keeping the record's original. APPLIED AND OBSERVED RED.
   */
  test("editing a record does not move it in the read order", () => {
    const store = createInMemoryTasksStore();
    for (const id of ["a", "b", "c"]) store.apply(ACCOUNT, { op: "create", record_id: id, content: {} });
    store.apply(ACCOUNT, { op: "patch", record_id: "a", patch: { touched: true } });

    expect(store.listRecords(ACCOUNT).map((row) => row.record_id)).toEqual(["a", "b", "c"]);
  });

  /**
   * A consumer cannot mutate the store by holding what it read.
   *
   * red-proofs, both APPLIED AND OBSERVED RED: drop the `Object.freeze` around
   * the sorted copy, and return the sorted array without freezing it at all.
   */
  test("the returned page is frozen and detached from the store", () => {
    const store = createInMemoryTasksStore();
    store.apply(ACCOUNT, { op: "create", record_id: "a", content: {} });
    const page = store.listRecords(ACCOUNT);
    expect(Object.isFrozen(page)).toBe(true);
    expect(() => (page as { push: (row: unknown) => void }).push({})).toThrow();
    expect(store.listRecords(ACCOUNT)).toHaveLength(1);
  });

  /**
   * R6: field bags are opaque. The store must not add, rename or interpret a
   * field — everything the read route projects comes either from the bag or
   * from a store-owned fact, and nothing is invented in between.
   *
   * red-proof: have `apply` stamp an `updated_at` into the stored content.
   * APPLIED AND OBSERVED RED.
   */
  test("the stored content is exactly the field bag that arrived", () => {
    const store = createInMemoryTasksStore();
    const content = { title: "x", nested: { a: [1, 2] }, "weird key": null };
    store.apply(ACCOUNT, { op: "create", record_id: "a", content });
    expect(store.readRecord(ACCOUNT, "a")?.content).toEqual(content);
  });

  /**
   * A patch is a SHALLOW merge. Deep-merging would require deciding whether a
   * nested object is a value or a container, which is field semantics — and
   * those are unratified (R6).
   */
  test("a patch replaces a nested value rather than merging into it", () => {
    const store = createInMemoryTasksStore();
    store.apply(ACCOUNT, { op: "create", record_id: "a", content: { meta: { keep: 1, drop: 2 } } });
    store.apply(ACCOUNT, { op: "patch", record_id: "a", patch: { meta: { keep: 1 } } });
    expect(store.readRecord(ACCOUNT, "a")?.content).toEqual({ meta: { keep: 1 } });
  });
});
