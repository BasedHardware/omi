import type { Database } from "bun:sqlite";

import {
  defineChatGenerationFinalization,
  type ChatGenerationFinalization,
} from "../../../apps/service/stores/chat-generation-finalization";
import { configureServiceStoreConnection } from "./connection";
import { SqliteChatGenerationEventsStore } from "./chat-generation-events-store";
import { SqliteChatMessagesStore } from "./chat-messages-store";

export interface SqliteChatGenerationFinalizationFaults {
  /** Crash-proof seam after canonical persistence and before terminal append. */
  readonly beforeTerminalAppend?: () => void;
  /** Crash-proof seam after terminal append and before transaction commit. */
  readonly afterTerminalAppend?: () => void;
}

export const createSqliteChatGenerationFinalization = (
  db: Database,
  faults: SqliteChatGenerationFinalizationFaults = {},
): ChatGenerationFinalization => {
  configureServiceStoreConnection(db);
  const messages = new SqliteChatMessagesStore(db);
  const events = new SqliteChatGenerationEventsStore(db);
  return defineChatGenerationFinalization({
    execute<Result>(_accountId: string, operation: () => Result): Result {
      return db.transaction(operation).immediate();
    },
  }, messages, events, faults.beforeTerminalAppend, faults.afterTerminalAppend);
};
