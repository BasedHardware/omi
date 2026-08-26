import type { ChatMessage } from "./wire";

type StoredMessage = {
  id: string;
  text: string;
  sender: "human" | "ai";
  createdAt: number;
  generationOutcome: "completed" | "cancelled" | null;
  position: number;
  payload: string | null;
};

export const CONVERSATIONS_READ_CONTRACT_VERSION = "1.0.0" as const;
export const CONVERSATIONS_FRONTIER = "frontier-v1:conversations-declared";
export const MAIN_CONVERSATION_ID = "chat-main";

/** Domain conversation as the worker projects it from D1 chat. */
export type ConversationProjection = {
  id: string;
  title: string;
  overview: string;
  createdAt: number;
  updatedAt: number;
  startedAt: number | null;
  finishedAt: number | null;
  source: string;
  status: string;
  discarded: boolean;
  starred: boolean;
  visibility: "public" | "private" | "shared";
  isLocked: boolean;
  folderId: string | null;
  revision: string | null;
};

/** Legacy list record the desktop client already parses. */
export type LegacyConversationRecord = {
  id: string;
  structured: { title: string; overview: string };
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  source: string;
  status: string;
  discarded: boolean;
  starred: boolean;
  visibility: "public" | "private" | "shared";
  is_locked: boolean;
  folder_id: string | null;
};

export type ConversationPage = {
  contractVersion: typeof CONVERSATIONS_READ_CONTRACT_VERSION;
  items: ConversationProjection[];
  window: {
    status: "complete" | "more";
    complete: boolean;
    hasMore: boolean;
    nextCursor: string | null;
  };
  completeness: {
    version: "conversations-completeness-v1";
    status: "complete";
    reasons: readonly [];
    frontiers: {
      declaredFrontier: typeof CONVERSATIONS_FRONTIER;
      newestAppliedFrontier: typeof CONVERSATIONS_FRONTIER;
      missingAppliedFrontierReason: null;
    };
  };
  absence: { kind: "query_gap" } | null;
};

export async function readConversations(
  db: D1Database,
  accountId: string
): Promise<ConversationProjection[]> {
  const result = await db
    .prepare(
      `SELECT id, text, sender, created_at AS createdAt, generation_outcome AS generationOutcome, position, payload
       FROM chat_messages
       WHERE account_id = ?
       ORDER BY position ASC`
    )
    .bind(accountId)
    .all<StoredMessage>();

  const groups = new Map<string, StoredMessage[]>();
  for (const row of result.results) {
    const sessionId = sessionIdOf(row);
    const rows = groups.get(sessionId);
    if (rows === undefined) groups.set(sessionId, [row]);
    else rows.push(row);
  }

  const conversations = [...groups.entries()].map(([id, rows]) =>
    projectConversation(id, rows)
  );
  conversations.sort((left, right) => {
    if (right.updatedAt !== left.updatedAt)
      return right.updatedAt - left.updatedAt;
    return left.id.localeCompare(right.id);
  });
  return conversations;
}

export function paginateConversations(
  items: ConversationProjection[],
  limit: number,
  cursor: string | undefined
): ConversationPage | "invalid_cursor" {
  let start = 0;
  if (cursor !== undefined) {
    if (!/^[\x21-\x7e]{1,1024}$/.test(cursor)) return "invalid_cursor";
    const index = items.findIndex((item) => item.id === cursor);
    if (index === -1) return "invalid_cursor";
    start = index + 1;
  }
  const pageRows = items.slice(start, start + limit);
  const hasMore = start + pageRows.length < items.length;
  const nextCursor =
    hasMore && pageRows[pageRows.length - 1] !== undefined
      ? pageRows[pageRows.length - 1]!.id
      : null;
  return conversationPage(pageRows, hasMore, nextCursor);
}

export function conversationPage(
  items: ConversationProjection[],
  hasMore: boolean,
  nextCursor: string | null
): ConversationPage {
  return {
    contractVersion: CONVERSATIONS_READ_CONTRACT_VERSION,
    items,
    window: {
      status: hasMore ? "more" : "complete",
      complete: !hasMore,
      hasMore,
      nextCursor,
    },
    completeness: {
      version: "conversations-completeness-v1",
      status: "complete",
      reasons: [],
      frontiers: {
        declaredFrontier: CONVERSATIONS_FRONTIER,
        newestAppliedFrontier: CONVERSATIONS_FRONTIER,
        missingAppliedFrontierReason: null,
      },
    },
    absence: items.length === 0 ? { kind: "query_gap" } : null,
  };
}

export function toLegacyConversation(
  item: ConversationProjection
): LegacyConversationRecord {
  return {
    id: item.id,
    structured: { title: item.title, overview: item.overview },
    created_at: iso(item.createdAt),
    updated_at: iso(item.updatedAt),
    started_at: item.startedAt === null ? null : iso(item.startedAt),
    finished_at: item.finishedAt === null ? null : iso(item.finishedAt),
    source: item.source,
    status: item.status,
    discarded: item.discarded,
    starred: item.starred,
    visibility: item.visibility,
    is_locked: item.isLocked,
    folder_id: item.folderId,
  };
}

function sessionIdOf(row: StoredMessage): string {
  if (row.payload === null) return MAIN_CONVERSATION_ID;
  try {
    const payload = JSON.parse(row.payload) as Partial<ChatMessage>;
    return typeof payload.chatSessionId === "string" &&
      payload.chatSessionId.length > 0
      ? payload.chatSessionId
      : MAIN_CONVERSATION_ID;
  } catch {
    return MAIN_CONVERSATION_ID;
  }
}

function projectConversation(
  id: string,
  rows: StoredMessage[]
): ConversationProjection {
  const first = rows[0]!;
  const last = rows[rows.length - 1]!;
  const titleSource = rows.find((row) => row.sender === "human") ?? first;
  const completed =
    last.sender === "ai" && last.generationOutcome === "completed";
  return {
    id,
    title: displayText(titleSource.text),
    overview: displayText(last.text),
    createdAt: first.createdAt,
    updatedAt: last.createdAt,
    startedAt: first.createdAt,
    finishedAt: completed ? last.createdAt : null,
    source: "chat",
    status: completed ? "completed" : "in_progress",
    discarded: false,
    starred: false,
    visibility: "private",
    isLocked: false,
    folderId: null,
    revision: null,
  };
}

function displayText(text: string): string {
  const trimmed = text.trim();
  if (trimmed.length === 0) return "Chat";
  return trimmed.length > 240 ? `${trimmed.slice(0, 237)}...` : trimmed;
}

function iso(value: number): string {
  return new Date(value).toISOString();
}
