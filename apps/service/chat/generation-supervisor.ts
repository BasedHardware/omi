// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import { createHash } from "node:crypto";

import type { ChatGenerationContextSource } from "./generation-context";
import type { ChatAttachmentContentPort } from "./attachment-content";
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
  readonly attachments: ChatAttachmentContentPort;
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
  runCancelled: boolean;
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
      attachments: Object.freeze([]),
    });
  };

  const cancelRun = (state: ActiveGeneration): void => {
    if (state.run === null || state.runCancelled) return;
    state.runCancelled = true;
    try {
      state.run.cancel();
    } catch {
      // Provider cancellation is best effort. Durable finalization remains the authority.
    }
  };

  const finalize = (
    state: ActiveGeneration,
    kind: "done" | "cancelled" | "failed",
    text: string,
  ): boolean => {
    if (state.terminal) return true;
    state.terminal = true;
    cancelRun(state);
    try {
      const message = text.length === 0 ? null : assistantMessage(state, text);
      const prior = deps.events.listAfter(state.accountId, state.generationId, null);
      if (prior === null) throw new TypeError("chat generation event log disappeared");
      deps.finalization.finalize({
        accountId: state.accountId,
        generationId: state.generationId,
        eventId: deps.eventId(state.accountId, state.generationId, kind, prior.length + 1),
        createdAt: deps.nowEpochMilliseconds(),
        frame: kind === "failed"
          ? {
              kind: "failed",
              error: { code: "generation_interrupted", retryable: true },
            }
          : kind === "done"
            ? { kind: "done", message: message ?? assistantMessage(state, FALLBACK_TEXT) }
            : { kind: "cancelled", message },
      });
    } catch {
      state.terminal = false;
      return false;
    }
    active.delete(keyOf(state.accountId, state.generationId));
    return true;
  };

  const failInterrupted = (accountId: string, generationId: string): boolean => {
    try {
      const prior = deps.events.listAfter(accountId, generationId, null);
      if (prior === null) return false;
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
      return true;
    } catch {
      return false;
    }
  };

  const cancelFromDurableState = (accountId: string, generationId: string): boolean => {
    const admitted = deps.messages.readHumanByGeneration(accountId, generationId);
    const events = deps.events.listAfter(accountId, generationId, null);
    if (admitted === null || events === null) {
      return failInterrupted(accountId, generationId);
    }
    const state: ActiveGeneration = {
      accountId,
      generationId,
      admitted,
      text: accumulatedText(events),
      run: null,
      runCancelled: false,
      terminal: false,
    };
    return finalize(state, "cancelled", state.text);
  };

  const supervisor: ChatGenerationSupervisor = Object.freeze({
    onAdmitted(input): void {
      const generationId = input.acceptedEvent.generationId;
      const key = keyOf(input.accountId, generationId);
      const lifecycle = deps.events.readLifecycle(input.accountId, generationId);
      if (lifecycle === null) {
        throw new TypeError("admitted chat generation event log disappeared");
      }
      if (lifecycle.state === "terminal") return;
      if (lifecycle.state === "cancellation_requested") {
        void cancelFromDurableState(input.accountId, generationId);
        return;
      }
      if (active.has(key)) return;
      const state: ActiveGeneration = {
        accountId: input.accountId,
        generationId,
        admitted: input.stored,
        text: "",
        run: null,
        runCancelled: false,
        terminal: false,
      };
      active.set(key, state);
      try {
        append(state, { kind: "snapshot", text: "" });
      } catch (error) {
        active.delete(key);
        throw error;
      }
      void Promise.all([
        deps.context.load({ accountId: input.accountId, admitted: input.stored }),
        Promise.resolve(deps.attachments.loadForGeneration({
          accountId: input.accountId,
          messageId: input.stored.message.id,
          attachments: input.stored.message.attachments ?? Object.freeze([]),
          nowEpochMilliseconds: deps.nowEpochMilliseconds(),
        })),
      ])
        .then(([context, attachments]) => {
          if (state.terminal) return;
          const run = deps.source.start({
            generationId,
            prompt: input.stored.message.text,
            context,
            attachments,
            onDelta(text): void {
              try {
                if (state.terminal || text.length === 0) return;
                append(state, { kind: "delta", text });
                state.text += text;
              } catch {
                void finalize(state, "failed", "");
              }
            },
            onComplete(): void {
              void finalize(state, "done", state.text);
            },
            onError(): void {
              void finalize(state, "done", FALLBACK_TEXT);
            },
          });
          state.run = run;
          if (state.terminal) cancelRun(state);
        })
        .catch(() => { void finalize(state, "done", FALLBACK_TEXT); });
    },

    cancel(accountId: string, generationId: string): void {
      const state = active.get(keyOf(accountId, generationId));
      queueMicrotask(() => {
        if (state !== undefined) void finalize(state, "cancelled", state.text);
        else void cancelFromDurableState(accountId, generationId);
      });
    },

    recoverInterrupted(): void {
      for (const lifecycle of deps.events.listUnterminated()) {
        const recovered = lifecycle.state === "cancellation_requested"
          ? cancelFromDurableState(lifecycle.accountId, lifecycle.generationId)
          : failInterrupted(lifecycle.accountId, lifecycle.generationId);
        if (recovered) {
          const key = keyOf(lifecycle.accountId, lifecycle.generationId);
          const state = active.get(key);
          if (state !== undefined) {
            state.terminal = true;
            cancelRun(state);
            active.delete(key);
          }
        }
      }
    },
  });

  return supervisor;
};
