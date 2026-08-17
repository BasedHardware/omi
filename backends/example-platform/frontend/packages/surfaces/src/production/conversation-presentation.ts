import type { RefreshPhase } from "@omi-core/domain";

/**
 * What Conversations may show when the URL names a detail id.
 *
 * Found rows beat phase: a hydrated conversation stays on screen while
 * refresh is still running. Missing rows are not "removed" until a ready
 * snapshot says so — loading and failed refreshes cannot know that.
 */
export type ConversationDetailKind = "none" | "detail" | "loading" | "not-found" | "unavailable";

export function conversationDetailKind(input: {
  phase: RefreshPhase;
  detailId: string | undefined;
  found: boolean;
}): ConversationDetailKind {
  if (!input.detailId) return "none";
  if (input.found) return "detail";
  switch (input.phase) {
    case "ready":
      return "not-found";
    case "initial-loading":
    case "refreshing":
      return "loading";
    case "unavailable":
    case "saved-but-refresh-failed":
      return "unavailable";
    default: {
      const _exhaustive: never = input.phase;
      throw new Error(`unhandled refresh phase: ${JSON.stringify(_exhaustive)}`);
    }
  }
}
