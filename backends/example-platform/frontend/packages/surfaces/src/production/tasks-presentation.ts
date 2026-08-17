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

/**
 * What Tasks' main region may show. Distinct from the lifecycle notice: the
 * notice can say "loading" while saved tasks stay on screen.
 *
 * `empty-projection` is only for a finished ready snapshot with zero rows.
 * A non-ready zero-row state is not emptiness, and a non-ready state that
 * already has rows is not a loading replacement for the list.
 */
export type TasksBodyKind = "loading" | "unavailable" | "empty-projection" | "filtered-out" | "rows";

export function tasksBodyKind(input: {
  phase: RefreshPhase;
  rowCount: number;
  visibleCount: number;
  filtering: boolean;
}): TasksBodyKind {
  if (input.filtering && input.rowCount > 0 && input.visibleCount === 0) return "filtered-out";
  if (input.rowCount > 0) return "rows";
  switch (input.phase) {
    case "ready":
      return "empty-projection";
    case "unavailable":
      return "unavailable";
    case "initial-loading":
    case "refreshing":
      return "loading";
    case "saved-but-refresh-failed":
      return "rows";
    default: {
      const _exhaustive: never = input.phase;
      throw new Error(`unhandled refresh phase: ${JSON.stringify(_exhaustive)}`);
    }
  }
}
