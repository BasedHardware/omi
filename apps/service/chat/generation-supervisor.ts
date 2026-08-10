// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import { createHash } from "node:crypto";

import type { ChatGenerationContextSource } from "./generation-context";
import type { ChatGenerationSource, ChatGenerationSourceRun } from "./generation-source";
import type { ChatGenerationEvent } from "../stores/chat-generation-events-store";
import type { ChatGenerationEventsStore } from "../stores/chat-generation-events-store";
import type { ChatGenerationFinalization } from "../stores/chat-generation-finalization";
import type { ChatMessageRecord, ChatMessagesStore, StoredChatMessage } from "../stores/chat-messages-store";

export interface AdmittedChatGeneration {
  readonly accountId: string;
  readonly stored: StoredChatMessage;
  readonly acceptedEvent: ChatGenerationEvent;
}

export interface ChatGenerationSupervisor {
  onAdmitted(input: AdmittedChatGeneration): void;
  cancel(accountId: string, generationId: string): void;
  recoverInterrupted(): void;
}

export interface ChatGenerationSupervisorDependencies {
  readonly source: ChatGenerationSource;
  readonly context: ChatGenerationContextSource;
  readonly messages: ChatMessagesStore;
  readonly events: ChatGenerationEventsStore;
  readonly finalization: ChatGenerationFinalization;
  readonly nowEpochMilliseconds: () => number;
  readonly assistantMessageId: (accountId: string, generationId: string) => string;
  readonly eventId: (
    accountId: string,
    generationId: string,
    kind: string,
    sequence: number,
  ) => string;
  readonly revision: (accountId: string, messageId: string, payloadHash: string) => string;
}

interface ActiveGeneration {
  readonly accountId: string;
  readonly generationId: string;
  readonly admitted: StoredChatMessage;
  text: string;
  run: ChatGenerationSourceRun | null;
  terminal: boolean;
}

const FALLBACK_TEXT = "I’m sorry, I couldn’t complete that response.";

const accumulatedText = (events: readonly ChatGenerationEvent[]): string => {
  let text = "";
  for (const event of events) {
    if (event.frame.kind === "snapshot") text = event.frame.text;
    if (event.frame.kind === "delta") text += event.frame.text;
  }
  return text;
};

