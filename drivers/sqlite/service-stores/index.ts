import type { Database } from "bun:sqlite";

import type { LocalServiceStores } from "../../../apps/service/app-facing";
import { SqliteAccountLifecycleStore } from "./account-lifecycle";
import { SqliteConversationsStore } from "./conversations-store";
import { SqliteCurrentSessionPort } from "./current-session";
import { createSqliteFolderDeletionUnitOfWork } from "./folder-deletion-unit-of-work";
import { SqliteFoldersStore } from "./folders-store";
import { SqliteAccountControlProjectionStore } from "./projection-store";
import { SqliteStragglerTable } from "./straggler-table";
import { SqliteSettingsProjectionStore } from "./settings-projection";
import { SqliteListenStore } from "./listen-store";
import { SqliteTasksStore } from "./tasks-store";
import { SqliteWriteIdRegistry } from "./write-id-registry";
import { createSqliteWriteUnitOfWork } from "./write-unit-of-work";

export { SqliteAccountLifecycleStore } from "./account-lifecycle";
export { SqliteCurrentSessionPort } from "./current-session";
export { SqliteSettingsProjectionStore } from "./settings-projection";
export { SqliteListenStore } from "./listen-store";

export { SqliteAccountControlProjectionStore } from "./projection-store";
export { SqliteConversationsStore } from "./conversations-store";
export { createSqliteFolderDeletionUnitOfWork } from "./folder-deletion-unit-of-work";
export { SqliteFoldersStore } from "./folders-store";
export { SqliteStragglerTable } from "./straggler-table";
export { SqliteTasksStore } from "./tasks-store";
export { SqliteWriteIdRegistry } from "./write-id-registry";
export { createSqliteWriteUnitOfWork } from "./write-unit-of-work";

/** Builds all service stores and the tasks unit of work over one SQLite connection. */
export const createSqliteLocalServiceStores = (
  db: Database,
): LocalServiceStores => {
  const tasks = new SqliteTasksStore(db);
  const registry = new SqliteWriteIdRegistry(db);
  const folders = new SqliteFoldersStore(db);
  const conversations = new SqliteConversationsStore(db, {
    hasFolder: (accountId, folderId) => folders.hasFolder(accountId, folderId),
  });
  return Object.freeze({
    conversations,
    folders,
    folderDeletion: createSqliteFolderDeletionUnitOfWork(db),
    tasks,
    registry,
    unitOfWork: createSqliteWriteUnitOfWork(db),
    stragglers: new SqliteStragglerTable(db),
    control: new SqliteAccountControlProjectionStore(db),
    settings: new SqliteSettingsProjectionStore(db),
    currentSession: new SqliteCurrentSessionPort(db),
    accountLifecycle: new SqliteAccountLifecycleStore(db),
    listen: new SqliteListenStore(db),
  });
};
