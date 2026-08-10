// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import type { Database } from "bun:sqlite";

import {
  compareChatHistoryKeys,
  detachChatMessage,
  type CanonicalChatMessageWriteOutcome,
  type ChatAttachmentMetadata,
  type ChatHistoryQuery,
  type ChatHistoryStorePage,
  type ChatMessageAdmissionOutcome,
  type ChatMessageRecord,
  type ChatMessagesStore,
  type ChatMessageSender,
  type ChatMessageType,
  type StoredChatMessage,
} from "../../../apps/service/stores/chat-messages-store";
import { configureServiceStoreConnection } from "./connection";

interface StoredRow {
  readonly id: string;
  readonly text: string;
  readonly sender: ChatMessageSender;
  readonly message_type: ChatMessageType;
  readonly created_at: number;
  readonly updated_at: number;
  readonly chat_session_id: string | null;
  readonly app_id: string | null;
  readonly journal_revision: number;
  readonly payload_hash: string;
  readonly message_source: string;
  readonly rating: number | null;
  readonly reported: number;
  readonly server_revision: string | null;
  readonly attachments_json: string | null;
  readonly generation_id: string | null;
}

const SELECT_FIELDS = `
  id, text, sender, message_type, created_at, updated_at, chat_session_id,
  app_id, journal_revision, payload_hash, message_source, rating, reported,
  server_revision, attachments_json, generation_id
`;

const attachmentsFromJson = (value: string | null): readonly ChatAttachmentMetadata[] | undefined => {
  if (value === null) return undefined;
  const parsed = JSON.parse(value) as unknown;
  if (!Array.isArray(parsed)) throw new TypeError("invalid stored chat attachment metadata");
  return parsed as unknown as readonly ChatAttachmentMetadata[];
};

const storedFromRow = (row: StoredRow): StoredChatMessage => Object.freeze({
  message: detachChatMessage({
    id: row.id,
    text: row.text,
    sender: row.sender,
    type: row.message_type,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    chatSessionId: row.chat_session_id,
    appId: row.app_id,
    journalRevision: row.journal_revision,
    payloadHash: row.payload_hash,
    messageSource: row.message_source,
    rating: row.rating,
    reported: row.reported === 1,
    revision: row.server_revision,
    ...(row.attachments_json === null
      ? {}
      : { attachments: attachmentsFromJson(row.attachments_json) }),
  }),
  generationId: row.generation_id,
});

const attachmentsJson = (message: ChatMessageRecord): string | null =>
  message.attachments === undefined ? null : JSON.stringify(message.attachments);

