import type { Database } from "bun:sqlite";

import {
  defineFolderDeletionUnitOfWork,
  type FolderDeletionInput,
  type FolderDeletionUnitOfWork,
} from "../../../apps/service/stores/folder-deletion-unit-of-work";
import {
  createUnitOfWorkContext,
  type UnitOfWorkContext,
} from "../../../apps/service/stores/unit-of-work-context";
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
 * SQLite's folder deletion unit. Every operation receives the one context
 * created for `db`; the context rejects a different Database instance before
 * it can issue SQL. BEGIN IMMEDIATE excludes target deletion between validation
 * and reassignment.
 */
export const createSqliteFolderDeletionUnitOfWork = (
  db: Database,
  faults: SqliteFolderDeletionFaults = {},
): FolderDeletionUnitOfWork => {
  configureServiceStoreConnection(db);
  const context = createUnitOfWorkContext(db);
  return defineFolderDeletionUnitOfWork({
    execute<Result>(
      _input: FolderDeletionInput,
      operation: (
        context: UnitOfWorkContext<Database>,
        checkpointBeforeFirstWrite: () => void,
      ) => Result,
    ): Promise<Result> {
      const write = db.transaction(() => operation(context, () => {}));
      return Promise.resolve(write.immediate());
    },
  }, {
    readCurrent: (workContext, input) => workContext.perform(db, (connection) => {
      const current = connection.query(`
        SELECT is_system
        FROM service_folder_records
        WHERE account_id = ? AND id = ?
      `).get(input.accountId, input.folderId) as StoredFolderFlags | null;
      return current === null ? null : { isSystem: current.is_system === 1 };
    }),
    targetExists: (workContext, input, targetFolderId) =>
      workContext.perform(db, (connection) => {
        const selected = connection.query(`
          SELECT id
          FROM service_folder_records
          WHERE account_id = ? AND id = ?
        `).get(input.accountId, targetFolderId) as StoredFolderId | null;
        return selected !== null;
      }),
    findDefaultTarget: (workContext, input) => workContext.perform(db, (connection) => {
      const selected = connection.query(`
        SELECT id
        FROM service_folder_records
        WHERE account_id = ? AND is_default = 1
        ORDER BY sequence ASC
        LIMIT 1
      `).get(input.accountId) as StoredFolderId | null;
      return selected?.id ?? null;
    }),
    reassignConversations: (workContext, input, targetFolderId) =>
      workContext.perform(db, (connection) => {
        const reassigned = connection.query(`
          UPDATE service_conversation_records
          SET folder_id = ?
          WHERE account_id = ? AND folder_id = ?
        `).run(targetFolderId, input.accountId, input.folderId);
        if (reassigned.changes > 0) {
          connection.query(`
            INSERT INTO service_conversation_account_state (account_id, revision)
            VALUES (?, 1)
            ON CONFLICT (account_id) DO UPDATE SET revision = revision + 1
          `).run(input.accountId);
        }
        faults.afterConversationReassignment?.();
      }),
    deleteFolder: (workContext, input) => workContext.perform(db, (connection) =>
      connection.query(`
        DELETE FROM service_folder_records
        WHERE account_id = ? AND id = ?
      `).run(input.accountId, input.folderId).changes === 1),
  });
};
