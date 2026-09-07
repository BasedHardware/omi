// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import {
  assertAuthorizedLedgerWriteContextCurrentAt,
  type AuthorizedLedgerWriteContext,
} from "../../apps/service/auth/authorized-context";
import type {
  ChatGenerationEvent,
  ChatGenerationFrame,
} from "../../apps/service/stores/chat-generation-events-store";
import {
  compareChatHistoryKeys,
  detachChatMessage,
  type ChatHistoryQuery,
  type ChatHistoryStorePage,
  type ChatMessageRecord,
  type StoredChatMessage,
} from "../../apps/service/stores/chat-messages-store";
import {
  MAIN_CHAT_CONVERSATION_ID,
  type ChatConversationSessionItem,
} from "../../apps/service/composition/chat-conversation-sessions";
import type { PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

export interface ChatReadStorage {
  readSnapshotSequence(): Promise<number>;
  listHistory(query: ChatHistoryQuery): Promise<ChatHistoryStorePage>;
  readMessage(messageId: string): Promise<StoredChatMessage | null>;
  listGenerationEvents(generationId: string): Promise<readonly ChatGenerationEvent[] | null>;
  listConversationSessions(): Promise<readonly ChatConversationSessionItem[]>;
}

const fail = (): never => {
  throw new PostgresRepositoryError("persistence_failed");
};

const integer = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) return value;
  if (typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value)) {
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
  }
  return null;
};

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;

const parseStored = (value: unknown): StoredChatMessage => {
  const row = record(value);
  if (row === null) return fail();
  const generationId = row.generationId;
  if (!(generationId === null || typeof generationId === "string")) return fail();
  let message: ChatMessageRecord;
  try {
    message = detachChatMessage({
      id: row.id as never,
      text: row.text as never,
      sender: row.sender as never,
      type: row.type as never,
      createdAt: row.createdAt as never,
      updatedAt: row.updatedAt as never,
      chatSessionId: row.chatSessionId as never,
      appId: row.appId as never,
      journalRevision: row.journalRevision as never,
      payloadHash: row.payloadHash as never,
      messageSource: row.messageSource as never,
      rating: row.rating as never,
      reported: row.reported as never,
      revision: row.revision as never,
      attachments: row.attachments as never,
    });
  } catch {
    return fail();
  }
  return Object.freeze({ message, generationId });
};

const parseFrame = (value: unknown): ChatGenerationFrame => {
  const frame = record(value);
  if (frame === null || typeof frame.kind !== "string" || frame.kind.length === 0) return fail();
  return frame as unknown as ChatGenerationFrame;
};

const parseEvent = (value: unknown): ChatGenerationEvent => {
  const row = record(value);
  if (row === null) return fail();
  const sequence = integer(row.sequence);
  const createdAt = integer(row.createdAt);
  if (typeof row.id !== "string" || row.id.length === 0
    || typeof row.generationId !== "string" || row.generationId.length === 0
    || sequence === null || sequence < 1 || createdAt === null) return fail();
  return Object.freeze({
    id: row.id,
    generationId: row.generationId,
    sequence,
    createdAt,
    frame: parseFrame(row.frame),
  });
};

const parseConversationSession = (value: unknown): ChatConversationSessionItem => {
  const row = record(value);
  const createdAt = integer(row?.createdAt);
  const updatedAt = integer(row?.updatedAt);
  const startedAt = integer(row?.startedAt);
  const finishedAt = row?.finishedAt === null ? null : integer(row?.finishedAt);
  if (row === null
    || row.id !== MAIN_CHAT_CONVERSATION_ID
    || typeof row.title !== "string" || row.title.length === 0 || row.title.length > 240
    || typeof row.overview !== "string" || row.overview.length === 0 || row.overview.length > 240
    || createdAt === null || updatedAt === null || startedAt === null
    || updatedAt < createdAt || startedAt !== createdAt
    || (finishedAt !== null && finishedAt < createdAt)
    || row.source !== "chat"
    || (row.status !== "completed" && row.status !== "in_progress")
    || row.discarded !== false || row.starred !== false
    || row.visibility !== "private" || row.isLocked !== false
    || row.folderId !== null || row.revision !== null) {
    return fail();
  }
  return Object.freeze({
    id: MAIN_CHAT_CONVERSATION_ID,
    title: row.title,
    overview: row.overview,
    createdAt,
    updatedAt,
    startedAt,
    finishedAt,
    source: "chat",
    status: row.status,
    discarded: false,
    starred: false,
    visibility: "private",
    isLocked: false,
    folderId: null,
    revision: null,
  });
};

