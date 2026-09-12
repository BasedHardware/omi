import { chatHistoryIsUnprojectable } from "./chat";
import {
  parseStoredTranscriptSegments,
  projectDeviceTranscription,
  recordingListSpeech,
} from "./device-transcriptions";
import {
  recoveredPayloadTextKeySql,
  visibleGenerationTrim,
  visibleStoredTextTrimSql,
} from "./generation-prompt";

type StoredConversation = {
  id: number[];
  title: number[];
  overview: number[];
  createdAt: number;
  updatedAt: number;
};

export const CONVERSATIONS_READ_CONTRACT_VERSION = "1.0.0" as const;
export const CONVERSATIONS_FRONTIER = "frontier-v1:conversations-declared";
export const MAIN_CONVERSATION_ID = "chat:chat-main";

export class UnprojectableConversationRecordError extends Error {
  constructor() {
    super("unprojectable conversation record");
    this.name = "UnprojectableConversationRecordError";
  }
}

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
  if (await chatHistoryIsUnprojectable(db, accountId)) {
    throw new UnprojectableConversationRecordError();
  }
  // ponytail: summaries scale with conversation count; paginate in SQL for larger accounts.
  const result = await db
    .prepare(
      `WITH normalized AS (
         SELECT id AS message_id, position, sender, created_at, generation_outcome, text,
           ${recoveredPayloadTextKeySql(
             "chat_messages",
             "chatSessionId"
           )} AS session_key
         FROM chat_messages WHERE account_id = ?
           AND ${recoveredPayloadTextKeySql("chat_messages", "appId")} IS NULL
       ), sessions AS (
         SELECT message_id, position, sender, created_at, generation_outcome, text,
           CASE WHEN typeof(session_key) = 'text' AND length(CAST(session_key AS BLOB)) > 0
             THEN 'chat:' || session_key ELSE 'chat:chat-main' END AS session_id
         FROM normalized
       ), ranked AS (
         SELECT *,
           row_number() OVER (PARTITION BY session_id ORDER BY CASE WHEN sender = 'human' AND length(${visibleStoredTextTrimSql(
             "text"
           )}) > 0 THEN 0 WHEN sender = 'human' THEN 1 ELSE 2 END, created_at, message_id) AS title_rank,
           row_number() OVER (PARTITION BY session_id ORDER BY CASE WHEN length(${visibleStoredTextTrimSql(
             "text"
           )}) > 0 THEN 0 ELSE 1 END, created_at DESC, message_id DESC) AS overview_rank,
           min(created_at) OVER (PARTITION BY session_id) AS session_created_at,
           max(created_at) OVER (PARTITION BY session_id) AS session_updated_at
         FROM sessions
       ), selected AS (
         SELECT *, ${visibleStoredTextTrimSql("text")} AS display_text
         FROM ranked WHERE title_rank = 1 OR overview_rank = 1
       )
       SELECT CAST(session_id AS BLOB) AS id,
         max(CASE WHEN title_rank = 1 THEN substr(CAST(display_text AS BLOB), 1, 964) END) AS title,
         max(CASE WHEN overview_rank = 1 THEN substr(CAST(display_text AS BLOB), 1, 964) END) AS overview,
         max(session_created_at) AS createdAt,
         max(session_updated_at) AS updatedAt
       FROM selected GROUP BY session_id`
    )
    .bind(accountId)
    .all<StoredConversation>();

  const conversations = result.results.map(projectConversation);
  const recordings = await db
    .prepare(
      `SELECT s.id, s.started_at, s.ended_at, s.captured_at_ms, t.state, substr(${visibleStoredTextTrimSql(
        "t.text"
      )}, 1, 241) AS text, t.text AS stored_text, t.segments, t.language, t.discarded_leading_packets AS discardedLeadingPackets, t.error_code AS errorCode, t.updated_at FROM device_transcriptions t JOIN device_sessions s ON s.id = t.session_id AND s.account_id = t.account_id WHERE t.account_id = ? ORDER BY s.started_at DESC`
    )
    .bind(accountId)
    .all<{
      id: string;
      started_at: number;
      ended_at: number | null;
      captured_at_ms: number | null;
      state: string;
      text: string | null;
      stored_text: string | null;
      segments: string | null;
      language: string | null;
      discardedLeadingPackets: number;
      errorCode: string | null;
      updated_at: number;
    }>();
  for (const recording of recordings.results) {
    if (
      typeof recording.id !== "string" ||
      !/^[!-~]{1,256}$/.test(recording.id)
    ) {
      throw new UnprojectableConversationRecordError();
    }
    const parsed =
      recording.segments === null
        ? null
        : parseStoredTranscriptSegments(recording.segments);
    if (
      projectDeviceTranscription({
        sessionId: recording.id,
        state: recording.state,
        text: recording.stored_text,
        segments: recording.segments,
        language: recording.language,
        discardedLeadingPackets: recording.discardedLeadingPackets,
        errorCode: recording.errorCode,
        updatedAt: recording.updated_at,
      }) === null
    ) {
      throw new UnprojectableConversationRecordError();
    }
    const speech =
      recording.state === "completed"
        ? recordingListSpeech(recording.text, parsed) ?? ""
        : "";
    assertProjectableTimestamp(recording.started_at);
    assertProjectableTimestamp(recording.updated_at);
    if (recording.ended_at !== null)
      assertProjectableTimestamp(recording.ended_at);
    if (recording.captured_at_ms != null)
      assertProjectableTimestamp(recording.captured_at_ms);
    if (
      recording.ended_at !== null &&
      recording.ended_at < recording.started_at
    ) {
      throw new UnprojectableConversationRecordError();
    }
    if (recording.updated_at < recording.started_at) {
      throw new UnprojectableConversationRecordError();
    }
    conversations.push({
      id: `recording:${recording.id}`,
      title: recordingExcerpt(speech).slice(0, 80),
      overview: recordingExcerpt(speech),
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
    return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
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
    if (cursor.length < 1 || cursor.length > 1024) return "invalid_cursor";
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
  assertProjectableChatTimestamp(row.createdAt);
  assertProjectableChatTimestamp(row.updatedAt);
  const sessionId = decodeSessionId(row.id);
  if (
    !sessionId.startsWith("chat:") ||
    sessionId.length <= "chat:".length ||
    sessionId.slice("chat:".length).length > 128
  ) {
    throw new UnprojectableConversationRecordError();
  }
  return {
    id: sessionId,
    title: boundedDisplayText(row.title),
    overview: boundedDisplayText(row.overview),
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
    startedAt: row.createdAt,
    finishedAt: null,
    source: "chat",
    status: "in_progress",
    discarded: false,
    starred: false,
    visibility: "private",
    isLocked: false,
    folderId: null,
    revision: null,
  };
}

function assertProjectableChatTimestamp(value: number): void {
  if (
    !Number.isSafeInteger(value) ||
    value < 0 ||
    !Number.isFinite(new Date(value).getTime())
  ) {
    throw new UnprojectableConversationRecordError();
  }
}

function assertProjectableTimestamp(value: number): void {
  if (
    !Number.isSafeInteger(value) ||
    value < 0 ||
    !Number.isFinite(new Date(value).getTime())
  ) {
    throw new UnprojectableConversationRecordError();
  }
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
  const characters = Array.from(text);
  return characters.length > 240
    ? `${characters.slice(0, 237).join("")}...`
    : text;
}

function recordingExcerpt(text: string): string {
  return visibleGenerationTrim(text).slice(0, 240);
}

function iso(value: number): string {
  return new Date(value).toISOString();
}
