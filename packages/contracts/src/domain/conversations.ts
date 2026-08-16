/**
 * Conversations domain contract — third slice after tasks/memories (WS-002),
 * built by copying the memories contract's shape (see `memories.ts`).
 *
 * Field set is grounded in the real legacy backend at baseline `e0893286`
 * (`backend/routers/conversations.py`, `backend/models/conversation.py`,
 * `backend/models/conversation_enums.py`, `backend/models/structured.py`,
 * and the folder-move endpoint in `backend/routers/folders.py` — reference
 * only, never imported). The `Conversation` model there is enormous
 * (transcript segments, photos, audio files, apps_results, plugins_results,
 * geolocation, external_data, post-processing, calendar links, …). This
 * contract keeps only what the tasks/memories selection precedent justifies
 * for a sync-layer list-and-mutate slice: identity, structured title/overview
 * (those live under `structured`, not at the top level), lifecycle timestamps,
 * source/status, discard/star/visibility/lock, folder membership, revision.
 * The omitted clusters are a foundation gap, not a decision made here —
 * surfaced in the adapter file header, not silently modeled.
 *
 * FOUNDATION GAP — no `create` variant: the legacy "create conversation"
 * HTTP entry is `process_in_progress_conversation`, a transcription/
 * processing pipeline that requires a pre-existing in-progress server
 * record. It is not an idempotent client-id create (ADR-004 D2 / ADR-006).
 * Conversations are server-originated. Emitting a `create` op the adapter
 * cannot implement would be dishonest; inventing a parallel write shape is
 * an architect decision. `ConversationOp` is therefore patch | delete only
 * until the rewrite (or an ADR amendment) can express server-originated
 * records. (Raw route strings live only in `adapters-legacy` — rule 3.)
 */

import type { RecordId } from "../ids.js";

export interface Conversation {
  id: RecordId;
  /** From wire `structured.title` — never a top-level field on the legacy model. */
  title: string;
  /** From wire `structured.overview` — never a top-level field on the legacy model. */
  overview: string;
  createdAt: number;
  updatedAt: number;
  startedAt: number | null;
  finishedAt: number | null;
  /**
   * Legacy `ConversationSource` is a large open set with a `_missing_` →
   * `unknown` fallback; kept as `string` rather than a closed union so the
   * contract does not need to track that enum table.
   */
  source: string;
  /**
   * Legacy `ConversationStatus` (`in_progress` | `processing` | `merging` |
   * `completed` | `failed`); kept as `string` for the same reason as `source`.
   */
  status: string;
  discarded: boolean;
  starred: boolean;
  visibility: "public" | "private" | "shared";
  isLocked: boolean;
  /** Present on the response model (`folder_id`); `null` = unfiled. */
  folderId: string | null;
  /**
   * Server revision of the last write we saw; reconcile compares these.
   * The legacy model documents `updated_at` as "the canonical server revision
   * clients use for cache reconciliation" — but tasks/memories currently leave
   * `revision: null` and inventing a conversations-only revision convention
   * would be a parallel pattern. Kept `null` here until an architect ratchets
   * the revision convention across domains; `updatedAt` still carries the
   * milliseconds value of that field for display/ordering.
   */
  revision: string | null;
}

/**
 * Fields a patch may touch. Absent key = unchanged, by construction.
 *
 * `overview` is deliberately excluded: the legacy router exposes
 * `PATCH .../title` (query) but no overview-update endpoint (the
 * `UpdateConversation` model exists, but no route consumes it for overview;
 * `PATCH .../summary` writes `apps_results`, not `structured.overview`).
 * `source`, `status`, `discarded`, and `isLocked` likewise have no sync-slice
 * mutation endpoints — see the adapter file header.
 */
export type ConversationPatch = Partial<Pick<Conversation, "title" | "starred" | "visibility" | "folderId">>;

/**
 * Write contract (ADR-004 D2 + ADR-005 shape), minus create — see file header.
 * Idempotent by opId on every operation that exists.
 */
export type ConversationOp =
  | { op: "patch"; opId: string; id: RecordId; at: number; patch: ConversationPatch }
  | { op: "delete"; opId: string; id: RecordId; at: number };

/**
 * What a backend (real or legacy adapter) must expose for conversations — the
 * ADR-004 D3 read side. `ids` MUST return a set version and be internally
 * consistent (red-team finding 9); deletion of local rows is permitted only
 * against a `complete: true` snapshot.
 *
 * FOUNDATION GAP: structurally identical to `TaskIdSnapshot` / `MemoryIdSnapshot`.
 * `Projection.reconcile` is typed against `TaskIdSnapshot` today. Do not unify
 * here — that is an architect-level ratchet.
 */
/** Alias of the shared IdSnapshot (wave-1 ratchet) — use IdSnapshot in new code. */
export type ConversationIdSnapshot = import("../snapshot.js").IdSnapshot;