const parseConversationSessions = (value: unknown): readonly ChatConversationSessionItem[] => {
  if (!Array.isArray(value) || value.length > 1) return fail();
  return Object.freeze(value.map(parseConversationSession));
};

const parseHistoryPage = (value: unknown): ChatHistoryStorePage => {
  const page = record(value);
  if (page === null || typeof page.hasOlder !== "boolean" || !Array.isArray(page.messages)) {
    return fail();
  }
  const stored = page.messages.map(parseStored);
  const messages = stored.map((row) => row.message).sort((left, right) => compareChatHistoryKeys(
    { createdAt: left.createdAt, id: left.id },
    { createdAt: right.createdAt, id: right.id },
  ));
  return Object.freeze({
    messages: Object.freeze(messages),
    hasOlder: page.hasOlder,
  });
};

export async function withAuthorizedChatRead<Result>(
  pool: PostgresTransactionPool,
  authority: AuthorizedLedgerWriteContext,
  signal: AbortSignal,
  project: (storage: ChatReadStorage) => Result | Promise<Result>,
): Promise<Result> {
  if (authority.capability !== "chat.read") {
    throw new PostgresRepositoryError("capability_denied");
  }
  signal.throwIfAborted();
  const boundedPool: PostgresTransactionPool = {
    withTransaction: (options, operation) =>
      pool.withTransaction({ ...options, signal }, operation),
  };
  return withAuthorizedSerializableConnectionTransaction(
    boundedPool,
    authority,
    async ({ connection, dbNowEpochSeconds }) => {
      const storage: ChatReadStorage = {
        async readSnapshotSequence() {
          const rows = await connection.query({
            name: "chat.read_snapshot",
            text: "SELECT omi_memory.read_chat_snapshot_sequence() AS sequence",
            values: [],
          });
          if (rows.length !== 1) return fail();
          const sequence = integer(rows[0]!.sequence);
          if (sequence === null) return fail();
          return sequence;
        },
        async listHistory(query: ChatHistoryQuery) {
          const rows = await connection.query({
            name: "chat.read_history",
            text: "SELECT omi_memory.read_chat_history($1,$2,$3,$4) AS page",
            values: [
              query.limit,
              query.snapshotSequence,
              query.olderThan?.createdAt ?? null,
              query.olderThan?.id ?? null,
            ],
          });
          if (rows.length !== 1) return fail();
          return parseHistoryPage(rows[0]!.page);
        },
        async readMessage(messageId: string) {
          const rows = await connection.query({
            name: "chat.read_message",
            text: "SELECT omi_memory.read_chat_message($1) AS message",
            values: [messageId],
          });
          if (rows.length !== 1) return fail();
          if (rows[0]!.message === null) return null;
          return parseStored(rows[0]!.message);
        },
        async listGenerationEvents(generationId: string) {
          const rows = await connection.query({
            name: "chat.read_generation_events",
            text: "SELECT omi_memory.read_chat_generation_events($1) AS events",
            values: [generationId],
          });
          if (rows.length !== 1) return fail();
          const events = rows[0]!.events;
          if (!Array.isArray(events)) return fail();
          return Object.freeze(events.map(parseEvent));
        },
        async listConversationSessions() {
          const rows = await connection.query({
            name: "chat.read_conversation_sessions",
            text: "SELECT omi_memory.read_chat_conversation_sessions() AS sessions",
            values: [],
          });
          if (rows.length !== 1) return fail();
          return parseConversationSessions(rows[0]!.sessions);
        },
      };
      const result = await project(storage);
      const clocks = await connection.query({
        name: "chat.final_clock",
        text: "SELECT floor(extract(epoch FROM clock_timestamp()))::bigint AS now",
        values: [],
      });
      const now = integer(clocks[0]?.now);
      if (clocks.length !== 1 || now === null) return fail();
      void dbNowEpochSeconds;
      signal.throwIfAborted();
      try {
        assertAuthorizedLedgerWriteContextCurrentAt(authority, now);
      } catch {
        throw new PostgresRepositoryError("expired_context");
      }
      return result;
    },
  );
}
