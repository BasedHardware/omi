import type { Database } from "bun:sqlite";

import type { ChatGenerationAttachmentDescriptor } from "../../../apps/service/chat/attachment-content";
import {
  CHAT_MAX_ATTACHMENT_BYTES,
  isAllowedChatAttachmentMimeType,
  type AllowedChatAttachmentMimeType,
} from "../../../apps/service/chat/attachment-policy";
import {
  advanceAttachmentScan,
  attachmentScanAdmissible,
  beginAttachmentScan,
  DEV_NOOP_SCANNER_ID,
  type AttachmentScanClock,
} from "../../../apps/service/chat/attachment-scanner";
import type {
  BindChatAttachmentsInput,
  ChatAttachmentRecord,
  ChatAttachmentState,
  ChatAttachmentsStore,
  ResolveChatAttachmentsInput,
  ResolveChatAttachmentsOutcome,
  StageChatAttachmentInput,
} from "../../../apps/service/stores/chat-attachments-store";
import type { ChatAttachmentMetadata } from "../../../apps/service/stores/chat-messages-store";
import { configureServiceStoreConnection } from "./connection";

interface StoredAttachmentRow {
  readonly id: string;
  readonly content_reference: string | null;
  readonly account_id: string;
  readonly attachment_scope: string;
  readonly display_name: string;
  readonly mime_type: AllowedChatAttachmentMimeType;
  readonly size_bytes: number;
  readonly attachment_state: ChatAttachmentState;
  readonly scanner_id: typeof DEV_NOOP_SCANNER_ID;
  readonly scanning_started_at: number | null;
  readonly staged_at: number;
  readonly stage_expires_at: number;
  readonly bound_message_id: string | null;
  readonly bound_at: number | null;
  readonly content_expires_at: number | null;
  readonly content_bytes: Uint8Array | null;
}

const SCAN_STATES = "'staged','scanning','clean','rejected','timed_out','error','bound'";

const SELECT_FIELDS = `
  id, content_reference, account_id, attachment_scope, display_name, mime_type,
  size_bytes, attachment_state, scanner_id, scanning_started_at, staged_at,
  stage_expires_at, bound_message_id, bound_at, content_expires_at, content_bytes
`;

const detachBytes = (value: Uint8Array | null): Uint8Array | null =>
  value === null ? null : new Uint8Array(value);

const fromRow = (row: StoredAttachmentRow): ChatAttachmentRecord => Object.freeze({
  id: row.id,
  contentReference: row.content_reference,
  accountId: row.account_id,
  scope: row.attachment_scope,
  displayName: row.display_name,
  mimeType: row.mime_type,
  sizeBytes: row.size_bytes,
  state: row.attachment_state,
  scannerId: row.scanner_id,
  scanningStartedAt: row.scanning_started_at,
  stagedAt: row.staged_at,
  stageExpiresAt: row.stage_expires_at,
  boundMessageId: row.bound_message_id,
  boundAt: row.bound_at,
  contentExpiresAt: row.content_expires_at,
  content: detachBytes(row.content_bytes),
});

const metadataOf = (row: StoredAttachmentRow, now: number): ChatAttachmentMetadata =>
  Object.freeze({
    id: row.id,
    displayName: row.display_name,
    mediaType: row.mime_type,
    sizeBytes: row.size_bytes,
    contentReference: row.attachment_state === "bound"
        && row.content_bytes !== null
        && row.content_reference !== null
        && row.content_expires_at !== null
        && now < row.content_expires_at
      ? row.content_reference
      : null,
    scanState: row.attachment_state,
    scannerId: row.scanner_id,
  });

const canResolve = (
  row: StoredAttachmentRow | null,
  input: ResolveChatAttachmentsInput,
): row is StoredAttachmentRow => row !== null
  && row.account_id === input.accountId
  && row.attachment_scope === input.scope
  && (row.attachment_state === "bound"
    ? row.bound_message_id === input.messageId
    : attachmentScanAdmissible(row.attachment_state)
      && input.nowEpochMilliseconds < row.stage_expires_at);

const scanInputOf = (row: StoredAttachmentRow) => ({
  scannerId: row.scanner_id,
  state: row.attachment_state,
  scanningStartedAt: row.scanning_started_at,
  stagedAt: row.staged_at,
});

