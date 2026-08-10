import type { Database } from "bun:sqlite";

import type { SettingsProjectionStore } from "../../../apps/service/control/settings-projection";
import {
  defineChatAdmission,
  type ChatAdmission,
} from "../../../apps/service/stores/chat-admission";
import type { ChatGenerationEventsStore } from "../../../apps/service/stores/chat-generation-events-store";
import type { ChatMessagesStore } from "../../../apps/service/stores/chat-messages-store";
import type { ChatAttachmentsStore } from "../../../apps/service/stores/chat-attachments-store";
import { configureServiceStoreConnection } from "./connection";

/** Message, quota, and accepted-event commit on one SQLite write transaction. */
export const createSqliteChatAdmission = (
  db: Database,
  messages: ChatMessagesStore,
  events: ChatGenerationEventsStore,
  settings: SettingsProjectionStore,
  attachments: ChatAttachmentsStore,
): ChatAdmission => {
  configureServiceStoreConnection(db);
  return defineChatAdmission({
    execute<Result>(_accountId: string, operation: () => Result): Result {
      return db.transaction(operation).immediate();
    },
  }, messages, events, settings, attachments);
};
