import type {
  ChatGenerationEvent,
  ChatGenerationEventsStore,
  ChatGenerationTerminalFrame,
} from "./chat-generation-events-store";
import type { ChatMessagesStore } from "./chat-messages-store";

export interface ChatGenerationFinalizationInput {
  readonly accountId: string;
  readonly generationId: string;
  readonly eventId: string;
  readonly createdAt: number;
  readonly frame: ChatGenerationTerminalFrame;
}

export interface ChatGenerationFinalization {
  finalize(input: ChatGenerationFinalizationInput): ChatGenerationEvent;
}

export interface ChatGenerationFinalizationTransaction {
  execute<Result>(operation: () => Result): Result;
}

/** Canonical assistant persistence and its terminal frame share one commit. */
export const defineChatGenerationFinalization = (
  transaction: ChatGenerationFinalizationTransaction,
  messages: ChatMessagesStore,
  events: ChatGenerationEventsStore,
  beforeTerminalAppend: () => void = () => {},
): ChatGenerationFinalization => Object.freeze({
  finalize(input): ChatGenerationEvent {
    return transaction.execute(() => {
      const terminal = events.listAfter(input.accountId, input.generationId, null)
        ?.find((event) => ["done", "failed", "cancelled"].includes(event.frame.kind));
      if (terminal !== undefined) return terminal;
      const message = input.frame.kind === "failed" ? null : input.frame.message;
      if (message !== null) {
        const written = messages.writeCanonical(input.accountId, message, input.generationId);
        if (written.kind === "conflict" || written.kind === "invalid_vocabulary") {
          throw new TypeError("canonical chat generation message was refused");
        }
      }
      beforeTerminalAppend();
      const appended = events.append({
        accountId: input.accountId,
        generationId: input.generationId,
        eventId: input.eventId,
        createdAt: input.createdAt,
        frame: input.frame,
      });
      if (appended.kind === "conflict") {
        throw new TypeError("chat generation terminal event identity conflict");
      }
      return appended.event;
    });
  },
});

export const createInMemoryChatGenerationFinalization = (
  messages: ChatMessagesStore,
  events: ChatGenerationEventsStore,
): ChatGenerationFinalization => defineChatGenerationFinalization(
  { execute: <Result>(operation: () => Result): Result => operation() },
  messages,
  events,
);
