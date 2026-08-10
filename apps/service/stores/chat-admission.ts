// domain-pending(DIV-CHAT-HASH-001)

import type {
  InMemorySettingsProjectionStore,
  SettingsProjectionStore,
} from "../control/settings-projection";
import type {
  ChatGenerationEvent,
  ChatGenerationEventsStore,
  InMemoryChatGenerationEventsStore,
} from "./chat-generation-events-store";
import type {
  ChatMessageRecord,
  ChatMessagesStore,
  InMemoryChatMessagesStore,
  StoredChatMessage,
} from "./chat-messages-store";

export interface ChatAdmissionInput {
  readonly accountId: string;
  readonly message: ChatMessageRecord;
  readonly generationId: string;
  readonly acceptedEventId: string;
  readonly admittedAt: number;
}

export type ChatAdmissionOutcome =
  | {
      readonly kind: "created";
      readonly stored: StoredChatMessage;
      readonly acceptedEvent: ChatGenerationEvent;
    }
  | { readonly kind: "replay"; readonly stored: StoredChatMessage }
  | { readonly kind: "conflict" }
  | { readonly kind: "entitlement" };

export interface ChatAdmission {
  admit(input: ChatAdmissionInput): ChatAdmissionOutcome;
}

export interface ChatAdmissionTransaction {
  execute<Result>(accountId: string, operation: () => Result): Result;
}

/**
 * One admission algorithm for every adapter. The transaction encloses replay
 * classification, the authoritative Settings entitlement update, the message,
 * and its first durable generation event.
 */
export const defineChatAdmission = (
  transaction: ChatAdmissionTransaction,
  messages: ChatMessagesStore,
  events: ChatGenerationEventsStore,
  settings: SettingsProjectionStore,
): ChatAdmission => Object.freeze({
  admit(input: ChatAdmissionInput): ChatAdmissionOutcome {
    return transaction.execute(input.accountId, () => {
      const existing = messages.readMessage(input.accountId, input.message.id);
      if (existing !== null) {
        if (existing.message.payloadHash !== input.message.payloadHash) {
          return { kind: "conflict" };
        }
        const replay = messages.admitHuman(
          input.accountId,
          input.message,
          existing.generationId ?? input.generationId,
        );
        if (replay.kind === "conflict") return { kind: "conflict" };
        return { kind: "replay", stored: replay.stored };
      }

      // This is the same projection Settings renders and the write fence reads.
      // There is no chat-local quota mirror.
      const entitlement = settings.readEntitlement(input.accountId);
      if (entitlement !== null && (entitlement.limitReached
        || (entitlement.limit !== null && entitlement.used >= entitlement.limit))) {
        return { kind: "entitlement" };
      }

      const admitted = messages.admitHuman(
        input.accountId,
        input.message,
        input.generationId,
      );
      if (admitted.kind === "conflict") return { kind: "conflict" };
      if (admitted.kind === "replay") return { kind: "replay", stored: admitted.stored };

      if (entitlement !== null) {
        const used = entitlement.used + 1;
        settings.putEntitlement(input.accountId, {
          ...entitlement,
          used,
          limitReached: entitlement.limit !== null && used >= entitlement.limit,
        });
      }

      const accepted = events.append({
        accountId: input.accountId,
        generationId: input.generationId,
        eventId: input.acceptedEventId,
        createdAt: input.admittedAt,
        frame: {
          kind: "accepted",
          message: admitted.stored.message,
          generation: { id: input.generationId },
        },
      });
      if (accepted.kind !== "appended") {
        throw new TypeError("chat admission event identity conflict");
      }
      return {
        kind: "created",
        stored: admitted.stored,
        acceptedEvent: accepted.event,
      };
    });
  },
});

export const createInMemoryChatAdmission = (
  messages: InMemoryChatMessagesStore,
  events: InMemoryChatGenerationEventsStore,
  settings: InMemorySettingsProjectionStore,
): ChatAdmission => defineChatAdmission(
  {
    execute<Result>(accountId: string, operation: () => Result): Result {
      const messagesBefore = messages.snapshotAccount(accountId);
      const eventsBefore = events.snapshotAccount(accountId);
      const settingsBefore = settings.snapshotAccount(accountId);
      try {
        return operation();
      } catch (error) {
        events.restoreAccount(accountId, eventsBefore);
        settings.restoreAccount(accountId, settingsBefore);
        messages.restoreAccount(accountId, messagesBefore);
        throw error;
      }
    },
  },
  messages,
  events,
  settings,
);
