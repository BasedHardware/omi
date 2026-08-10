// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMCORE-013)

import type { ConversationsStore } from "../stores/conversations-store";
import type { ListenSessionRecord } from "../stores/listen-store";

/**
 * Downstream seam after transcript durability.
 *
 * The new memory system intentionally does not appear here. A completed listen
 * session becomes a normal conversation record; later processing can subscribe
 * beyond this port without the socket knowing any memory internals.
 */
export interface ListenConversationFinalizer {
  finalize(input: {
    readonly accountId: string;
    readonly session: ListenSessionRecord;
    readonly locked: boolean;
  }): void;
}

export const createListenConversationFinalizer = (
  conversations: ConversationsStore,
): ListenConversationFinalizer => Object.freeze({
  finalize({ accountId, session, locked }): void {
    const endedAt = session.endedAt ?? session.updatedAt;
    const outcome = conversations.upsert(accountId, {
      id: session.conversationId,
      structured: { title: "", overview: "" },
      created_at: session.startedAt,
      updated_at: endedAt,
      started_at: session.startedAt,
      finished_at: endedAt,
      source: session.source ?? "listen",
      // Transcript storage is complete; summarization/memory work is downstream.
      status: "processing",
      discarded: false,
      starred: false,
      visibility: "private",
      is_locked: locked,
      folder_id: null,
    });
    if (!outcome.stored) {
      throw new TypeError("listen conversation finalization was refused");
    }
  },
});
