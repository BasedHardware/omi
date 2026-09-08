import { recoveredPayloadTextKeySql } from "./generation-prompt";

type StoredConversation = {
  id: number[];
  title: number[];
  overview: number[];
  createdAt: number;
  updatedAt: number;
  completed: number;
};

export const CONVERSATIONS_READ_CONTRACT_VERSION = "1.0.0" as const;
export const CONVERSATIONS_FRONTIER = "frontier-v1:conversations-declared";
export const MAIN_CONVERSATION_ID = "chat:chat-main";

/** Domain conversation as the worker projects it from D1 chat. */
export type ConversationProjection = {
  id: string;
  title: string;
  overview: string;
  createdAt: number;
  updatedAt: number;
  startedAt: number | null;
  capturedAtMs?: number;
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
  captured_at_ms?: number;
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
  // ponytail: summaries scale with conversation count; paginate in SQL for larger accounts.
  const result = await db
    .prepare(
      `WITH normalized AS (
         SELECT position, sender, created_at, generation_outcome, text,
           ${recoveredPayloadTextKeySql(
             "chat_messages",
             "chatSessionId"
           )} AS session_key
         FROM chat_messages WHERE account_id = ?
       ), sessions AS (
         SELECT position, sender, created_at, generation_outcome, text,
           CASE WHEN typeof(session_key) = 'text' AND length(CAST(session_key AS BLOB)) > 0
             THEN 'chat:' || session_key ELSE 'chat:chat-main' END AS session_id
         FROM normalized
       ), ranked AS (
         SELECT *,
           row_number() OVER (PARTITION BY session_id ORDER BY position) AS first_rank,
           row_number() OVER (PARTITION BY session_id ORDER BY position DESC) AS last_rank,
           row_number() OVER (PARTITION BY session_id ORDER BY sender = 'human' DESC, position) AS title_rank
         FROM sessions
       ), selected AS (
         SELECT *, trim(text, char(9,10,11,12,13,32,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288,65279)) AS display_text
         FROM ranked WHERE first_rank = 1 OR last_rank = 1 OR title_rank = 1
       )
       SELECT CAST(session_id AS BLOB) AS id,
         max(CASE WHEN title_rank = 1 THEN substr(CAST(display_text AS BLOB), 1, 964) END) AS title,
         max(CASE WHEN last_rank = 1 THEN substr(CAST(display_text AS BLOB), 1, 964) END) AS overview,
         max(CASE WHEN first_rank = 1 THEN created_at END) AS createdAt,
         max(CASE WHEN last_rank = 1 THEN created_at END) AS updatedAt,
         max(CASE WHEN last_rank = 1 THEN sender = 'ai' AND generation_outcome = 'completed' ELSE 0 END) AS completed
       FROM selected GROUP BY session_id`
    )
    .bind(accountId)
    .all<StoredConversation>();

  const conversations = result.results.map(projectConversation);
  const recordings = await db
    .prepare(
      "SELECT s.id, s.started_at, s.ended_at, s.captured_at_ms, t.state, substr(trim(t.text), 1, 241) AS text, t.updated_at FROM device_transcriptions t JOIN device_sessions s ON s.id = t.session_id AND s.account_id = t.account_id WHERE t.account_id = ? ORDER BY s.started_at DESC"
    )
    .bind(accountId)
    .all<{
      id: string;
      started_at: number;
      ended_at: number | null;
      captured_at_ms: number | null;
      state: string;
      text: string | null;
      updated_at: number;
    }>();
  for (const recording of recordings.results) {
    conversations.push({
      id: `recording:${recording.id}`,
      title: recording.text?.trim()
        ? displayText(recording.text).slice(0, 80)
        : "",
      overview: recording.text?.trim() ? displayText(recording.text) : "",
      createdAt: recording.started_at,
      updatedAt: recording.updated_at,
      startedAt: recording.started_at,
      ...(recording.captured_at_ms == null
        ? {}
        : { capturedAtMs: recording.captured_at_ms }),
      finishedAt: recording.ended_at,
      source: "omi",
      status:
        recording.state === "completed"
          ? "completed"
          : recording.state === "failed"
          ? "failed"
          : "processing",
      discarded: false,
      starred: false,
      visibility: "private",
      isLocked: false,
      folderId: null,
      revision: null,
    });
  }
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
    ...(item.capturedAtMs === undefined
      ? {}
      : { captured_at_ms: item.capturedAtMs }),
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

function projectConversation(row: StoredConversation): ConversationProjection {
  return {
    id: decodeSessionId(row.id),
    title: boundedDisplayText(row.title),
    overview: boundedDisplayText(row.overview),
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
    startedAt: row.createdAt,
    finishedAt: row.completed ? row.updatedAt : null,
    source: "chat",
    status: row.completed ? "completed" : "in_progress",
    discarded: false,
    starred: false,
    visibility: "private",
    isLocked: false,
    folderId: null,
    revision: null,
  };
}

function decodeSessionId(bytes: number[]): string {
  const input = new Uint8Array(bytes);
  const decoder = new TextDecoder("utf-8", { ignoreBOM: true });
  let result = "";
  let start = 0;
  for (let index = 0; index + 2 < input.length; index++) {
    const middle = input[index + 1]!;
    const last = input[index + 2]!;
    if (
      input[index] === 0xed &&
      middle >= 0xa0 &&
      middle <= 0xbf &&
      last >= 0x80 &&
      last <= 0xbf
    ) {
      result += decoder.decode(input.subarray(start, index));
      result += String.fromCharCode(
        0xd000 | ((middle & 0x3f) << 6) | (last & 0x3f)
      );
      index += 2;
      start = index + 1;
    }
  }
  return result + decoder.decode(input.subarray(start));
}

function boundedDisplayText(bytes: number[]): string {
  const text = new TextDecoder().decode(new Uint8Array(bytes), {
    stream: true,
  });
  return text.length > 240 ? `${text.slice(0, 237)}...` : text;
}

function displayText(text: string): string {
  const trimmed = text.trim();
  return trimmed.length > 240 ? `${trimmed.slice(0, 237)}...` : trimmed;
}

function iso(value: number): string {
  return new Date(value).toISOString();
}
