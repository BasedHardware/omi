import type { Database } from "bun:sqlite";

import type { LocalServiceStores } from "../../../apps/service/app-facing";
import type { ConversationFolderReferenceLookup } from "../../../apps/service/stores/conversations-store";
import { denyAllConversationFolderReferences } from "../../../apps/service/stores/conversations-store";
import { SqliteConversationsStore } from "./conversations-store";
import { SqliteAccountControlProjectionStore } from "./projection-store";
import { SqliteStragglerTable } from "./straggler-table";
import { SqliteTasksStore } from "./tasks-store";
import { SqliteWriteIdRegistry } from "./write-id-registry";
import { SqliteWriteUnitOfWork } from "./write-unit-of-work";

export { SqliteAccountControlProjectionStore } from "./projection-store";
export { SqliteConversationsStore } from "./conversations-store";
export { SqliteStragglerTable } from "./straggler-table";
export { SqliteTasksStore } from "./tasks-store";
export { SqliteWriteIdRegistry } from "./write-id-registry";
export { SqliteWriteUnitOfWork } from "./write-unit-of-work";

export interface SqliteLocalServiceStoreOptions {
  readonly conversationFolders?: ConversationFolderReferenceLookup;
}

/** Builds all service stores and the tasks unit of work over one SQLite connection. */
export const createSqliteLocalServiceStores = (
  db: Database,
  options: SqliteLocalServiceStoreOptions = {},
): LocalServiceStores => {
  const tasks = new SqliteTasksStore(db);
  const registry = new SqliteWriteIdRegistry(db);
  return Object.freeze({
    conversations: new SqliteConversationsStore(
      db,
      options.conversationFolders ?? denyAllConversationFolderReferences,
    ),
    tasks,
    registry,
    unitOfWork: new SqliteWriteUnitOfWork(db, tasks, registry),
    stragglers: new SqliteStragglerTable(db),
    control: new SqliteAccountControlProjectionStore(db),
  });
};
