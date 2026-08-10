import type { RefreshPhase } from "@omi-core/domain";

/**
 * Shared empty kinds for list surfaces that already distinguish true-empty
 * copy from filter-miss copy (Memories, Conversations). Matches the worked
 * example's `empty-projection` / `filtered-out` vocabulary.
 *
 * Non-ready zero-row states return null so the refresh notice is not paired
 * with a lying `common.noResults` empty region.
 */
export type ListEmptyKind = "empty-projection" | "filtered-out";

export function listEmptyKind(input: {
  phase: RefreshPhase;
  rowCount: number;
  visibleCount: number;
}): ListEmptyKind | null {
  if (input.phase === "ready" && input.rowCount === 0) return "empty-projection";
  if (input.rowCount > 0 && input.visibleCount === 0) return "filtered-out";
  return null;
}
