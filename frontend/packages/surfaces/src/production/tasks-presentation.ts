import type { RefreshPhase } from "@omi-core/domain";

/**
 * Surface-level empty kinds for Tasks.
 *
 * True empty (`empty-projection`) is "the loaded snapshot has no tasks."
 * Filter miss (`filtered-out`) is "tasks exist, and the local query excluded
 * every one." Day-bucket emptiness inside a non-empty filtered set is not a
 * surface empty kind — that stays `lifecycle.empty` under each group heading.
 */
export type TasksEmptyKind = "empty-projection" | "filtered-out";

export function tasksEmptyKind(input: {
  phase: RefreshPhase;
  rowCount: number;
  visibleCount: number;
  filtering: boolean;
}): TasksEmptyKind | null {
  if (input.phase === "ready" && input.rowCount === 0) return "empty-projection";
  if (input.filtering && input.rowCount > 0 && input.visibleCount === 0) return "filtered-out";
  return null;
}
