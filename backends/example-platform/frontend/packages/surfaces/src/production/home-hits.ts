/**
 * Home's search hits — the fields this surface can honestly render.
 *
 * Mapped at the Home boundary from whichever generation the host selected.
 * Synthesized memories are a different record class from legacy `Memory`
 * (`text`, no `content`/`category`/`updatedAt`). Conversations are
 * field-identical across generations except `id` branding. This module copies
 * the fields Home uses and nothing else; it does not invent timestamps,
 * categories, completeness, or lock state.
 *
 * Self-contained so `node --test` can execute it directly.
 */

export type HomeMemoryCopy = "legacy" | "synthesized";

export type HomeMemoryHit = {
  readonly id: string;
  /** The one presentation field. Legacy `content` or synthesized `text`. */
  readonly text: string;
  /**
   * Legacy memories carry `updatedAt`. Synthesized memories do not: the
   * ratified projection has no timestamp, and Home must not invent one.
   */
  readonly timestamp: number | null;
  /** Which presenter produced this hit — not a server field. */
  readonly copy: HomeMemoryCopy;
};

export type HomeConversationHit = {
  readonly id: string;
  readonly title: string;
  readonly overview: string;
  readonly timestamp: number;
};

export function homeMemoryHitFromLegacy(memory: {
  readonly id: string;
  readonly content: string;
  readonly updatedAt: number;
}): HomeMemoryHit {
  return {
    id: memory.id,
    text: memory.content,
    timestamp: memory.updatedAt,
    copy: "legacy",
  };
}

export function homeMemoryHitFromSynthesized(item: {
  readonly id: string;
  readonly text: string;
}): HomeMemoryHit {
  return {
    id: item.id,
    text: item.text,
    timestamp: null,
    copy: "synthesized",
  };
}

export function homeConversationHitFromRecord(conversation: {
  readonly id: string;
  readonly title: string;
  readonly overview: string;
  readonly createdAt: number;
  readonly updatedAt: number;
  readonly startedAt: number | null;
}): HomeConversationHit {
  return {
    id: conversation.id,
    title: conversation.title,
    overview: conversation.overview,
    timestamp: conversation.startedAt ?? conversation.updatedAt ?? conversation.createdAt,
  };
}

/**
 * Dated rows newest-first; rows with no honest timestamp sort after dated
 * ones and keep their relative (server) order via a stable sort.
 */
export function compareHomeSpineTimestamps(left: number | null, right: number | null): number {
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  return right - left;
}
