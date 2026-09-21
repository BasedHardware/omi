// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-ATTACH-001)

import {
  assertAuthorizedLedgerWriteContextCurrentAt,
  type AuthorizedLedgerWriteContext,
} from "../../apps/service/auth/authorized-context";
import {
  ATTACHMENT_CONTENT_RETENTION_MS,
  CHAT_MAX_ATTACHMENT_BYTES,
  isAllowedChatAttachmentMimeType,
} from "../../apps/service/chat/attachment-policy";
import {
  advanceAttachmentScan,
  attachmentScanAdmissible,
  beginAttachmentScan,
  DEV_NOOP_SCANNER_ID,
  type AttachmentScanClock,
} from "../../apps/service/chat/attachment-scanner";
import type {
  BindChatAttachmentsInput,
  ChatAttachmentRecord,
  ChatAttachmentState,
  ResolveChatAttachmentsInput,
  ResolveChatAttachmentsOutcome,
  StageChatAttachmentInput,
} from "../../apps/service/stores/chat-attachments-store";
import type { ChatAttachmentMetadata } from "../../apps/service/stores/chat-messages-store";
import type { PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
} from "./transaction";

/** Unmounted chat.write attachment rows. Scanner is `dev-noop-scanner` only;
 *  this is not a malware guarantee and does not expose generation content. */
export interface ChatAttachmentStorage {
  stage(input: StageChatAttachmentInput): Promise<ChatAttachmentRecord>;
  advanceScan(id: string, clock: AttachmentScanClock): Promise<ChatAttachmentRecord | null>;
  retryScan(id: string, clock: AttachmentScanClock): Promise<ChatAttachmentRecord | null>;
  bindToMessage(input: BindChatAttachmentsInput): Promise<ResolveChatAttachmentsOutcome>;
  resolveForAdmission(input: ResolveChatAttachmentsInput): Promise<ResolveChatAttachmentsOutcome>;
  removeUnbound(id: string, accountId: string): Promise<boolean>;
  projectMessageAttachments(input: {
    readonly accountId: string;
    readonly messageId: string;
    readonly attachments: readonly ChatAttachmentMetadata[];
    readonly nowEpochMilliseconds: number;
  }): Promise<readonly ChatAttachmentMetadata[]>;
}

const fail = (): never => {
  throw new PostgresRepositoryError("persistence_failed");
};

const integer = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) return value;
  if (typeof value === "bigint" && value >= 0n && value <= BigInt(Number.MAX_SAFE_INTEGER)) {
    return Number(value);
  }
  if (typeof value === "string" && /^(0|[1-9][0-9]*)$/.test(value)) {
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
  }
  return null;
};

const STATES = new Set<ChatAttachmentState>([
  "staged", "scanning", "clean", "rejected", "timed_out", "error", "bound",
]);

const bytesOf = (value: unknown): Uint8Array | null => {
  if (value === null) return null;
  if (value instanceof Uint8Array) return new Uint8Array(value);
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  return fail();
};

const parseRow = (row: Record<string, unknown>): ChatAttachmentRecord => {
  const sizeBytes = integer(row.size_bytes);
  const stagedAt = integer(row.staged_at);
  const stageExpiresAt = integer(row.stage_expires_at);
  const scanningStartedAt = row.scanning_started_at === null ? null : integer(row.scanning_started_at);
  const boundAt = row.bound_at === null ? null : integer(row.bound_at);
  const contentExpiresAt = row.content_expires_at === null ? null : integer(row.content_expires_at);
  const state = row.attachment_state;
  if (typeof row.id !== "string" || row.id.length === 0
    || typeof row.account_id !== "string"
    || typeof row.attachment_scope !== "string"
    || typeof row.display_name !== "string"
    || typeof row.mime_type !== "string" || !isAllowedChatAttachmentMimeType(row.mime_type)
    || typeof state !== "string" || !STATES.has(state as ChatAttachmentState)
    || row.scanner_id !== DEV_NOOP_SCANNER_ID
    || sizeBytes === null || sizeBytes <= 0 || sizeBytes > CHAT_MAX_ATTACHMENT_BYTES
    || stagedAt === null || stageExpiresAt === null || stageExpiresAt <= stagedAt
    || (row.content_reference !== null && typeof row.content_reference !== "string")
    || (row.bound_message_id !== null && typeof row.bound_message_id !== "string")
    || (scanningStartedAt === null && row.scanning_started_at !== null)
    || (boundAt === null && row.bound_at !== null)
    || (contentExpiresAt === null && row.content_expires_at !== null)) {
    return fail();
  }
  return Object.freeze({
    id: row.id,
    contentReference: row.content_reference as string | null,
    accountId: row.account_id,
    scope: row.attachment_scope,
    displayName: row.display_name,
    mimeType: row.mime_type,
    sizeBytes,
    state: state as ChatAttachmentState,
    scannerId: DEV_NOOP_SCANNER_ID,
    scanningStartedAt,
    stagedAt,
    stageExpiresAt,
    boundMessageId: row.bound_message_id as string | null,
    boundAt,
    contentExpiresAt,
    content: bytesOf(row.content_bytes),
  });
};

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
    scanState: record.state,
    scannerId: record.scannerId,
  });