export class SqliteChatAttachmentsStore implements ChatAttachmentsStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_chat_attachments (
        id TEXT PRIMARY KEY,
        content_reference TEXT UNIQUE,
        account_id TEXT NOT NULL,
        attachment_scope TEXT NOT NULL,
        display_name TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
        attachment_state TEXT NOT NULL CHECK (attachment_state IN (${SCAN_STATES})),
        scanner_id TEXT NOT NULL,
        scanning_started_at INTEGER,
        staged_at INTEGER NOT NULL CHECK (staged_at >= 0),
        stage_expires_at INTEGER NOT NULL CHECK (stage_expires_at > staged_at),
        bound_message_id TEXT,
        bound_at INTEGER,
        content_expires_at INTEGER,
        content_bytes BLOB
      );
      CREATE INDEX IF NOT EXISTS service_chat_attachments_owner_message
        ON service_chat_attachments (account_id, attachment_scope, bound_message_id, id);
      CREATE INDEX IF NOT EXISTS service_chat_attachments_staging_expiry
        ON service_chat_attachments (attachment_state, stage_expires_at);
    `);
    const columns = this.db.query("PRAGMA table_info(service_chat_attachments)").all() as Array<{ name: string }>;
    const names = new Set(columns.map((column) => column.name));
    if (!names.has("scanner_id")) {
      this.db.exec("ALTER TABLE service_chat_attachments ADD COLUMN scanner_id TEXT NOT NULL DEFAULT 'dev-noop-scanner';");
    }
    if (!names.has("scanning_started_at")) {
      this.db.exec("ALTER TABLE service_chat_attachments ADD COLUMN scanning_started_at INTEGER;");
    }
  }

  stage(input: StageChatAttachmentInput): ChatAttachmentRecord {
    if (input.id.length === 0 || input.contentReference.length === 0
      || input.displayName.length === 0 || !isAllowedChatAttachmentMimeType(input.mimeType)
      || input.content.byteLength === 0
      || input.content.byteLength > CHAT_MAX_ATTACHMENT_BYTES
      || !Number.isSafeInteger(input.stagedAt) || input.stagedAt < 0
      || input.stageExpiresAt <= input.stagedAt) {
      throw new TypeError("invalid staged chat attachment");
    }
    const inserted = this.db.query(`
      INSERT INTO service_chat_attachments (
        id, content_reference, account_id, attachment_scope, display_name,
        mime_type, size_bytes, attachment_state, scanner_id, scanning_started_at,
        staged_at, stage_expires_at, bound_message_id, bound_at, content_expires_at,
        content_bytes
      ) VALUES (?, ?, ?, ?, ?, ?, ?, 'staged', ?, NULL, ?, ?, NULL, NULL, NULL, ?)
      ON CONFLICT DO NOTHING
    `).run(
      input.id,
      input.contentReference,
      input.accountId,
      input.scope,
      input.displayName,
      input.mimeType,
      input.content.byteLength,
      DEV_NOOP_SCANNER_ID,
      input.stagedAt,
      input.stageExpiresAt,
      input.content,
    );
    if (inserted.changes !== 1) throw new TypeError("chat attachment opaque identity collision");
    return fromRow(this.readRow(input.id)!);
  }

  advanceScan(id: string, clock: AttachmentScanClock): ChatAttachmentRecord | null {
    const row = this.readRow(id);
    if (row === null || row.attachment_state === "bound") return null;
    const next = row.attachment_state === "staged"
      ? beginAttachmentScan(scanInputOf(row), { clock })
      : advanceAttachmentScan(scanInputOf(row), { clock });
    this.db.query(`
      UPDATE service_chat_attachments
      SET attachment_state = ?, scanning_started_at = ?
      WHERE id = ?
    `).run(next.state, next.scanningStartedAt, id);
    return fromRow(this.readRow(id)!);
  }

  retryScan(id: string, clock: AttachmentScanClock): ChatAttachmentRecord | null {
    const row = this.readRow(id);
    if (row === null || row.attachment_state === "bound" || row.attachment_state === "staged"
      || row.attachment_state === "scanning" || row.attachment_state === "clean") return null;
    const restarted = beginAttachmentScan(scanInputOf(row), { clock });
    this.db.query(`
      UPDATE service_chat_attachments
      SET attachment_state = ?, scanning_started_at = ?
      WHERE id = ?
    `).run(restarted.state, restarted.scanningStartedAt, id);
    return this.advanceScan(id, clock);
  }

  removeUnbound(id: string, accountId: string): boolean {
    const deleted = this.db.query(`
      DELETE FROM service_chat_attachments
      WHERE id = ? AND account_id = ? AND attachment_state != 'bound'
    `).run(id, accountId);
    return deleted.changes === 1;
  }

  resolveForAdmission(input: ResolveChatAttachmentsInput): ResolveChatAttachmentsOutcome {
    const rows: StoredAttachmentRow[] = [];
    for (const id of input.attachmentIds) {
      const row = this.readRow(id);
      if (!canResolve(row, input)) return { kind: "not_found" };
      rows.push(row);
    }
    return Object.freeze({
      kind: "ready" as const,
      attachments: Object.freeze(rows.map((row) => metadataOf(row, input.nowEpochMilliseconds))),
    });
  }

  bindToMessage(input: BindChatAttachmentsInput): ResolveChatAttachmentsOutcome {
    const ready = this.resolveForAdmission(input);
    if (ready.kind === "not_found") return ready;
    for (const id of input.attachmentIds) {
      this.db.query(`
        UPDATE service_chat_attachments SET
          attachment_state = 'bound', bound_message_id = ?, bound_at = ?,
          content_expires_at = ?
        WHERE id = ? AND account_id = ? AND attachment_scope = ?
          AND attachment_state = 'clean' AND stage_expires_at > ?
      `).run(
        input.messageId,
        input.nowEpochMilliseconds,
        input.contentExpiresAt,
        id,
        input.accountId,
        input.scope,
        input.nowEpochMilliseconds,
      );
    }
    return this.resolveForAdmission(input);
  }

  projectMessageAttachments(input: {
    readonly accountId: string;
    readonly messageId: string;
    readonly attachments: readonly ChatAttachmentMetadata[];
    readonly nowEpochMilliseconds: number;
  }): readonly ChatAttachmentMetadata[] {
    return this.db.transaction(() => {
      this.expireContent(input.accountId, input.messageId, input.nowEpochMilliseconds);
      return Object.freeze(input.attachments.map((metadata) => {
        const row = this.readRow(metadata.id);
        return row !== null
            && row.account_id === input.accountId
            && row.bound_message_id === input.messageId
          ? metadataOf(row, input.nowEpochMilliseconds)
          : Object.freeze({ ...metadata, contentReference: null });
      }));
    }).immediate();
  }

  loadForGeneration(input: {
    readonly accountId: string;
    readonly messageId: string;
    readonly attachments: readonly ChatAttachmentMetadata[];
    readonly nowEpochMilliseconds: number;
  }): readonly ChatGenerationAttachmentDescriptor[] {
    return this.db.transaction(() => {
      this.expireContent(input.accountId, input.messageId, input.nowEpochMilliseconds);
      return Object.freeze(input.attachments.map((metadata) => {
        const row = this.readRow(metadata.id);
        const owned = row !== null
          && row.account_id === input.accountId
          && row.bound_message_id === input.messageId;
        const projected = owned
          ? metadataOf(row, input.nowEpochMilliseconds)
          : Object.freeze({ ...metadata, contentReference: null });
        return Object.freeze({
          ...projected,
          content: owned ? detachBytes(row.content_bytes) : null,
        });
      }));
    }).immediate();
  }

  reset(): void {
    this.db.transaction(() => {
      this.db.exec("DELETE FROM service_chat_attachments;");
    }).immediate();
  }

  private readRow(id: string): StoredAttachmentRow | null {
    return this.db.query(`
      SELECT ${SELECT_FIELDS} FROM service_chat_attachments WHERE id = ?
    `).get(id) as StoredAttachmentRow | null;
  }

  private expireContent(accountId: string, messageId: string, now: number): void {
    this.db.query(`
      UPDATE service_chat_attachments
      SET content_reference = NULL, content_bytes = NULL
      WHERE account_id = ? AND bound_message_id = ? AND attachment_state = 'bound'
        AND content_expires_at <= ?
        AND (content_reference IS NOT NULL OR content_bytes IS NOT NULL)
    `).run(accountId, messageId, now);
  }
}
