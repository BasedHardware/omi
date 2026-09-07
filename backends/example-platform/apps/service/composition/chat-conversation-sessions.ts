export const MAIN_CHAT_CONVERSATION_ID = "chat:chat-main";

export type ChatConversationSessionItem = {
  readonly id: string;
  readonly title: string;
  readonly overview: string;
  readonly createdAt: number;
  readonly updatedAt: number;
  readonly startedAt: number;
  readonly finishedAt: number | null;
  readonly source: "chat";
  readonly status: "completed" | "in_progress";
  readonly discarded: false;
  readonly starred: false;
  readonly visibility: "private";
  readonly isLocked: false;
  readonly folderId: null;
  readonly revision: null;
};

export type ConversationEnvelopePage = {
  readonly contractVersion: unknown;
  readonly items: readonly Record<string, unknown>[];
  readonly window: unknown;
  readonly completeness: unknown;
  readonly absence: { readonly kind: "query_gap" } | null;
};

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;

const compareItems = (
  left: Record<string, unknown>,
  right: Record<string, unknown>,
): number => {
  const leftUpdated = left.updatedAt;
  const rightUpdated = right.updatedAt;
  if (typeof leftUpdated === "number" && typeof rightUpdated === "number"
    && leftUpdated !== rightUpdated) {
    return rightUpdated - leftUpdated;
  }
  const leftId = typeof left.id === "string" ? left.id : "";
  const rightId = typeof right.id === "string" ? right.id : "";
  return leftId < rightId ? -1 : leftId > rightId ? 1 : 0;
};

export const composeChatSessionsIntoConversationPage = (
  page: unknown,
  sessions: readonly ChatConversationSessionItem[],
): ConversationEnvelopePage | null => {
  const envelope = record(page);
  if (envelope === null || !Array.isArray(envelope.items) || sessions.length === 0) {
    return null;
  }
  const items: Record<string, unknown>[] = [];
  const sessionIds = new Set<string>(sessions.map((session) => session.id));
  for (const item of envelope.items) {
    const row = record(item);
    if (row === null || typeof row.id !== "string" || typeof row.updatedAt !== "number") {
      return null;
    }
    if (!sessionIds.has(row.id)) items.push(row);
  }
  items.push(...sessions);
  items.sort(compareItems);
  return Object.freeze({
    contractVersion: envelope.contractVersion,
    items: Object.freeze(items),
    window: envelope.window,
    completeness: envelope.completeness,
    absence: items.length === 0 ? { kind: "query_gap" } : null,
  });
};