const canResolve = (
  record: ChatAttachmentRecord | null,
  input: ResolveChatAttachmentsInput,
): record is ChatAttachmentRecord => record !== null
  && record.accountId === input.accountId
  && record.scope === input.scope
  && (record.state === "bound"
    ? record.boundMessageId === input.messageId
    : attachmentScanAdmissible(record.state)
      && input.nowEpochMilliseconds < record.stageExpiresAt);

const assertSameAccount = (
  authority: AuthorizedLedgerWriteContext,
  accountId: string,
): void => {
  if (accountId !== authority.account_id) {
    throw new PostgresRepositoryError("authorization_state_denied");
  }
};

export async function withAuthorizedChatAttachments<Result>(
  pool: PostgresTransactionPool,
  authority: AuthorizedLedgerWriteContext,
  signal: AbortSignal,
  project: (storage: ChatAttachmentStorage) => Result | Promise<Result>,
): Promise<Result> {
  if (authority.capability !== "chat.write") {
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
      const readRow = async (id: string): Promise<ChatAttachmentRecord | null> => {
        const rows = await connection.query({
          name: "chat.attachment_read",
          text: `SELECT account_id, id, content_reference, attachment_scope, display_name, mime_type,
            size_bytes, attachment_state, scanner_id, scanning_started_at, staged_at,
            stage_expires_at, bound_message_id, bound_at, content_expires_at, content_bytes
            FROM omi_memory.chat_attachments WHERE account_id=$1 AND id=$2`,
          values: [authority.account_id, id],
        });
        if (rows.length === 0) return null;
        if (rows.length !== 1) return fail();
        return parseRow(rows[0]!);
      };

      const storage: ChatAttachmentStorage = {
        async stage(input) {
          assertSameAccount(authority, input.accountId);
          if (input.id.length === 0 || input.contentReference.length === 0
            || input.displayName.length === 0 || !isAllowedChatAttachmentMimeType(input.mimeType)
            || input.content.byteLength === 0
            || input.content.byteLength > CHAT_MAX_ATTACHMENT_BYTES
            || !Number.isSafeInteger(input.stagedAt) || input.stagedAt < 0
            || input.stageExpiresAt <= input.stagedAt) {
            throw new TypeError("invalid staged chat attachment");
          }
          const inserted = await connection.execute({
            name: "chat.attachment_stage",
            text: `INSERT INTO omi_memory.chat_attachments (
              account_id, id, content_reference, attachment_scope, display_name, mime_type,
              size_bytes, attachment_state, scanner_id, scanning_started_at, staged_at,
              stage_expires_at, bound_message_id, bound_at, content_expires_at, content_bytes
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,'staged',$8,NULL,$9,$10,NULL,NULL,NULL,$11)
            ON CONFLICT (account_id, id) DO NOTHING`,
            values: [
              authority.account_id,
              input.id,
              input.contentReference,
              input.scope,
              input.displayName,
              input.mimeType,
              input.content.byteLength,
              DEV_NOOP_SCANNER_ID,
              input.stagedAt,
              input.stageExpiresAt,
              input.content,
            ],
          });
          if (inserted.rowCount !== 1) throw new TypeError("chat attachment opaque identity collision");
          const stored = await readRow(input.id);
          if (stored === null) return fail();
          return stored;
        },

        async advanceScan(id, clock) {
          const row = await readRow(id);
          if (row === null || row.state === "bound") return null;
          const next = row.state === "staged"
            ? beginAttachmentScan({
              scannerId: row.scannerId,
              state: row.state,
              scanningStartedAt: row.scanningStartedAt,
              stagedAt: row.stagedAt,
            }, { clock })
            : advanceAttachmentScan({
              scannerId: row.scannerId,
              state: row.state,
              scanningStartedAt: row.scanningStartedAt,
              stagedAt: row.stagedAt,
            }, { clock });
          const updated = await connection.execute({
            name: "chat.attachment_scan",
            text: `UPDATE omi_memory.chat_attachments
              SET attachment_state=$1, scanning_started_at=$2
              WHERE account_id=$3 AND id=$4 AND attachment_state IS DISTINCT FROM 'bound'`,
            values: [next.state, next.scanningStartedAt, authority.account_id, id],
          });
          if (updated.rowCount !== 1) return fail();
          return readRow(id);
        },

        async retryScan(id, clock) {
          const row = await readRow(id);
          if (row === null || row.state === "bound" || row.state === "staged"
            || row.state === "scanning" || row.state === "clean") return null;
          const restarted = beginAttachmentScan({
            scannerId: row.scannerId,
            state: row.state,
            scanningStartedAt: row.scanningStartedAt,
            stagedAt: row.stagedAt,
          }, { clock });
          const updated = await connection.execute({
            name: "chat.attachment_retry_scan",
            text: `UPDATE omi_memory.chat_attachments
              SET attachment_state=$1, scanning_started_at=$2
              WHERE account_id=$3 AND id=$4 AND attachment_state IS DISTINCT FROM 'bound'`,
            values: [restarted.state, restarted.scanningStartedAt, authority.account_id, id],
          });
          if (updated.rowCount !== 1) return fail();
          return storage.advanceScan(id, clock);
        },

        async resolveForAdmission(input) {
          assertSameAccount(authority, input.accountId);
          const attachments: ChatAttachmentMetadata[] = [];
          for (const id of input.attachmentIds) {
            const row = await readRow(id);
            if (!canResolve(row, input)) return { kind: "not_found" };
            attachments.push(metadataOf(row, input.nowEpochMilliseconds));
          }
          return Object.freeze({ kind: "ready" as const, attachments: Object.freeze(attachments) });
        },

        async bindToMessage(input) {
          const ready = await storage.resolveForAdmission(input);
          if (ready.kind === "not_found") return ready;
          const contentExpiresAt = input.contentExpiresAt ?? input.nowEpochMilliseconds + ATTACHMENT_CONTENT_RETENTION_MS;
          for (const id of input.attachmentIds) {
            await connection.execute({
              name: "chat.attachment_bind",
              text: `UPDATE omi_memory.chat_attachments SET
                attachment_state='bound', bound_message_id=$1, bound_at=$2, content_expires_at=$3
                WHERE account_id=$4 AND id=$5 AND attachment_scope=$6
                  AND attachment_state='clean' AND stage_expires_at>$7`,
              values: [
                input.messageId,
                input.nowEpochMilliseconds,
                contentExpiresAt,
                authority.account_id,
                id,
                input.scope,
                input.nowEpochMilliseconds,
              ],
            });
          }
          return storage.resolveForAdmission(input);
        },

        async removeUnbound(id, accountId) {
          assertSameAccount(authority, accountId);
          const rows = await connection.query({
            name: "chat.attachment_remove_unbound",
            text: "SELECT omi_memory.remove_unbound_chat_attachment($1) AS removed",
            values: [id],
          });
          return rows[0]?.removed === true;
        },

        async projectMessageAttachments(input) {
          assertSameAccount(authority, input.accountId);
          await connection.execute({
            name: "chat.attachment_expire_content",
            text: `UPDATE omi_memory.chat_attachments
              SET content_reference=NULL, content_bytes=NULL
              WHERE account_id=$1 AND bound_message_id=$2 AND attachment_state='bound'
                AND content_expires_at<=$3
                AND (content_reference IS NOT NULL OR content_bytes IS NOT NULL)`,
            values: [authority.account_id, input.messageId, input.nowEpochMilliseconds],
          });
          return Object.freeze(await Promise.all(input.attachments.map(async (metadata) => {
            const row = await readRow(metadata.id);
            return row !== null && row.boundMessageId === input.messageId
              ? metadataOf(row, input.nowEpochMilliseconds)
              : Object.freeze({ ...metadata, contentReference: null });
          })));
        },
      };

      const result = await project(storage);
      const clocks = await connection.query({
        name: "chat.attachment_final_clock",
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
