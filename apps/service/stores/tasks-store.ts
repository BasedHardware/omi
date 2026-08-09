/**
 * THE SERVER TASKS STORE — one module, two interfaces, one owner.
 *
 * `POST /v1/tasks/ops` applies into it; the tasks read route serves out of it.
 * Two implementations of this would be the two-doors defect on the night's
 * largest new surface, which is why R11 gives it a single owner (OPS) and makes
 * the read side a read-only consumer rather than a second builder.
 *
 * ── WHAT THIS MODULE REFUSES TO KNOW: TASK FIELD SEMANTICS (R6) ──────────────
 *
 * 0.5.0 is deliberately domain-generic. `create.content` and `patch.patch` are
 * OPAQUE FIELD BAGS, and no ruling exists on task field vocabulary. So this
 * store holds the bag and never reads inside it: it does not know what `title`
 * means, it does not mint `createdAt`, and it has no clock. Everything it
 * exposes is a fact it owns — the record id the envelope named, the revision it
 * computed, and the order in which it first saw each record.
 *
 * This is a real constraint on the read side, stated here rather than
 * discovered there: any field of the ratified tasks read model that is not a
 * store-owned fact must come out of the opaque bag, because inventing one here
 * would be this module ruling on field meaning. When the tasks field vocabulary
 * ratifies, the projection of bag -> named fields is the change, and it happens
 * in the read composition, not here.
 *
 * ── REVISIONS ARE A HASH CHAIN, NOT A CONTENT DIGEST ─────────────────────────
 *
 * `revision_n = sha256(canonical([revision_{n-1}, record_id, content_n]))`.
 *
 * A pure content digest would give two different histories the same revision
 * whenever a record was edited back to an earlier state, and `base_revision` is
 * a LOST-UPDATE precondition: "the record is as I last saw it". Under a content
 * digest, A -> B -> A would satisfy a precondition taken at the first A, and the
 * concurrent edit that produced B would be silently overwritten — exactly the
 * blind spot the ratified contract says `base_revision` exists to cover. The
 * chain makes each applied write a distinct point in the record's history.
 *
 * It is also hermetic: no clock, no randomness, no I/O. The same sequence of
 * envelopes produces the same revisions on every machine, which is what lets a
 * conformance corpus pin them at all.
 *
 * **A DELETE DOES NOT RESET THE CHAIN, and the first version of this module got
 * that wrong.** A probe deleted a record and recreated it with identical
 * content, and the recreate minted the ORIGINAL revision — because `delete`
 * dropped the record, so the recreate began a second genesis. The consequence
 * is the exact failure `base_revision` exists to prevent: a token captured
 * before the delete then satisfied a precondition on the record that replaced
 * it, and a patch written against a dead history was applied to a new one. So
 * a delete leaves a TOMBSTONE carrying the last revision, and the next write to
 * that id links to it. The record's identity is its `record_id`, and its
 * history does not restart just because it was empty for a while.
 *
 * ── WHAT THIS IS NOT ─────────────────────────────────────────────────────────
 *
 * Durable. It is in-memory, said plainly, for the same reason
 * `control/projection-store.ts` is: the durable store is `WS-003`/`ADR-009`'s
 * and there is no adapter for it in this repo. Writing one to host a schema
 * that is itself the thing under test would be inventing a data plane. What an
 * in-memory store does buy is real — apply, precondition, ordering and replay
 * semantics exercised across a real process over real HTTP.
 */

import { createHash } from "node:crypto";

/** 64 lowercase hex, matching the ratified contract's `REVISION_PATTERN`. */
const STORE_REVISION_PATTERN = /^[0-9a-f]{64}$/;

/** The genesis link of a record's revision chain. Never a valid revision. */
const NO_PRIOR_REVISION = null;

/**
 * One stored record.
 *
 * `first_seen_seq` is a STORE-OWNED ordering fact, not a timestamp and not a
 * task field: it is the order in which this store first admitted the record.
 * The read side needs a total order to page over and this is the only one this
 * module is entitled to state.
 */
export interface TasksRecord {
  readonly record_id: string;
  readonly revision: string;
  /** The opaque field bag, exactly as it arrived. Never interpreted here. */
  readonly content: Readonly<Record<string, unknown>>;
  readonly first_seen_seq: number;
  readonly last_applied_seq: number;
}

