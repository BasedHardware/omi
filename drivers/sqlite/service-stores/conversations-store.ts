// domain-pending(DIV-DOMCORE-013)
// domain-pending(UNK-DOMCORE-002)
import type { Database } from "bun:sqlite";

import type {
  ConversationDeleteOutcome,
  ConversationFolderReferenceLookup,
  ConversationFolderReassignmentOutcome,
  ConversationPatchOutcome,
  ConversationRecord,
  ConversationsStore,
  ConversationUpsertOutcome,
  ConversationVisibility,
} from "../../../apps/service/stores/conversations-store";
import { denyAllConversationFolderReferences } from "../../../apps/service/stores/conversations-store";
import { configureServiceStoreConnection } from "./connection";

interface StoredConversationRow {
  readonly id: string;
  readonly structured_title: string;
  readonly structured_overview: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly started_at: string;
  readonly finished_at: string;
  readonly source: string;
  readonly status: string;
  readonly discarded: number;
  readonly starred: number;
  readonly visibility: ConversationVisibility;
  readonly is_locked: number;
  readonly folder_id: string | null;
}

const toRecord = (row: StoredConversationRow): ConversationRecord => Object.freeze({
  id: row.id,
  structured: Object.freeze({
    title: row.structured_title,
    overview: row.structured_overview,
  }),
  created_at: row.created_at,
  updated_at: row.updated_at,
  started_at: row.started_at,
  finished_at: row.finished_at,
  source: row.source,
  status: row.status,
  discarded: row.discarded === 1,
  starred: row.starred === 1,
  visibility: row.visibility,
  is_locked: row.is_locked === 1,
  folder_id: row.folder_id,
});

const SELECT_FIELDS = `
  id, structured_title, structured_overview, created_at, updated_at,
  started_at, finished_at, source, status, discarded, starred,
  visibility, is_locked, folder_id
`;

