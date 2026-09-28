// domain-pending(DIV-DOMCORE-012)
// domain-pending(UNK-DOMAPPS-001)

import type { Database } from "bun:sqlite";

import { defineListenSegmentUnitOfWork } from "../../../apps/service/stores/listen-segment-unit-of-work";
import { createUnitOfWorkContext, type UnitOfWorkContext } from "../../../apps/service/stores/unit-of-work-context";
import { configureServiceStoreConnection } from "./connection";
import { SqliteListenStore } from "./listen-store";
import { SqliteSettingsProjectionStore } from "./settings-projection";

export interface SqliteListenSegmentUnitOfWorkFaults {
  /** Crash-proof seam after transcript insertion and before usage accounting. */
  readonly afterSegmentAppend?: () => void;
}

export const createSqliteListenSegmentUnitOfWork = (
  db: Database,
  faults: SqliteListenSegmentUnitOfWorkFaults = {},
) => {
  configureServiceStoreConnection(db);
  const listen = new SqliteListenStore(db);
  const settings = new SqliteSettingsProjectionStore(db);
  const context = createUnitOfWorkContext(db);
  return defineListenSegmentUnitOfWork({
    execute<Result>(
      _input,
      operation: (workContext: UnitOfWorkContext<Database>) => Result,
    ): Promise<Result> {
      try {
        const transaction = db.transaction(() => operation(context));
        return Promise.resolve(transaction.immediate());
      } catch (error) {
        return Promise.reject(error);
      }
    },
  }, {
    readEntitlement: (workContext, input) => workContext.perform(db, () =>
      settings.readEntitlement(input.accountId)),
    appendSegment: (workContext, input) => workContext.perform(db, () => {
      const appended = listen.appendSegment(
        input.accountId,
        input.sessionId,
        input.segment,
        input.at,
      );
      faults.afterSegmentAppend?.();
      return appended;
    }),
    consumeTranscriptionSeconds: (workContext, input) => workContext.perform(db, () =>
      settings.consumeTranscriptionSeconds(input.accountId, input.consumedSeconds)),
  });
};