/**
 * THE READ INTERFACE — the tasks read route's only view of this store.
 *
 * Narrow on purpose. It exposes no mutation, no cross-account listing, and no
 * internal map: a read consumer cannot reach a record of an account it was not
 * asked about, because there is no method that would let it.
 */
export interface TasksReadStore {
  /**
   * Every live record of one account, in a stable total order
   * (`first_seen_seq` ascending, `record_id` as the tiebreak that cannot
   * happen but must still be pinned). Deleted records are absent.
   *
   * Returns a fresh frozen array: a consumer cannot mutate the store by
   * holding onto what it read.
   */
  listRecords(accountId: string): readonly TasksRecord[];
  /** One record, or `null` when this account has no live record by that id. */
  readRecord(accountId: string, recordId: string): TasksRecord | null;
}

/** The outcome of applying one op. Never a thrown exception. */
export type TasksApplyOutcome =
  | { readonly applied: true; readonly record_id: string; readonly revision: string | null }
  /** `base_revision` was supplied and does not match the record's current revision. */
  | { readonly applied: false; readonly reason: "conflict" };

/** A single op, in the shape the ratified envelope carries it. */
export type TasksWriteOp =
  | { readonly op: "create"; readonly record_id: string; readonly content: Readonly<Record<string, unknown>> }
  | { readonly op: "patch"; readonly record_id: string; readonly patch: Readonly<Record<string, unknown>>; readonly base_revision?: string }
  | { readonly op: "delete"; readonly record_id: string; readonly base_revision?: string };

export interface TasksStore extends TasksReadStore {
  /**
   * Applies one op for one account. The account id comes from the
   * authenticated principal at the call site and never from the envelope —
   * `backend:ADR-012` §4 — and this module cannot check that for its caller,
   * so the route is where that discipline is asserted.
   */
  apply(accountId: string, op: TasksWriteOp): TasksApplyOutcome;
  /** Drops every record of every account. Test and QA-reset support only. */
  reset(): void;
}

/**
 * Canonical bytes for hashing: the compact `JSON.stringify` encoding, with
 * object key order preserved — the same definition the ratified contract's
 * `parseCanonicalJson` enforces on the request body. Reusing that definition
 * rather than sorting keys keeps one notion of "the canonical bytes of this
 * op" in the system instead of two that agree until they do not.
 */
const canonicalBytes = (value: unknown): string => JSON.stringify(value);

const nextRevision = (
  previous: string | null,
  recordId: string,
  content: Readonly<Record<string, unknown>>,
): string =>
  createHash("sha256")
    .update(canonicalBytes([previous, recordId, content]), "utf8")
    .digest("hex");

/**
 * `base_revision` semantics, in one place so the three ops cannot disagree:
 *
 * - absent  -> no precondition, always satisfied;
 * - present, record live, revisions equal -> satisfied;
 * - present, record live, revisions differ -> CONFLICT (a genuine concurrent edit);
 * - present, record absent -> CONFLICT. "As I last saw it" is false of a record
 *   that is not there, and answering "applied" would let a delete-then-recreate
 *   race silently overwrite the recreation.
 */
const preconditionHolds = (current: TasksRecord | undefined, baseRevision: string | undefined): boolean => {
  if (baseRevision === undefined) return true;
  return current !== undefined && current.revision === baseRevision;
};

/** What a deleted record leaves behind, so its history can be continued. */
interface TasksTombstone {
  readonly revision: string;
  readonly first_seen_seq: number;
}

