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

export type ChatGenerationTerminalFrame = Extract<
  ChatGenerationFrame,
  { readonly kind: "done" | "failed" | "cancelled" }
>;

export interface ChatGenerationLifecycle {
  readonly accountId: string;
  readonly generationId: string;
  readonly state: "active" | "cancellation_requested" | "terminal";
}

export type ChatCancellationRequestOutcome =
  | { readonly kind: "accepted" }
  | { readonly kind: "already_requested" | "already_terminal" }
  | { readonly kind: "not_found" };

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
  readLifecycle(accountId: string, generationId: string): ChatGenerationLifecycle | null;
  listUnterminated(): readonly ChatGenerationLifecycle[];
  requestCancellation(accountId: string, generationId: string): ChatCancellationRequestOutcome;
  reset(): void;
}

export interface InMemoryChatGenerationEventsAccountSnapshot {
  readonly logs: readonly {
    readonly generationId: string;
    readonly events: readonly ChatGenerationEvent[];
    readonly state: ChatGenerationLifecycle["state"];
  }[];
}

/** Adapter-private capabilities owned by the in-memory chat admission unit. */
export interface InMemoryChatGenerationEventsStore extends ChatGenerationEventsStore {
  snapshotAccount(accountId: string): InMemoryChatGenerationEventsAccountSnapshot;
  restoreAccount(accountId: string, snapshot: InMemoryChatGenerationEventsAccountSnapshot): void;
}

interface AccountGenerationLog {
  readonly accountId: string;
  readonly generationId: string;
  readonly events: ChatGenerationEvent[];
  readonly byId: Map<string, ChatGenerationEvent>;
  state: ChatGenerationLifecycle["state"];
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

export const createInMemoryChatGenerationEventsStore = (): InMemoryChatGenerationEventsStore => {
  const logs = new Map<string, AccountGenerationLog>();

  return Object.freeze({
    append(input: Parameters<ChatGenerationEventsStore["append"]>[0]): AppendChatGenerationEventOutcome {
      if (!input.eventId || !input.generationId || !Number.isSafeInteger(input.createdAt)
        || input.createdAt < 0) {
        throw new TypeError("invalid chat generation event");
      }
      const key = keyOf(input.accountId, input.generationId);
      const log = logs.get(key) ?? {
        accountId: input.accountId,
        generationId: input.generationId,
        events: [],
        byId: new Map<string, ChatGenerationEvent>(),
        state: "active" as const,
      };
      logs.set(key, log);
      const existing = log.byId.get(input.eventId);
      if (existing !== undefined) {
        return existing.generationId === input.generationId
          && existing.createdAt === input.createdAt
          && stableFrame(existing.frame) === stableFrame(input.frame)
          ? { kind: "replay", event: detachEvent(existing) }
          : { kind: "conflict" };
      }
      if (log.state === "terminal") {
        const terminal = log.events.find((event) =>
          ["done", "failed", "cancelled"].includes(event.frame.kind));
        if (terminal === undefined) throw new TypeError("terminal chat generation has no terminal event");
        return { kind: "replay", event: detachEvent(terminal) };
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
      if (["done", "failed", "cancelled"].includes(event.frame.kind)) log.state = "terminal";
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

    readLifecycle(accountId: string, generationId: string): ChatGenerationLifecycle | null {
      const log = logs.get(keyOf(accountId, generationId));
      return log === undefined ? null : Object.freeze({ accountId, generationId, state: log.state });
    },

    listUnterminated(): readonly ChatGenerationLifecycle[] {
      const generations: ChatGenerationLifecycle[] = [];
      for (const log of logs.values()) {
        if (log.state === "terminal") continue;
        const accepted = log.events.find((event) => event.frame.kind === "accepted");
        if (accepted === undefined || accepted.frame.kind !== "accepted") continue;
        generations.push(Object.freeze({
          accountId: log.accountId,
          generationId: log.generationId,
          state: log.state,
        }));
      }
      return Object.freeze(generations);
    },

    requestCancellation(accountId: string, generationId: string): ChatCancellationRequestOutcome {
      const log = logs.get(keyOf(accountId, generationId));
      if (log === undefined) return { kind: "not_found" };
      if (log.state === "terminal") return { kind: "already_terminal" };
      if (log.state === "cancellation_requested") return { kind: "already_requested" };
      log.state = "cancellation_requested";
      return { kind: "accepted" };
    },

    snapshotAccount(accountId: string): InMemoryChatGenerationEventsAccountSnapshot {
      return Object.freeze({
        logs: Object.freeze([...logs.values()]
          .filter((log) => log.accountId === accountId)
          .map((log) => Object.freeze({
            generationId: log.generationId,
            events: Object.freeze(log.events.map(detachEvent)),
            state: log.state,
          }))),
      });
    },

    restoreAccount(
      accountId: string,
      snapshot: InMemoryChatGenerationEventsAccountSnapshot,
    ): void {
      for (const [key, log] of logs) {
        if (log.accountId === accountId) logs.delete(key);
      }
      for (const log of snapshot.logs) {
        const events = log.events.map(detachEvent);
        logs.set(keyOf(accountId, log.generationId), {
          accountId,
          generationId: log.generationId,
          events,
          byId: new Map(events.map((event) => [event.id, event])),
          state: log.state,
        });
      }
    },

    reset(): void {
      logs.clear();
    },
  });
};
