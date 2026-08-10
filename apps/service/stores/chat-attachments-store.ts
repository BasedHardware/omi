// domain-pending(DIV-CHAT-SESSION-001)

import type {
  ChatAttachmentContentPort,
  ChatGenerationAttachmentDescriptor,
} from "../chat/attachment-content";
import {
  CHAT_MAX_ATTACHMENT_BYTES,
  isAllowedChatAttachmentMimeType,
  type AllowedChatAttachmentMimeType,
} from "../chat/attachment-policy";
import type { ChatAttachmentMetadata } from "./chat-messages-store";

export type ChatAttachmentState = "staged" | "bound";

export interface ChatAttachmentRecord {
  readonly id: string;
  readonly contentReference: string | null;
  readonly accountId: string;
  readonly scope: string;
  readonly displayName: string;
  readonly mimeType: AllowedChatAttachmentMimeType;
  readonly sizeBytes: number;
  readonly state: ChatAttachmentState;
  readonly stagedAt: number;
  readonly stageExpiresAt: number;
  readonly boundMessageId: string | null;
  readonly boundAt: number | null;
  readonly contentExpiresAt: number | null;
  readonly content: Uint8Array | null;
}

export interface StageChatAttachmentInput {
  readonly id: string;
  readonly contentReference: string;
  readonly accountId: string;
  readonly scope: string;
  readonly displayName: string;
  readonly mimeType: AllowedChatAttachmentMimeType;
  readonly content: Uint8Array;
  readonly stagedAt: number;
  readonly stageExpiresAt: number;
}

export type ResolveChatAttachmentsOutcome =
  | { readonly kind: "ready"; readonly attachments: readonly ChatAttachmentMetadata[] }
  | { readonly kind: "not_found" };

export interface ResolveChatAttachmentsInput {
  readonly accountId: string;
  readonly scope: string;
  readonly attachmentIds: readonly string[];
  readonly messageId: string;
  readonly nowEpochMilliseconds: number;
}

export interface BindChatAttachmentsInput extends ResolveChatAttachmentsInput {
  readonly contentExpiresAt: number;
}

export interface ChatAttachmentsStore extends ChatAttachmentContentPort {
  stage(input: StageChatAttachmentInput): ChatAttachmentRecord;
  resolveForAdmission(input: ResolveChatAttachmentsInput): ResolveChatAttachmentsOutcome;
  bindToMessage(input: BindChatAttachmentsInput): ResolveChatAttachmentsOutcome;
  projectMessageAttachments(input: {
    readonly accountId: string;
    readonly messageId: string;
    readonly attachments: readonly ChatAttachmentMetadata[];
    readonly nowEpochMilliseconds: number;
  }): readonly ChatAttachmentMetadata[];
  reset(): void;
}

export interface InMemoryChatAttachmentsAccountSnapshot {
  readonly rows: readonly ChatAttachmentRecord[] | null;
}

export interface InMemoryChatAttachmentsStore extends ChatAttachmentsStore {
  snapshotAccount(accountId: string): InMemoryChatAttachmentsAccountSnapshot;
  restoreAccount(accountId: string, snapshot: InMemoryChatAttachmentsAccountSnapshot): void;
}

const detachBytes = (value: Uint8Array | null): Uint8Array | null =>
  value === null ? null : new Uint8Array(value);

const detachRecord = (record: ChatAttachmentRecord): ChatAttachmentRecord => Object.freeze({
  ...record,
  content: detachBytes(record.content),
});

const metadataOf = (record: ChatAttachmentRecord, now: number): ChatAttachmentMetadata =>
  Object.freeze({
    id: record.id,
    displayName: record.displayName,
    mediaType: record.mimeType,
    sizeBytes: record.sizeBytes,
    contentReference: record.state === "bound"
        && record.content !== null
        && record.contentReference !== null
        && record.contentExpiresAt !== null
        && now < record.contentExpiresAt
      ? record.contentReference
      : null,
  });

const canResolve = (
  record: ChatAttachmentRecord | undefined,
  input: ResolveChatAttachmentsInput,
): record is ChatAttachmentRecord => record !== undefined
  && record.accountId === input.accountId
  && record.scope === input.scope
  && (record.state === "bound"
    ? record.boundMessageId === input.messageId
    : input.nowEpochMilliseconds < record.stageExpiresAt);