export const createInMemoryTasksStore = (): TasksStore => {
  /** account id -> record id -> record. */
  const accounts = new Map<string, Map<string, TasksRecord>>();
  /**
   * account id -> record id -> the chain link a delete left behind.
   *
   * Bounded by the number of distinct record ids an account has ever deleted,
   * which is the price of the property: a record id's history is continuous
   * across deletion, so no revision is ever minted twice for one id and no
   * precondition token outlives the history it was taken from.
   */
  const graves = new Map<string, Map<string, TasksTombstone>>();
  let sequence = 0;

  const recordsOf = (accountId: string): Map<string, TasksRecord> => {
    const existing = accounts.get(accountId);
    if (existing !== undefined) return existing;
    const created = new Map<string, TasksRecord>();
    accounts.set(accountId, created);
    return created;
  };

  const gravesOf = (accountId: string): Map<string, TasksTombstone> => {
    const existing = graves.get(accountId);
    if (existing !== undefined) return existing;
    const created = new Map<string, TasksTombstone>();
    graves.set(accountId, created);
    return created;
  };

  return Object.freeze({
    listRecords(accountId: string): readonly TasksRecord[] {
      const records = accounts.get(accountId);
      if (records === undefined) return Object.freeze([]);
      return Object.freeze(
        [...records.values()].sort((left, right) =>
          left.first_seen_seq !== right.first_seen_seq
            ? left.first_seen_seq - right.first_seen_seq
            : left.record_id < right.record_id ? -1 : left.record_id > right.record_id ? 1 : 0),
      );
    },

    readRecord(accountId: string, recordId: string): TasksRecord | null {
      return accounts.get(accountId)?.get(recordId) ?? null;
    },

    apply(accountId: string, op: TasksWriteOp): TasksApplyOutcome {
      const records = recordsOf(accountId);
      const buried = gravesOf(accountId);
      const current = records.get(op.record_id);
      // The chain link for the next write to this id: the live record's
      // revision, or — if it was deleted — the one its tombstone kept.
      const priorRevision = current?.revision ?? buried.get(op.record_id)?.revision ?? NO_PRIOR_REVISION;
      const priorSeq = current?.first_seen_seq ?? buried.get(op.record_id)?.first_seen_seq;

      if (op.op === "delete") {
        if (!preconditionHolds(current, op.base_revision)) return { applied: false, reason: "conflict" };
        if (current !== undefined) {
          buried.set(op.record_id, {
            revision: current.revision,
            first_seen_seq: current.first_seen_seq,
          });
        }
        records.delete(op.record_id);
        // A deleted record has no current revision, and inventing one would
        // hand a client a precondition token for something that is not there.
        return { applied: true, record_id: op.record_id, revision: null };
      }

      sequence += 1;

      if (op.op === "create") {
        // A create carries no precondition — there is nothing to be a revision
        // OF, and the contract's own validator refuses `base_revision` here.
        // A create over a live record therefore REPLACES its content and
        // continues its chain rather than forking a second history for one id.
        const revision = nextRevision(priorRevision, op.record_id, op.content);
        records.set(op.record_id, {
          record_id: op.record_id,
          revision,
          content: op.content,
          first_seen_seq: priorSeq ?? sequence,
          last_applied_seq: sequence,
        });
        return { applied: true, record_id: op.record_id, revision };
      }

      // A PATCH OF AN ABSENT RECORD, with no `base_revision`, UPSERTS. Ruled
      // here rather than improvised, with the blast radius stated: it is this
      // branch plus a corpus case, and no wire byte moves either way.
      //
      // The alternative is refusing it, and the refusal vocabulary the ratified
      // contract offers is `conflict`, whose own documentation is "`base_revision`
      // precondition failed: a genuine concurrent edit". Answering that to a
      // request that carried NO precondition would tell a client something
      // false about its own op, which is the failure class this program exists
      // to eliminate. A client that wants "only if it exists" has a ratified way
      // to say so — send `base_revision` — and that path does refuse.
      if (!preconditionHolds(current, op.base_revision)) return { applied: false, reason: "conflict" };

      // A patch is a SHALLOW MERGE over the opaque bag. Shallow is the only
      // merge this module is entitled to: a deep merge would have to decide
      // what a nested object MEANS — whether it is a value or a container —
      // and that is field semantics, which R6 says are unratified. A client
      // that needs to replace a nested value sends the whole value.
      const merged: Record<string, unknown> = { ...(current?.content ?? {}), ...op.patch };
      const revision = nextRevision(priorRevision, op.record_id, merged);
      records.set(op.record_id, {
        record_id: op.record_id,
        revision,
        content: merged,
        first_seen_seq: priorSeq ?? sequence,
        last_applied_seq: sequence,
      });
      return { applied: true, record_id: op.record_id, revision };
    },

    reset(): void {
      accounts.clear();
      graves.clear();
      sequence = 0;
    },
  });
};

/** Exported for the route's own assertion that it never emits a bad revision. */
export const isStoreRevision = (value: unknown): value is string =>
  typeof value === "string" && STORE_REVISION_PATTERN.test(value);
