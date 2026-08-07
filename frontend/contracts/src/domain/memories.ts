/**
 * Memories domain contract — second slice after tasks (WS-002), built by
 * copying the tasks contract's shape exactly (see `tasks.ts`).
 *
 * Field set is grounded in the real legacy backend at baseline `e0893286`
 * (`backend/routers/memories.py`, `backend/models/memories.py` via
 * `adapters-legacy` — reference only, never imported). `MemoryDB` there
 * carries far more (propositions, evidence, tiering, device scoping); this
 * contract keeps only what tasks.ts's own selection precedent justifies:
 * content, category, visibility, review state, timestamps, revision. The
 * canonical-memory proposition/evidence/tiering fields are a foundation gap,
 * not a decision made here — surfaced in the adapter file header, not
 * silently modeled.
 */

import type { RecordId } from "../ids.js";

export interface Memory {
  id: RecordId;
  content: string;
  /**
   * Legacy accepts an open string set and server-side maps old categories
   * onto a smaller primary set (`interesting` | `system` | `manual` |
   * `workflow`); kept as `string` here rather than a closed union so the
   * contract does not need to track that legacy mapping table.
   */
  category: string;
  visibility: "public" | "private";
  /** Server has resolved this memory through review (accept/reject/timeout). */
  reviewed: boolean;
  /** Tri-state: `null` = never reviewed by the user, else the user's verdict. */
  userReview: boolean | null;
  createdAt: number;
  updatedAt: number;
  /** Server revision of the last write we saw; reconcile compares these. */
  revision: string | null;
  /**
   * The server withheld this record's full content and sent a TRUNCATION in
   * `content` (legacy: locked memories are serialized as `content[:70] + '...'`
   * behind a paid-plan gate). `content` is therefore NOT the record when this
   * is true, and writing it back destroys the real content — so a locked
   * memory's content is never editable and `MemoryPatch.content` must never be
   * built from it. Server-owned: absent from `MemoryPatch` by construction.
   */
  locked: boolean;
}

/**
 * Fields a patch may touch. Absent key = unchanged, by construction.
 *
 * `category` is deliberately excluded: the legacy backend exposes no
 * endpoint to change a memory's category after creation (only content,
 * visibility, and review verdict have PATCH/POST equivalents) — see the
 * adapter file header for the full gap list.
 *
 * `locked` is excluded because it is server-owned (a paid-plan gate), and
 * because `content` on a locked record is a truncation rather than the record
 * — see `Memory.locked`. `MemoriesStore.patch` refuses a `content` patch on a
 * locked row for exactly that reason.
 */
export type MemoryPatch = Partial<Pick<Memory, "content" | "visibility" | "userReview">>;

/**
 * The universal write contract (ADR-004 D2 + ADR-005 shape): client-supplied
 * id on create (slug, per ADR-006), idempotent by opId on every operation.
 */
export type MemoryOp =
  | { op: "create"; opId: string; id: RecordId; at: number; content: string; category?: string; visibility?: "public" | "private" }
  | { op: "patch"; opId: string; id: RecordId; at: number; patch: MemoryPatch }
  | { op: "delete"; opId: string; id: RecordId; at: number };

/**
 * What a backend (real or legacy adapter) must expose for memories — the
 * ADR-004 D3 read side. `ids` MUST return a set version and be internally
 * consistent (red-team finding 9); deletion of local rows is permitted only
 * against a `complete: true` snapshot.
 */
/** Alias of the shared IdSnapshot (wave-1 ratchet) — use IdSnapshot in new code. */
export type MemoryIdSnapshot = import("../snapshot.js").IdSnapshot;
