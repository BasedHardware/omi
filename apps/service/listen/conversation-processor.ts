// domain-pending(DIV-DOMCORE-013)

import type {
  ConversationRecord,
  ConversationsStore,
} from "../stores/conversations-store";

/** Downstream processing seam; future summarization/memory adapters plug in here. */
export interface ListenConversationProcessor {
  process(input: {
    readonly accountId: string;
    readonly conversation: ConversationRecord;
  }): void;
}

export type ListenConversationProcessorFactory = (
  conversations: ConversationsStore,
) => ListenConversationProcessor;

/** Deterministic local adapter: processing is complete once transcript persistence finishes. */
export const createDeterministicListenConversationProcessor = (
  conversations: ConversationsStore,
): ListenConversationProcessor => Object.freeze({
  process({ accountId, conversation }): void {
    if (conversation.status !== "processing") {
      throw new TypeError("listen conversation was not awaiting processing");
    }
    const outcome = conversations.upsert(accountId, {
      ...conversation,
      status: "completed",
    });
    if (!outcome.stored) {
      throw new TypeError("listen conversation processing transition was refused");
    }
  },
});
