// domain-pending(DIV-DOMTASK-001)
// domain-pending(DIV-DOMTASK-002)
// domain-pending(FC-DOMTASK-001)

import type { Database } from "bun:sqlite";

import {
  defineWriteUnitOfWork,
  type WriteUnitOfWork,
  type WriteUnitOfWorkInput,
} from "../../../apps/service/stores/write-unit-of-work";
import {
  createUnitOfWorkContext,
  type UnitOfWorkContext,
} from "../../../apps/service/stores/unit-of-work-context";
import { configureServiceStoreConnection } from "./connection";
import { SqliteTasksStore } from "./tasks-store";
import { SqliteWriteIdRegistry } from "./write-id-registry";

export interface SqliteWriteUnitOfWorkFaults {
  /** Crash-proof seam after task apply and immediately before registry record. */
  readonly beforeRegistryRecord?: () => void;
}

/**
 * SQLite's write unit. The participating adapters are constructed here from
 * the same `db`; callers cannot supply independently bound stores. Every
 * operation additionally passes the runtime identity check before delegating.
 */
export const createSqliteWriteUnitOfWork = (
  db: Database,
  faults: SqliteWriteUnitOfWorkFaults = {},
): WriteUnitOfWork => {
  configureServiceStoreConnection(db);
  const tasks = new SqliteTasksStore(db);
  const registry = new SqliteWriteIdRegistry(db);
  const context = createUnitOfWorkContext(db);
  return defineWriteUnitOfWork({
    execute<Result>(
      _input: WriteUnitOfWorkInput,
      operation: (context: UnitOfWorkContext<Database>) => Result,
    ): Promise<Result> {
      const transaction = db.transaction(() => operation(context));
      return Promise.resolve(transaction.immediate());
    },
  }, {
    lookup: (workContext, input) => workContext.perform(db, () =>
      registry.lookup(input.accountId, input.writeId, input.fingerprintOf)),
    apply: (workContext, input) => workContext.perform(db, () =>
      tasks.apply(input.accountId, input.op)),
    record: (workContext, input, outcome) => workContext.perform(db, () => {
      faults.beforeRegistryRecord?.();
      registry.record({
        accountId: input.accountId,
        writeId: input.writeId,
        fingerprintOf: input.fingerprintOf,
        accountEpoch: input.accountEpoch,
        outcome,
      });
    }),
  });
};
