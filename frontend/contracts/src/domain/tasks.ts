/**
 * Tasks domain contract — the exemplar domain (WS-002).
 *
 * Field set mirrors the backend action-item record at baseline `e0893286`
 * (`backend/models/action_items` via `adapters-legacy`), including the five
 * fields the Reminders sync bug clobbers (issue draft 02) — our write
 * contract makes that class of bug inexpressible: edits are keyed patches,
 * and an absent key ALWAYS means "leave unchanged", never "reset to default".
 */

import type { RecordId } from "../ids.js";

export interface Task {
  id: RecordId;
  description: string;
  completed: boolean;
  completedAt: number | null;
  dueAt: number | null;
  owner: string | null;
  /** Where the task came from; `assistant` writes carry provenance. */
  source: string;
  provenance: readonly string[];
  sortOrder: number;
  indentLevel: number;
  createdAt: number;
  updatedAt: number;
  /** Server revision of the last write we saw; reconcile compares these. */
  revision: string | null;
}

/** Fields a patch may touch. Absent key = unchanged, by construction. */
export type TaskPatch = Partial<
  Pick<Task, "description" | "completed" | "completedAt" | "dueAt" | "owner" | "sortOrder" | "indentLevel">
>;

/**
 * The universal write contract (ADR-004 D2 + ADR-005 shape): client-supplied
 * id on create (slug, per ADR-006), idempotent by opId on every operation.
 */
export type TaskOp =
  | { op: "create"; opId: string; id: RecordId; at: number; description: string; dueAt?: number; source: string }
  | { op: "patch"; opId: string; id: RecordId; at: number; patch: TaskPatch }
  | { op: "delete"; opId: string; id: RecordId; at: number };

/**
 * What a backend (real or legacy adapter) must expose for tasks — the
 * ADR-004 D3 read side. `ids` MUST return a set version and be internally
 * consistent (red-team finding 9); deletion of local rows is permitted only
 * against a `complete: true` snapshot.
 */
/** Alias of the shared IdSnapshot (wave-1 ratchet) — use IdSnapshot in new code. */
export type TaskIdSnapshot = import("../snapshot.js").IdSnapshot;
