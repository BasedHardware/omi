/**
 * Folders domain contract — third slice after tasks/memories (WS-002), built by
 * copying the tasks contract's shape exactly (see `tasks.ts`).
 *
 * Field set is grounded in the real legacy backend at baseline `e0893286`
 * (`backend/routers/folders.py`, `backend/models/folder.py` via
 * `adapters-legacy` — reference only, never imported). `Folder` there also
 * carries `category_mapping` and `conversation_count`; this contract omits
 * them deliberately:
 * - `category_mapping` is a backwards-compatibility hook mapping legacy
 *   `CategoryEnum` values onto system folders — not part of the new write/read
 *   contract; system folders are identified by `isSystem` / `isDefault`.
 * - `conversation_count` is a server-computed denormalized rollup maintained by
 *   folder membership mutations (owned by the conversations domain, not here);
 *   including it would invite stale reads and reconcile churn without a defined
 *   invalidation contract.
 *
 * `isSystem` and `isDefault` are included: the UI and delete policy need them
 * (system folders return 400 on delete), and they are stable record metadata.
 */

import type { RecordId } from "../ids.js";

export interface Folder {
  id: RecordId;
  name: string;
  /** Natural-language instruction for AI folder assignment; `null` = unset. */
  description: string | null;
  color: string;
  icon: string;
  createdAt: number;
  updatedAt: number;
  order: number;
  /** True for the user's default target folder (usually "Other"). */
  isDefault: boolean;
  /** True for server-created category-based folders that cannot be deleted. */
  isSystem: boolean;
  /** Server revision of the last write we saw; reconcile compares these. */
  revision: string | null;
}

/**
 * Fields a patch may touch. Absent key = unchanged, by construction.
 *
 * `description` may be set to `null` to clear; omitted means leave as-is.
 * The legacy `PATCH` handler uses `exclude_unset=True`, so explicit
 * `description: null` on the wire clears while an absent key does not — our
 * keyed patch mirrors that. (Omitted vs null is indistinguishable in
 * `UpdateFolderRequest`'s Pydantic defaults alone; the wire distinction is
 * what matters and is expressible.)
 */
export type FolderPatch = Partial<Pick<Folder, "name" | "color" | "icon" | "order">> & {
  description?: string | null;
};

/**
 * The universal write contract (ADR-004 D2 + ADR-005 shape): client-supplied
 * id on create (slug, per ADR-006), idempotent by opId on every operation.
 */
export type FolderOp =
  | {
      op: "create";
      opId: string;
      id: RecordId;
      at: number;
      name: string;
      description?: string;
      color?: string;
      icon?: string;
    }
  | { op: "patch"; opId: string; id: RecordId; at: number; patch: FolderPatch }
  | { op: "delete"; opId: string; id: RecordId; at: number; moveToFolderId?: RecordId };

/**
 * What a backend (real or legacy adapter) must expose for folders — the
 * ADR-004 D3 read side. `ids` MUST return a set version and be internally
 * consistent (red-team finding 9); deletion of local rows is permitted only
 * against a `complete: true` snapshot.
 */
export interface FolderIdSnapshot {
  setVersion: string;
  complete: boolean;
  ids: readonly string[];
}
