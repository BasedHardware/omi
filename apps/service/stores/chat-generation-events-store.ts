import type { ChatMessageRecord } from "./chat-messages-store";

export type ChatGenerationFrame =
  | {
      readonly kind: "accepted";
      readonly message: ChatMessageRecord;
      readonly generation: { readonly id: string };
    }
  | { readonly kind: "snapshot"; readonly text: string }
  | { readonly kind: "delta"; readonly text: string }
  | { readonly kind: "done"; readonly message: ChatMessageRecord }
  | { readonly kind: "failed"; readonly error: { readonly code: string; readonly retryable: boolean } }
  | { readonly kind: "cancelled"; readonly message: ChatMessageRecord | null };

/** Durable event-log row. Sequence is per generation and strictly monotonic. */
export interface ChatGenerationEvent {
  readonly id: string;
  readonly generationId: string;
  readonly sequence: number;
  readonly createdAt: number;
  readonly frame: ChatGenerationFrame;
}

export type AppendChatGenerationEventOutcome =
  | { readonly kind: "appended"; readonly event: ChatGenerationEvent }
  | { readonly kind: "replay"; readonly event: ChatGenerationEvent }
  | { readonly kind: "conflict" };

export interface ChatGenerationEventsStore {
  append(input: {
    readonly accountId: string;
    readonly generationId: string;
    readonly eventId: string;
    readonly createdAt: number;
    readonly frame: ChatGenerationFrame;
  }): AppendChatGenerationEventOutcome;
  listAfter(
    accountId: string,
    generationId: string,
    afterEventId: string | null,
  ): readonly ChatGenerationEvent[] | null;
  reset(): void;
}

interface AccountGenerationLog {
  readonly events: ChatGenerationEvent[];
  readonly byId: Map<string, ChatGenerationEvent>;
}

const stableFrame = (frame: ChatGenerationFrame): string => JSON.stringify(frame);

const detachEvent = (event: ChatGenerationEvent): ChatGenerationEvent => Object.freeze({
  id: event.id,
  generationId: event.generationId,
  sequence: event.sequence,
  createdAt: event.createdAt,
  frame: structuredClone(event.frame),
});

const keyOf = (accountId: string, generationId: string): string =>
  `${accountId.length}:${accountId}:${generationId}`;

export const createInMemoryChatGenerationEventsStore = (): ChatGenerationEventsStore => {
  const logs = new Map<string, AccountGenerationLog>();

  return Object.freeze({
    append(input: Parameters<ChatGenerationEventsStore["append"]>[0]): AppendChatGenerationEventOutcome {
      if (!input.eventId || !input.generationId || !Number.isSafeInteger(input.createdAt)
        || input.createdAt < 0) {
        throw new TypeError("invalid chat generation event");
      }
      const key = keyOf(input.accountId, input.generationId);
      const log = logs.get(key) ?? { events: [], byId: new Map<string, ChatGenerationEvent>() };
      logs.set(key, log);
      const existing = log.byId.get(input.eventId);
      if (existing !== undefined) {
        return existing.generationId === input.generationId
          && existing.createdAt === input.createdAt
          && stableFrame(existing.frame) === stableFrame(input.frame)
          ? { kind: "replay", event: detachEvent(existing) }
          : { kind: "conflict" };
      }
      const event = Object.freeze({
        id: input.eventId,
        generationId: input.generationId,
        sequence: log.events.length + 1,
        createdAt: input.createdAt,
        frame: structuredClone(input.frame),
      });
      log.events.push(event);
      log.byId.set(event.id, event);
      return { kind: "appended", event: detachEvent(event) };
    },

    listAfter(
      accountId: string,
      generationId: string,
      afterEventId: string | null,
    ): readonly ChatGenerationEvent[] | null {
      const log = logs.get(keyOf(accountId, generationId));
      if (log === undefined) return Object.freeze([]);
      let index = 0;
      if (afterEventId !== null) {
        const found = log.events.findIndex((event) => event.id === afterEventId);
        if (found < 0) return null;
        index = found + 1;
      }
      return Object.freeze(log.events.slice(index).map(detachEvent));
    },

    reset(): void {
      logs.clear();
    },
  });
};
