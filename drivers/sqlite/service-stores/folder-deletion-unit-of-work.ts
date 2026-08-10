import type { Database } from "bun:sqlite";

import type {
  FolderDeletionInput,
  FolderDeletionOutcome,
  FolderDeletionUnitOfWork,
} from "../../../apps/service/stores/folder-deletion-unit-of-work";
import { configureServiceStoreConnection } from "./connection";

interface StoredFolderFlags {
  readonly is_system: number;
}

interface StoredFolderId {
  readonly id: string;
}

export interface SqliteFolderDeletionFaults {
  /** Crash-proof seam at the committed operation's real between-write boundary. */
  readonly afterConversationReassignment?: () => void;
}

/**
 * SQLite's folder deletion unit. All reads and writes are issued directly on
 * `db`; no participating store can start a nested transaction or choose a
 * different connection. BEGIN IMMEDIATE also excludes a target deletion between
 * validation and reassignment.
 */
export class SqliteFolderDeletionUnitOfWork implements FolderDeletionUnitOfWork {
  constructor(
    private readonly db: Database,
    private readonly faults: SqliteFolderDeletionFaults = {},
  ) {
    configureServiceStoreConnection(db);
  }

  execute(input: FolderDeletionInput): Promise<FolderDeletionOutcome> {
    const write = this.db.transaction((): FolderDeletionOutcome => {
      const current = this.db.query(`
        SELECT is_system
        FROM service_folder_records
        WHERE account_id = ? AND id = ?
      `).get(input.accountId, input.folderId) as StoredFolderFlags | null;
      if (current === null) return { deleted: false, reason: "not_found" };
      if (current.is_system === 1) return { deleted: false, reason: "system_folder" };
      if (input.requestedTarget === input.folderId) {
        return { deleted: false, reason: "self_move" };
      }

      let target: string | null;
      if (input.requestedTarget !== null) {
        const selected = this.db.query(`
          SELECT id
          FROM service_folder_records
          WHERE account_id = ? AND id = ?
        `).get(input.accountId, input.requestedTarget) as StoredFolderId | null;
        if (selected === null) return { deleted: false, reason: "target_not_found" };
        target = selected.id;
      } else {
        const selected = this.db.query(`
          SELECT id
          FROM service_folder_records
          WHERE account_id = ? AND is_default = 1
          ORDER BY sequence ASC
          LIMIT 1
        `).get(input.accountId) as StoredFolderId | null;
        target = selected?.id ?? null;
      }

      if (target !== null) {
        const reassigned = this.db.query(`
          UPDATE service_conversation_records
          SET folder_id = ?
          WHERE account_id = ? AND folder_id = ?
        `).run(target, input.accountId, input.folderId);
        if (reassigned.changes > 0) {
          this.db.query(`
            INSERT INTO service_conversation_account_state (account_id, revision)
            VALUES (?, 1)
            ON CONFLICT (account_id) DO UPDATE SET revision = revision + 1
          `).run(input.accountId);
        }
        this.faults.afterConversationReassignment?.();
      }

      const deleted = this.db.query(`
        DELETE FROM service_folder_records
        WHERE account_id = ? AND id = ?
      `).run(input.accountId, input.folderId);
      if (deleted.changes !== 1) {
        throw new Error("folder disappeared inside SQLite deletion unit");
      }
      return { deleted: true, moved_to_folder_id: target };
    });
    return Promise.resolve(write.immediate());
  }
}