/** SQLite adapter for canonical Chat records and insertion-snapshot history. */
export class SqliteChatMessagesStore implements ChatMessagesStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_chat_messages (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        id TEXT NOT NULL,
        text TEXT NOT NULL,
        sender TEXT NOT NULL CHECK (sender IN ('human', 'ai', 'unknown')),
        message_type TEXT NOT NULL CHECK (message_type IN ('text', 'day_summary', 'unknown')),
        created_at INTEGER NOT NULL CHECK (created_at >= 0),
        updated_at INTEGER NOT NULL CHECK (updated_at >= 0),
        chat_session_id TEXT,
        app_id TEXT,
        journal_revision INTEGER NOT NULL CHECK (journal_revision >= 0),
        payload_hash TEXT NOT NULL,
        message_source TEXT NOT NULL,
        rating REAL,
        reported INTEGER NOT NULL CHECK (reported IN (0, 1)),
        server_revision TEXT,
        attachments_json TEXT,
        generation_id TEXT,
        UNIQUE (account_id, id)
      );
      CREATE INDEX IF NOT EXISTS service_chat_messages_history
        ON service_chat_messages (
          account_id, app_id, chat_session_id, created_at DESC, id DESC, sequence
        );
    `);
  }

  readMessage(accountId: string, messageId: string): StoredChatMessage | null {
    const row = this.db.query(`
      SELECT ${SELECT_FIELDS}
      FROM service_chat_messages
      WHERE account_id = ? AND id = ?
    `).get(accountId, messageId) as StoredRow | null;
    return row === null ? null : storedFromRow(row);
  }

  readHumanByGeneration(accountId: string, generationId: string): StoredChatMessage | null {
    const row = this.db.query(`
      SELECT ${SELECT_FIELDS}
      FROM service_chat_messages
      WHERE account_id = ? AND generation_id = ? AND sender = 'human'
      ORDER BY sequence ASC
      LIMIT 1
    `).get(accountId, generationId) as StoredRow | null;
    return row === null ? null : storedFromRow(row);
  }

  readSnapshotSequence(accountId: string): number {
    const row = this.db.query(`
      SELECT COALESCE(MAX(sequence), 0) AS sequence
      FROM service_chat_messages
      WHERE account_id = ?
    `).get(accountId) as { readonly sequence: number };
    return row.sequence;
  }

  listHistory(accountId: string, query: ChatHistoryQuery): ChatHistoryStorePage {
    const rows = query.olderThan === null
      ? this.db.query(`
          SELECT ${SELECT_FIELDS}
          FROM service_chat_messages
          WHERE account_id = ? AND app_id IS NULL AND chat_session_id IS NULL
            AND sequence <= ?
          ORDER BY created_at DESC, id DESC
          LIMIT ?
        `).all(accountId, query.snapshotSequence, query.limit + 1) as StoredRow[]
      : this.db.query(`
          SELECT ${SELECT_FIELDS}
          FROM service_chat_messages
          WHERE account_id = ? AND app_id IS NULL AND chat_session_id IS NULL
            AND sequence <= ?
            AND (created_at < ? OR (created_at = ? AND id < ?))
          ORDER BY created_at DESC, id DESC
          LIMIT ?
        `).all(
          accountId,
          query.snapshotSequence,
          query.olderThan.createdAt,
          query.olderThan.createdAt,
          query.olderThan.id,
          query.limit + 1,
        ) as StoredRow[];
    const hasOlder = rows.length > query.limit;
    const messages = rows.slice(0, query.limit).map(storedFromRow).map((row) => row.message);
    messages.sort((left, right) => compareChatHistoryKeys(
      { createdAt: left.createdAt, id: left.id },
      { createdAt: right.createdAt, id: right.id },
    ));
    return Object.freeze({ messages: Object.freeze(messages), hasOlder });
  }

  admitHuman(
    accountId: string,
    message: ChatMessageRecord,
    generationId: string,
  ): ChatMessageAdmissionOutcome {
    if (message.sender !== "human" || message.type === "unknown") return { kind: "conflict" };
    const outcome = this.write(accountId, message, generationId);
    if (outcome.kind === "conflict" || outcome.kind === "invalid_vocabulary") {
      return { kind: "conflict" };
    }
    return {
      kind: outcome.kind === "created" ? "created" : "replay",
      stored: outcome.stored,
    };
  }

  writeCanonical(
    accountId: string,
    message: ChatMessageRecord,
    generationId: string | null,
  ): CanonicalChatMessageWriteOutcome {
    return this.write(accountId, message, generationId);
  }

  reset(): void {
    const reset = this.db.transaction(() => {
      this.db.exec("DELETE FROM service_chat_messages;");
      this.db.query("DELETE FROM sqlite_sequence WHERE name = ?").run("service_chat_messages");
    });
    reset.immediate();
  }

  private write(
    accountId: string,
    message: ChatMessageRecord,
    generationId: string | null,
  ): CanonicalChatMessageWriteOutcome {
    const detached = detachChatMessage(message);
    if (detached.sender === "unknown" || detached.type === "unknown") {
      return { kind: "invalid_vocabulary" };
    }
    const inserted = this.db.query(`
      INSERT INTO service_chat_messages (
        account_id, id, text, sender, message_type, created_at, updated_at,
        chat_session_id, app_id, journal_revision, payload_hash, message_source,
        rating, reported, server_revision, attachments_json, generation_id
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT (account_id, id) DO NOTHING
    `).run(
      accountId,
      detached.id,
      detached.text,
      detached.sender,
      detached.type,
      detached.createdAt,
      detached.updatedAt,
      detached.chatSessionId,
      detached.appId,
      detached.journalRevision,
      detached.payloadHash,
      detached.messageSource,
      detached.rating,
      detached.reported ? 1 : 0,
      detached.revision,
      attachmentsJson(detached),
      generationId,
    );
    if (inserted.changes === 1) {
      return { kind: "created", stored: this.readMessage(accountId, detached.id)! };
    }
    const current = this.readMessage(accountId, detached.id)!;
    if (current.message.payloadHash !== detached.payloadHash) return { kind: "conflict" };
    if (detached.journalRevision <= current.message.journalRevision) {
      return { kind: "replay", stored: current };
    }
    this.db.query(`
      UPDATE service_chat_messages SET
        text = ?, sender = ?, message_type = ?, created_at = ?, updated_at = ?,
        chat_session_id = ?, app_id = ?, journal_revision = ?, message_source = ?,
        rating = ?, reported = ?, server_revision = ?, attachments_json = ?,
        generation_id = COALESCE(generation_id, ?)
      WHERE account_id = ? AND id = ? AND payload_hash = ? AND journal_revision < ?
    `).run(
      detached.text,
      detached.sender,
      detached.type,
      detached.createdAt,
      detached.updatedAt,
      detached.chatSessionId,
      detached.appId,
      detached.journalRevision,
      detached.messageSource,
      detached.rating,
      detached.reported ? 1 : 0,
      detached.revision,
      attachmentsJson(detached),
      generationId,
      accountId,
      detached.id,
      detached.payloadHash,
      detached.journalRevision,
    );
    return { kind: "updated", stored: this.readMessage(accountId, detached.id)! };
  }
}
