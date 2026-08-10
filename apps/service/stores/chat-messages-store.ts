// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

export type ChatMessageSender = "human" | "ai" | "unknown";
export type ChatMessageType = "text" | "day_summary" | "unknown";
export type WritableChatMessageSender = Exclude<ChatMessageSender, "unknown">;
export type WritableChatMessageType = Exclude<ChatMessageType, "unknown">;

/** Metadata survives admission even while attachment content support is disabled. */
export interface ChatAttachmentMetadata {
  readonly displayName: string;
  readonly mediaType: string;
  readonly size: number;
}

/** The canonical durable Chat record served by history. */
export interface ChatMessageRecord {
  readonly id: string;
  readonly text: string;
  readonly sender: ChatMessageSender;
  readonly type: ChatMessageType;
  readonly createdAt: number;
  readonly updatedAt: number;
  readonly chatSessionId: string | null;
  readonly appId: string | null;
  readonly journalRevision: number;
  readonly payloadHash: string;
  readonly messageSource: string;
  readonly rating: number | null;
  readonly reported: boolean;
  readonly revision: string | null;
  readonly attachments?: readonly ChatAttachmentMetadata[];
}

export interface StoredChatMessage {
  readonly message: ChatMessageRecord;
  readonly generationId: string | null;
}

export interface ChatHistoryKey {
  readonly createdAt: number;
  readonly id: string;
}

export interface ChatHistoryQuery {
  readonly limit: number;
  /** Inclusion snapshot allocated before the first page read. */
  readonly snapshotSequence: number;
  /** Strict older-than boundary. Null means the newest page. */
  readonly olderThan: ChatHistoryKey | null;
}

export interface ChatHistoryStorePage {
  readonly messages: readonly ChatMessageRecord[];
  readonly hasOlder: boolean;
}

export type ChatMessageAdmissionOutcome =
  | { readonly kind: "created"; readonly stored: StoredChatMessage }
  | { readonly kind: "replay"; readonly stored: StoredChatMessage }
  | { readonly kind: "conflict" };

export type CanonicalChatMessageWriteOutcome =
  | { readonly kind: "created" | "updated" | "replay"; readonly stored: StoredChatMessage }
  | { readonly kind: "conflict" }
  | { readonly kind: "invalid_vocabulary" };

export interface ChatMessagesStore {
  readMessage(accountId: string, messageId: string): StoredChatMessage | null;
  /** The insertion snapshot used to keep a whole cursor chain stable. */
  readSnapshotSequence(accountId: string): number;
  listHistory(accountId: string, query: ChatHistoryQuery): ChatHistoryStorePage;
  /** Client admission is human-only. Payload hash, not op id, owns replay identity. */
  admitHuman(
    accountId: string,
    message: ChatMessageRecord,
    generationId: string,
  ): ChatMessageAdmissionOutcome;
  /** Server-authored terminal/cancelled messages use this seam in the next lane. */
  writeCanonical(
    accountId: string,
    message: ChatMessageRecord,
    generationId: string | null,
  ): CanonicalChatMessageWriteOutcome;
  reset(): void;
}

export interface RestoredChatMessage {
  readonly accountId: string;
  readonly stored: StoredChatMessage;
}

const isNonNegativeSafeInteger = (value: number): boolean =>
  Number.isSafeInteger(value) && value >= 0;

const detachAttachments = (
  attachments: readonly ChatAttachmentMetadata[] | undefined,
): readonly ChatAttachmentMetadata[] | undefined => {
  if (attachments === undefined) return undefined;
  return Object.freeze(attachments.map((attachment) => {
    if (typeof attachment.displayName !== "string"
      || typeof attachment.mediaType !== "string"
      || !isNonNegativeSafeInteger(attachment.size)) {
      throw new TypeError("invalid chat attachment metadata");
    }
    return Object.freeze({
      displayName: attachment.displayName,
      mediaType: attachment.mediaType,
      size: attachment.size,
    });
  }));
};

export const detachChatMessage = (message: ChatMessageRecord): ChatMessageRecord => {
  if (typeof message.id !== "string" || message.id.length === 0
    || typeof message.text !== "string"
    || !["human", "ai", "unknown"].includes(message.sender)
    || !["text", "day_summary", "unknown"].includes(message.type)
    || !isNonNegativeSafeInteger(message.createdAt)
    || !isNonNegativeSafeInteger(message.updatedAt)
    || !(message.chatSessionId === null || typeof message.chatSessionId === "string")
    || !(message.appId === null || typeof message.appId === "string")
    || !isNonNegativeSafeInteger(message.journalRevision)
    || typeof message.payloadHash !== "string"
    || typeof message.messageSource !== "string"
    || !(message.rating === null || Number.isFinite(message.rating))
    || typeof message.reported !== "boolean"
    || !(message.revision === null || typeof message.revision === "string")) {
    throw new TypeError("invalid chat message record");
  }
  const attachments = detachAttachments(message.attachments);
  return Object.freeze({
    id: message.id,
    text: message.text,
    sender: message.sender,
    type: message.type,
    createdAt: message.createdAt,
    updatedAt: message.updatedAt,
    chatSessionId: message.chatSessionId,
    appId: message.appId,
    journalRevision: message.journalRevision,
    payloadHash: message.payloadHash,
    messageSource: message.messageSource,
    rating: message.rating,
    reported: message.reported,
    revision: message.revision,
    ...(attachments === undefined ? {} : { attachments }),
  });
};