export const createInMemoryChatAttachmentsStore = (): InMemoryChatAttachmentsStore => {
  const rows = new Map<string, ChatAttachmentRecord>();

  const expireContent = (accountId: string, messageId: string, now: number): void => {
    for (const [id, record] of rows) {
      if (record.accountId === accountId
        && record.boundMessageId === messageId
        && record.contentExpiresAt !== null
        && now >= record.contentExpiresAt
        && (record.content !== null || record.contentReference !== null)) {
        rows.set(id, detachRecord({ ...record, content: null, contentReference: null }));
      }
    }
  };

  const resolve = (input: ResolveChatAttachmentsInput): ResolveChatAttachmentsOutcome => {
    const resolved: ChatAttachmentRecord[] = [];
    for (const id of input.attachmentIds) {
      const record = rows.get(id);
      if (!canResolve(record, input)) return { kind: "not_found" };
      resolved.push(record);
    }
    return Object.freeze({
      kind: "ready" as const,
      attachments: Object.freeze(resolved.map((record) => metadataOf(
        record,
        input.nowEpochMilliseconds,
      ))),
    });
  };

  return Object.freeze({
    stage(input): ChatAttachmentRecord {
      if (input.id.length === 0 || input.contentReference.length === 0
        || input.displayName.length === 0 || !isAllowedChatAttachmentMimeType(input.mimeType)
        || input.content.byteLength === 0
        || input.content.byteLength > CHAT_MAX_ATTACHMENT_BYTES
        || !Number.isSafeInteger(input.stagedAt) || input.stagedAt < 0
        || input.stageExpiresAt <= input.stagedAt) {
        throw new TypeError("invalid staged chat attachment");
      }
      if (rows.has(input.id)) throw new TypeError("chat attachment id collision");
      if ([...rows.values()].some((row) => row.contentReference === input.contentReference)) {
        throw new TypeError("chat attachment content reference collision");
      }
      const record = detachRecord({
        id: input.id,
        contentReference: input.contentReference,
        accountId: input.accountId,
        scope: input.scope,
        displayName: input.displayName,
        mimeType: input.mimeType,
        sizeBytes: input.content.byteLength,
        state: "staged",
        stagedAt: input.stagedAt,
        stageExpiresAt: input.stageExpiresAt,
        boundMessageId: null,
        boundAt: null,
        contentExpiresAt: null,
        content: input.content,
      });
      rows.set(record.id, record);
      return detachRecord(record);
    },

    resolveForAdmission: resolve,

    bindToMessage(input): ResolveChatAttachmentsOutcome {
      const ready = resolve(input);
      if (ready.kind === "not_found") return ready;
      for (const id of input.attachmentIds) {
        const record = rows.get(id)!;
        if (record.state === "staged") {
          rows.set(id, detachRecord({
            ...record,
            state: "bound",
            boundMessageId: input.messageId,
            boundAt: input.nowEpochMilliseconds,
            contentExpiresAt: input.contentExpiresAt,
          }));
        }
      }
      return {
        kind: "ready",
        attachments: Object.freeze(input.attachmentIds.map((id) =>
          metadataOf(rows.get(id)!, input.nowEpochMilliseconds))),
      };
    },

    projectMessageAttachments(input): readonly ChatAttachmentMetadata[] {
      expireContent(input.accountId, input.messageId, input.nowEpochMilliseconds);
      return Object.freeze(input.attachments.map((metadata) => {
        const record = rows.get(metadata.id);
        return record !== undefined
            && record.accountId === input.accountId
            && record.boundMessageId === input.messageId
          ? metadataOf(record, input.nowEpochMilliseconds)
          : Object.freeze({ ...metadata, contentReference: null });
      }));
    },

    loadForGeneration(input): readonly ChatGenerationAttachmentDescriptor[] {
      expireContent(input.accountId, input.messageId, input.nowEpochMilliseconds);
      return Object.freeze(input.attachments.map((metadata) => {
        const record = rows.get(metadata.id);
        const owned = record !== undefined
          && record.accountId === input.accountId
          && record.boundMessageId === input.messageId;
        const projected = owned
          ? metadataOf(record, input.nowEpochMilliseconds)
          : Object.freeze({ ...metadata, contentReference: null });
        return Object.freeze({
          ...projected,
          content: owned ? detachBytes(record.content) : null,
        });
      }));
    },

    snapshotAccount(accountId): InMemoryChatAttachmentsAccountSnapshot {
      const selected = [...rows.values()].filter((row) => row.accountId === accountId);
      return Object.freeze({
        rows: selected.length === 0 ? null : Object.freeze(selected.map(detachRecord)),
      });
    },

    restoreAccount(accountId, snapshot): void {
      for (const [id, row] of rows) if (row.accountId === accountId) rows.delete(id);
      for (const row of snapshot.rows ?? []) rows.set(row.id, detachRecord(row));
    },

    reset(): void {
      rows.clear();
    },
  });
};