export const createChatGenerationSupervisor = (
  deps: ChatGenerationSupervisorDependencies,
): ChatGenerationSupervisor => {
  const active = new Map<string, ActiveGeneration>();
  const keyOf = (accountId: string, generationId: string): string =>
    `${accountId.length}:${accountId}:${generationId}`;

  const append = (
    state: Pick<ActiveGeneration, "accountId" | "generationId">,
    frame: { readonly kind: "snapshot" | "delta"; readonly text: string },
  ): void => {
    const prior = deps.events.listAfter(state.accountId, state.generationId, null);
    if (prior === null) throw new TypeError("chat generation event log disappeared");
    const appended = deps.events.append({
      accountId: state.accountId,
      generationId: state.generationId,
      eventId: deps.eventId(
        state.accountId,
        state.generationId,
        frame.kind,
        prior.length + 1,
      ),
      createdAt: deps.nowEpochMilliseconds(),
      frame,
    });
    if (appended.kind !== "appended") {
      throw new TypeError("chat generation event identity conflict");
    }
  };

  const assistantMessage = (
    state: Pick<ActiveGeneration, "accountId" | "generationId" | "admitted">,
    text: string,
  ): ChatMessageRecord => {
    const id = deps.assistantMessageId(state.accountId, state.generationId);
    const payloadHash = `sha256:${createHash("sha256")
      .update(`assistant\0${text}`, "utf8")
      .digest("hex")}`;
    const authoredAt = state.admitted.message.createdAt;
    const createdAt = Math.max(
      deps.nowEpochMilliseconds(),
      Math.min(Number.MAX_SAFE_INTEGER, authoredAt + 1),
    );
    return Object.freeze({
      id,
      text,
      sender: "ai",
      type: "text",
      createdAt,
      updatedAt: createdAt,
      chatSessionId: state.admitted.message.chatSessionId,
      appId: state.admitted.message.appId,
      journalRevision: 1,
      payloadHash,
      messageSource: "chat_generation",
      rating: null,
      reported: false,
      revision: deps.revision(state.accountId, id, payloadHash),
    });
  };

  const finalize = (
    state: ActiveGeneration,
    kind: "done" | "cancelled",
    text: string,
  ): void => {
    if (state.terminal) return;
    state.terminal = true;
    state.run?.cancel();
    const message = text.length === 0 ? null : assistantMessage(state, text);
    const prior = deps.events.listAfter(state.accountId, state.generationId, null);
    if (prior === null) throw new TypeError("chat generation event log disappeared");
    try {
      deps.finalization.finalize({
        accountId: state.accountId,
        generationId: state.generationId,
        eventId: deps.eventId(state.accountId, state.generationId, kind, prior.length + 1),
        createdAt: deps.nowEpochMilliseconds(),
        frame: kind === "done"
          ? { kind: "done", message: message ?? assistantMessage(state, FALLBACK_TEXT) }
          : { kind: "cancelled", message },
      });
    } catch (error) {
      state.terminal = false;
      throw error;
    }
    active.delete(keyOf(state.accountId, state.generationId));
  };

  const failInterrupted = (accountId: string, generationId: string): void => {
    const prior = deps.events.listAfter(accountId, generationId, null);
    if (prior === null) return;
    deps.finalization.finalize({
      accountId,
      generationId,
      eventId: deps.eventId(accountId, generationId, "failed", prior.length + 1),
      createdAt: deps.nowEpochMilliseconds(),
      frame: {
        kind: "failed",
        error: { code: "generation_interrupted", retryable: true },
      },
    });
  };

  const cancelFromDurableState = (accountId: string, generationId: string): void => {
    const admitted = deps.messages.readHumanByGeneration(accountId, generationId);
    const events = deps.events.listAfter(accountId, generationId, null);
    if (admitted === null || events === null) {
      failInterrupted(accountId, generationId);
      return;
    }
    const state: ActiveGeneration = {
      accountId,
      generationId,
      admitted,
      text: accumulatedText(events),
      run: null,
      terminal: false,
    };
    finalize(state, "cancelled", state.text);
  };

  const supervisor: ChatGenerationSupervisor = Object.freeze({
    onAdmitted(input): void {
      const generationId = input.acceptedEvent.generationId;
      const key = keyOf(input.accountId, generationId);
      if (active.has(key)) return;
      const state: ActiveGeneration = {
        accountId: input.accountId,
        generationId,
        admitted: input.stored,
        text: "",
        run: null,
        terminal: false,
      };
      active.set(key, state);
      append(state, { kind: "snapshot", text: "" });
      void deps.context.load({ accountId: input.accountId, admitted: input.stored })
        .then((context) => {
          if (state.terminal) return;
          state.run = deps.source.start({
            generationId,
            prompt: input.stored.message.text,
            context,
            onDelta(text): void {
              if (state.terminal || text.length === 0) return;
              state.text += text;
              append(state, { kind: "delta", text });
            },
            onComplete(): void {
              finalize(state, "done", state.text);
            },
            onError(): void {
              finalize(state, "done", FALLBACK_TEXT);
            },
          });
        })
        .catch(() => finalize(state, "done", FALLBACK_TEXT));
    },

    cancel(accountId: string, generationId: string): void {
      const state = active.get(keyOf(accountId, generationId));
      state?.run?.cancel();
      queueMicrotask(() => {
        if (state !== undefined) finalize(state, "cancelled", state.text);
        else cancelFromDurableState(accountId, generationId);
      });
    },

    recoverInterrupted(): void {
      for (const lifecycle of deps.events.listUnterminated()) {
        if (lifecycle.state === "cancellation_requested") {
          cancelFromDurableState(lifecycle.accountId, lifecycle.generationId);
        } else {
          failInterrupted(lifecycle.accountId, lifecycle.generationId);
        }
      }
    },
  });

  return supervisor;
};