const detachStored = (stored: StoredChatMessage): StoredChatMessage => Object.freeze({
  message: detachChatMessage(stored.message),
  generationId: stored.generationId,
});

export const compareChatHistoryKeys = (left: ChatHistoryKey, right: ChatHistoryKey): number =>
  left.createdAt < right.createdAt ? -1
    : left.createdAt > right.createdAt ? 1
      : left.id < right.id ? -1 : left.id > right.id ? 1 : 0;

const isWritableVocabulary = (message: ChatMessageRecord): boolean =>
  message.sender !== "unknown" && message.type !== "unknown";

interface InMemoryRow extends StoredChatMessage {
  readonly sequence: number;
}

/** Process-local adapter. Restored rows deliberately accept the read-tolerance sentinels. */
export const createInMemoryChatMessagesStore = (
  restored: readonly RestoredChatMessage[] = [],
): ChatMessagesStore => {
  const accounts = new Map<string, Map<string, InMemoryRow>>();
  const sequences = new Map<string, number>();

  const rowsOf = (accountId: string): Map<string, InMemoryRow> => {
    const present = accounts.get(accountId);
    if (present !== undefined) return present;
    const created = new Map<string, InMemoryRow>();
    accounts.set(accountId, created);
    return created;
  };

  for (const row of restored) {
    const sequence = (sequences.get(row.accountId) ?? 0) + 1;
    sequences.set(row.accountId, sequence);
    rowsOf(row.accountId).set(row.stored.message.id, Object.freeze({
      ...detachStored(row.stored),
      sequence,
    }));
  }

  const admit = (
    accountId: string,
    message: ChatMessageRecord,
    generationId: string | null,
  ): CanonicalChatMessageWriteOutcome => {
    const detached = detachChatMessage(message);
    if (!isWritableVocabulary(detached)) return { kind: "invalid_vocabulary" };
    const rows = rowsOf(accountId);
    const current = rows.get(detached.id);
    if (current !== undefined) {
      if (current.message.payloadHash !== detached.payloadHash) return { kind: "conflict" };
      if (detached.journalRevision <= current.message.journalRevision) {
        return { kind: "replay", stored: detachStored(current) };
      }
      const updated = Object.freeze({
        message: detached,
        generationId: current.generationId ?? generationId,
        sequence: current.sequence,
      });
      rows.set(detached.id, updated);
      return { kind: "updated", stored: detachStored(updated) };
    }
    const sequence = (sequences.get(accountId) ?? 0) + 1;
    sequences.set(accountId, sequence);
    const created = Object.freeze({ message: detached, generationId, sequence });
    rows.set(detached.id, created);
    return { kind: "created", stored: detachStored(created) };
  };

  return Object.freeze({
    readMessage(accountId: string, messageId: string): StoredChatMessage | null {
      const row = accounts.get(accountId)?.get(messageId);
      return row === undefined ? null : detachStored(row);
    },

    readSnapshotSequence(accountId: string): number {
      return sequences.get(accountId) ?? 0;
    },

    listHistory(accountId: string, query: ChatHistoryQuery): ChatHistoryStorePage {
      const rows = [...(accounts.get(accountId)?.values() ?? [])]
        .filter((row) => row.sequence <= query.snapshotSequence)
        .filter((row) => row.message.appId === null && row.message.chatSessionId === null)
        .filter((row) => query.olderThan === null || compareChatHistoryKeys(
          { createdAt: row.message.createdAt, id: row.message.id },
          query.olderThan,
        ) < 0)
        .sort((left, right) => compareChatHistoryKeys(
          { createdAt: right.message.createdAt, id: right.message.id },
          { createdAt: left.message.createdAt, id: left.message.id },
        ));
      const hasOlder = rows.length > query.limit;
      const selected = rows.slice(0, query.limit).reverse().map((row) => row.message);
      return Object.freeze({ messages: Object.freeze(selected), hasOlder });
    },

    admitHuman(
      accountId: string,
      message: ChatMessageRecord,
      generationId: string,
    ): ChatMessageAdmissionOutcome {
      if (message.sender !== "human") return { kind: "conflict" };
      const outcome = admit(accountId, message, generationId);
      if (outcome.kind === "invalid_vocabulary" || outcome.kind === "conflict") {
        return { kind: "conflict" };
      }
      return {
        kind: outcome.kind === "created" ? "created" : "replay",
        stored: outcome.stored,
      };
    },

    writeCanonical: admit,

    reset(): void {
      accounts.clear();
      sequences.clear();
    },
  });
};