/** SQLite persistence adapter for the ConversationsStore port. */
export class SqliteConversationsStore implements ConversationsStore {
  constructor(
    private readonly db: Database,
    private readonly folders: ConversationFolderReferenceLookup =
      denyAllConversationFolderReferences,
  ) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_conversation_records (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        id TEXT NOT NULL,
        structured_title TEXT NOT NULL,
        structured_overview TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        source TEXT NOT NULL,
        status TEXT NOT NULL,
        discarded INTEGER NOT NULL CHECK (discarded IN (0, 1)),
        starred INTEGER NOT NULL CHECK (starred IN (0, 1)),
        visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private', 'shared')),
        is_locked INTEGER NOT NULL CHECK (is_locked IN (0, 1)),
        folder_id TEXT,
        UNIQUE (account_id, id)
      );
      CREATE TABLE IF NOT EXISTS service_conversation_account_state (
        account_id TEXT PRIMARY KEY,
        revision INTEGER NOT NULL CHECK (revision >= 0)
      );
      CREATE INDEX IF NOT EXISTS service_conversation_records_by_account
        ON service_conversation_records (account_id, sequence);
    `);
  }

  listRecords(accountId: string): readonly ConversationRecord[] {
    const rows = this.db.query(`
      SELECT ${SELECT_FIELDS}
      FROM service_conversation_records
      WHERE account_id = ?
      ORDER BY sequence ASC
    `).all(accountId) as StoredConversationRow[];
    return Object.freeze(rows.map(toRecord));
  }

  readRecord(accountId: string, recordId: string): ConversationRecord | null {
    const row = this.db.query(`
      SELECT ${SELECT_FIELDS}
      FROM service_conversation_records
      WHERE account_id = ? AND id = ?
    `).get(accountId, recordId) as StoredConversationRow | null;
    return row === null ? null : toRecord(row);
  }

  upsert(accountId: string, record: ConversationRecord): ConversationUpsertOutcome {
    const write = this.db.transaction((): ConversationUpsertOutcome => {
      if (record.folder_id !== null && !this.folders.hasFolder(accountId, record.folder_id)) {
        return { stored: false, reason: "folder_not_found" };
      }
      this.db.query(`
        INSERT INTO service_conversation_records (
          account_id, id, structured_title, structured_overview,
          created_at, updated_at, started_at, finished_at, source, status,
          discarded, starred, visibility, is_locked, folder_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (account_id, id) DO UPDATE SET
          structured_title = excluded.structured_title,
          structured_overview = excluded.structured_overview,
          created_at = excluded.created_at,
          updated_at = excluded.updated_at,
          started_at = excluded.started_at,
          finished_at = excluded.finished_at,
          source = excluded.source,
          status = excluded.status,
          discarded = excluded.discarded,
          starred = excluded.starred,
          visibility = excluded.visibility,
          is_locked = excluded.is_locked,
          folder_id = excluded.folder_id
      `).run(
        accountId,
        record.id,
        record.structured.title,
        record.structured.overview,
        record.created_at,
        record.updated_at,
        record.started_at,
        record.finished_at,
        record.source,
        record.status,
        record.discarded ? 1 : 0,
        record.starred ? 1 : 0,
        record.visibility,
        record.is_locked ? 1 : 0,
        record.folder_id,
      );
      return { stored: true, record: this.readRecord(accountId, record.id)! };
    });
    return write.immediate();
  }

  updateTitle(
    accountId: string,
    recordId: string,
    title: string,
    updatedAt: string,
  ): ConversationPatchOutcome {
    return this.update(accountId, recordId, () => {
      this.db.query(`
        UPDATE service_conversation_records
        SET structured_title = ?, updated_at = ?
        WHERE account_id = ? AND id = ?
      `).run(title, updatedAt, accountId, recordId);
    });
  }

  updateStarred(
    accountId: string,
    recordId: string,
    starred: boolean,
    updatedAt: string,
  ): ConversationPatchOutcome {
    return this.update(accountId, recordId, () => {
      this.db.query(`
        UPDATE service_conversation_records
        SET starred = ?, updated_at = ?
        WHERE account_id = ? AND id = ?
      `).run(starred ? 1 : 0, updatedAt, accountId, recordId);
    });
  }

  updateVisibility(
    accountId: string,
    recordId: string,
    visibility: ConversationVisibility,
    updatedAt: string,
  ): ConversationPatchOutcome {
    return this.update(accountId, recordId, () => {
      this.db.query(`
        UPDATE service_conversation_records
        SET visibility = ?, updated_at = ?
        WHERE account_id = ? AND id = ?
      `).run(visibility, updatedAt, accountId, recordId);
    });
  }

  updateFolder(
    accountId: string,
    recordId: string,
    folderId: string | null,
    updatedAt: string,
  ): ConversationPatchOutcome {
    const write = this.db.transaction((): ConversationPatchOutcome => {
      if (this.readRecord(accountId, recordId) === null) {
        return { updated: false, reason: "not_found" };
      }
      if (folderId !== null && !this.folders.hasFolder(accountId, folderId)) {
        return { updated: false, reason: "folder_not_found" };
      }
      this.db.query(`
        UPDATE service_conversation_records
        SET folder_id = ?, updated_at = ?
        WHERE account_id = ? AND id = ?
      `).run(folderId, updatedAt, accountId, recordId);
      const stateRevision = this.bumpRevision(accountId);
      return {
        updated: true,
        record: this.readRecord(accountId, recordId)!,
        state_revision: stateRevision,
      };
    });
    return write.immediate();
  }

  deleteRecord(accountId: string, recordId: string): ConversationDeleteOutcome {
    const write = this.db.transaction((): ConversationDeleteOutcome => {
      const removed = this.db.query(`
        DELETE FROM service_conversation_records
        WHERE account_id = ? AND id = ?
      `).run(accountId, recordId);
      if (removed.changes === 0) return { deleted: false, reason: "not_found" };
      return { deleted: true, state_revision: this.bumpRevision(accountId) };
    });
    return write.immediate();
  }

  reassignFolderReferences(
    accountId: string,
    fromFolderId: string,
    toFolderId: string,
  ): ConversationFolderReassignmentOutcome {
    const write = this.db.transaction((): ConversationFolderReassignmentOutcome => {
      const result = this.db.query(`
        UPDATE service_conversation_records
        SET folder_id = ?
        WHERE account_id = ? AND folder_id = ?
      `).run(toFolderId, accountId, fromFolderId);
      return {
        reassigned: result.changes,
        state_revision: result.changes === 0 ? null : this.bumpRevision(accountId),
      };
    });
    return write.immediate();
  }

  readStateRevision(accountId: string): number {
    const row = this.db.query(`
      SELECT revision
      FROM service_conversation_account_state
      WHERE account_id = ?
    `).get(accountId) as { readonly revision: number } | null;
    return row?.revision ?? 0;
  }

  reset(): void {
    const reset = this.db.transaction(() => {
      this.db.exec("DELETE FROM service_conversation_records;");
      this.db.exec("DELETE FROM service_conversation_account_state;");
      this.db.query("DELETE FROM sqlite_sequence WHERE name = ?")
        .run("service_conversation_records");
    });
    reset.immediate();
  }

  private update(
    accountId: string,
    recordId: string,
    apply: () => void,
  ): ConversationPatchOutcome {
    const write = this.db.transaction((): ConversationPatchOutcome => {
      if (this.readRecord(accountId, recordId) === null) {
        return { updated: false, reason: "not_found" };
      }
      apply();
      const stateRevision = this.bumpRevision(accountId);
      return {
        updated: true,
        record: this.readRecord(accountId, recordId)!,
        state_revision: stateRevision,
      };
    });
    return write.immediate();
  }

  private bumpRevision(accountId: string): number {
    this.db.query(`
      INSERT INTO service_conversation_account_state (account_id, revision)
      VALUES (?, 1)
      ON CONFLICT (account_id) DO UPDATE SET revision = revision + 1
    `).run(accountId);
    return this.readStateRevision(accountId);
  }
}
