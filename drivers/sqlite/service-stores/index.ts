import type { Database } from "bun:sqlite";

import type { LocalServiceStores } from "../../../apps/service/app-facing";
import { SqliteConversationsStore } from "./conversations-store";
import { SqliteFoldersStore } from "./folders-store";
import { SqliteAccountControlProjectionStore } from "./projection-store";
import { SqliteStragglerTable } from "./straggler-table";
import { SqliteTasksStore } from "./tasks-store";
import { SqliteWriteIdRegistry } from "./write-id-registry";
import { SqliteWriteUnitOfWork } from "./write-unit-of-work";

export { SqliteAccountControlProjectionStore } from "./projection-store";
export { SqliteConversationsStore } from "./conversations-store";
export { SqliteFoldersStore } from "./folders-store";
export { SqliteStragglerTable } from "./straggler-table";
export { SqliteTasksStore } from "./tasks-store";
export { SqliteWriteIdRegistry } from "./write-id-registry";
export { SqliteWriteUnitOfWork } from "./write-unit-of-work";

/** Builds all service stores and the tasks unit of work over one SQLite connection. */
export const createSqliteLocalServiceStores = (
  db: Database,
): LocalServiceStores => {
  const tasks = new SqliteTasksStore(db);
  const registry = new SqliteWriteIdRegistry(db);
  let folders: SqliteFoldersStore | undefined;
  const conversations = new SqliteConversationsStore(db, {
    hasFolder: (accountId, folderId) => folders?.hasFolder(accountId, folderId) ?? false,
  });
  folders = new SqliteFoldersStore(db, conversations);
  return Object.freeze({
    conversations,
    folders,
    tasks,
    registry,
    unitOfWork: new SqliteWriteUnitOfWork(db, tasks, registry),
    stragglers: new SqliteStragglerTable(db),
    control: new SqliteAccountControlProjectionStore(db),
  });
};
