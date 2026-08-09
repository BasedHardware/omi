import type { Database } from "bun:sqlite";

import type { LocalServiceStores } from "../../../apps/service/app-facing";
import { SqliteAccountControlProjectionStore } from "./projection-store";
import { SqliteStragglerTable } from "./straggler-table";
import { SqliteTasksStore } from "./tasks-store";
import { SqliteWriteIdRegistry } from "./write-id-registry";

export { SqliteAccountControlProjectionStore } from "./projection-store";
export { SqliteStragglerTable } from "./straggler-table";
export { SqliteTasksStore } from "./tasks-store";
export { SqliteWriteIdRegistry } from "./write-id-registry";

/** Builds all four adapters over one caller-owned SQLite connection. */
export const createSqliteLocalServiceStores = (db: Database): LocalServiceStores =>
  Object.freeze({
    tasks: new SqliteTasksStore(db),
    registry: new SqliteWriteIdRegistry(db),
    stragglers: new SqliteStragglerTable(db),
    control: new SqliteAccountControlProjectionStore(db),
  });

