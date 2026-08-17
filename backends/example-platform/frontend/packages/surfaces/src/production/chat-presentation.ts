import type { RefreshPhase } from "@omi-core/domain";

/**
 * What Chat's main region may show. Distinct from the lifecycle notice: the
 * notice can say "loading" while saved messages stay on screen.
 *
 * `empty-projection` is only for a finished ready snapshot with zero rows.
 * A non-ready zero-row state is not emptiness, and a non-ready state that
 * already has rows is not a loading replacement for the thread.
 */
export type ChatBodyKind = "loading" | "unavailable" | "empty-projection" | "thread";

export function chatBodyKind(phase: RefreshPhase, messageCount: number): ChatBodyKind {
  if (messageCount > 0) return "thread";
  switch (phase) {
    case "ready":
      return "empty-projection";
    case "unavailable":
    case "saved-but-refresh-failed":
      return "unavailable";
    case "initial-loading":
    case "refreshing":
      return "loading";
    default: {
      const _exhaustive: never = phase;
      throw new Error(`unhandled refresh phase: ${JSON.stringify(_exhaustive)}`);
    }
  }
}
