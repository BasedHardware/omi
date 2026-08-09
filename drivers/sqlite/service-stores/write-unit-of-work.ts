// domain-pending(DIV-DOMTASK-001)
// domain-pending(DIV-DOMTASK-002)
// domain-pending(FC-DOMTASK-001)

import type { Database } from "bun:sqlite";

import {
  executeWriteUnit,
  type WriteUnitOfWork,
  type WriteUnitOfWorkInput,
  type WriteUnitOfWorkOutcome,
} from "../../../apps/service/stores/write-unit-of-work";
import type { TasksStore } from "../../../apps/service/stores/tasks-store";
import type { WriteIdRegistry } from "../../../apps/service/stores/write-id-registry";
import { configureServiceStoreConnection } from "./connection";

/**
 * SQLite's write unit of work. The task and registry adapters passed here must
 * be bound to `db`; the composition factory is the authority that constructs
 * that exact bundle. `BEGIN IMMEDIATE` serializes fresh-key lookup with other
 * writers and SQLite rolls the task change back if the registry record is not
 * reached before process death.
 */
export class SqliteWriteUnitOfWork implements WriteUnitOfWork {
  constructor(
    private readonly db: Database,
    private readonly tasks: TasksStore,
    private readonly registry: WriteIdRegistry,
  ) {
    configureServiceStoreConnection(db);
  }

  execute(input: WriteUnitOfWorkInput): Promise<WriteUnitOfWorkOutcome> {
    const transaction = this.db.transaction(() =>
      executeWriteUnit(this.tasks, this.registry, input));
    return Promise.resolve(transaction.immediate());
  }
}
