// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import { createHash } from "node:crypto";

import {
  snapshotChatGenerationMemoryContext,
  type ChatGenerationContextSource,
  type ChatGenerationMemoryContext,
} from "./generation-context";
import type {
  ChatAttachmentContentPort,
  ChatGenerationAttachmentDescriptor,
} from "./attachment-content";
import type { ChatGenerationSource, ChatGenerationSourceRun } from "./generation-source";
import type { ChatGenerationEvent } from "../stores/chat-generation-events-store";
import type { ChatGenerationEventsStore } from "../stores/chat-generation-events-store";
import type { ChatGenerationFinalization } from "../stores/chat-generation-finalization";
import type { ChatMessageRecord, ChatMessagesStore, StoredChatMessage } from "../stores/chat-messages-store";

export interface AdmittedChatGeneration {
  readonly accountId: string;
  readonly stored: StoredChatMessage;
  readonly acceptedEvent: ChatGenerationEvent;
  /** Ephemeral request credential used only by the injected context source. */
  readonly bearerToken: string;
}

export interface ChatGenerationSupervisor {
  onAdmitted(input: AdmittedChatGeneration): void;
  cancel(accountId: string, generationId: string): void;
  /** Optional fault-injection seam; production timeouts can adopt this later. */
  timeout?(accountId: string, generationId: string): void;
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
  failure: ChatGenerationFailure | null;
}

const FALLBACK_TEXT = "I’m sorry, I couldn’t complete that response.";

export type ChatGenerationFailureCode =
  | "generation_provider_failed"
  | "generation_context_failed"
  | "generation_attachment_failed"
  | "generation_interrupted"
  | "generation_timeout";

export interface ChatGenerationFailure {
  readonly code: ChatGenerationFailureCode;
  readonly retryable: boolean;
}

const defaultFailure = (
  stage: "provider" | "context" | "attachment" | "callback" | "timeout",
): ChatGenerationFailure => stage === "context"
  ? { code: "generation_context_failed", retryable: true }
  : stage === "attachment"
    ? { code: "generation_attachment_failed", retryable: true }
    : stage === "callback"
      ? { code: "generation_interrupted", retryable: true }
      : stage === "timeout"
        ? { code: "generation_timeout", retryable: true }
        : { code: "generation_provider_failed", retryable: true };

/** Reads only own data properties; hostile getters/proxies fail closed. */
const readFailureDeclaration = (
  error: unknown,
): Readonly<{ readonly code: unknown; readonly retryable: unknown }> | null => {
  try {
    if (error === null || typeof error !== "object") return null;
    const code = Object.getOwnPropertyDescriptor(error, "code");
    const retryable = Object.getOwnPropertyDescriptor(error, "retryable");
    if (code === undefined || retryable === undefined
      || !("value" in code) || !("value" in retryable)) return null;
    return Object.freeze({ code: code.value, retryable: retryable.value });
  } catch {
    return null;
  }
};

const classifyFailure = (
  error: unknown,
  stage: "provider" | "context" | "attachment" | "callback" | "timeout",
): ChatGenerationFailure => {
  try {
    const candidate = readFailureDeclaration(error);
    const allowed = stage === "provider"
      ? ["generation_provider_failed", "generation_timeout"]
      : stage === "context"
        ? ["generation_context_failed", "generation_timeout"]
        : stage === "attachment"
          ? ["generation_attachment_failed", "generation_timeout"]
          : stage === "callback"
            ? ["generation_interrupted", "generation_timeout"]
            : ["generation_timeout"];
    if (candidate !== null && typeof candidate.code === "string"
      && allowed.includes(candidate.code) && typeof candidate.retryable === "boolean") {
      return { code: candidate.code as ChatGenerationFailureCode, retryable: candidate.retryable };
    }
  } catch {
    // Treat all malformed declarations, including adversarial proxies, as an
    // untyped failure at the current boundary.
  }
  return defaultFailure(stage);
};

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
    failure: ChatGenerationFailure | null = null,
  ): boolean => {
    if (state.terminal) return true;
    if (kind === "done" && state.failure !== null) {
      kind = "failed";
      text = "";
      failure = state.failure;
    }
    if (kind === "failed") state.failure = failure ?? classifyFailure(null, "provider");
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
              error: state.failure!,
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

  const failInterrupted = (
    accountId: string,
    generationId: string,
    failure: ChatGenerationFailure = { code: "generation_interrupted", retryable: true },
  ): boolean => {
    try {
      const prior = deps.events.listAfter(accountId, generationId, null);
      // A timeout/recovery callback must never manufacture a terminal for a
      // generation that has no durable admission record.
      if (prior === null || !prior.some((event) => event.frame.kind === "accepted")) return false;
      deps.finalization.finalize({
        accountId,
        generationId,
        eventId: deps.eventId(accountId, generationId, "failed", prior.length + 1),
        createdAt: deps.nowEpochMilliseconds(),
        frame: {
          kind: "failed",
          error: failure,
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
      failure: null,
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
        failure: null,
      };
      active.set(key, state);
      try {
        append(state, { kind: "snapshot", text: "" });
      } catch (error) {
        active.delete(key);
        throw error;
      }
      void (async (): Promise<void> => {
        // Credential is passed only into this load and is never retained in
        // active or durable generation state. Hostile or undeclarable memory
        // envelopes fail the generation as a typed context fault; authorized
        // memory-read unavailability is represented by the context source
        // itself, not by swallowing the error here.
        let context: ChatGenerationMemoryContext;
        try {
          const loaded = snapshotChatGenerationMemoryContext(await deps.context.load({
            accountId: input.accountId,
            admitted: input.stored,
            bearerToken: input.bearerToken,
          }));
          if (loaded === null) throw new TypeError("untrusted generation context");
          context = loaded;
        } catch (error) {
          void finalize(state, "failed", "", classifyFailure(error, "context"));
          return;
        }
        if (state.terminal) return;
        let attachments: readonly ChatGenerationAttachmentDescriptor[];
        try {
          attachments = await deps.attachments.loadForGeneration({
            accountId: input.accountId,
            messageId: input.stored.message.id,
            attachments: input.stored.message.attachments ?? Object.freeze([]),
            nowEpochMilliseconds: deps.nowEpochMilliseconds(),
          });
        } catch (error) {
          void finalize(state, "failed", "", classifyFailure(error, "attachment"));
          return;
        }
        if (state.terminal) return;
        try {
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
                void finalize(state, "failed", "", classifyFailure(null, "callback"));
              }
            },
            onComplete(): void {
              void finalize(state, "done", state.text);
            },
            onError(error): void {
              void finalize(state, "failed", "", classifyFailure(error, "provider"));
            },
          });
          state.run = run;
          if (state.terminal) cancelRun(state);
        } catch (error) {
          void finalize(state, "failed", "", classifyFailure(error, "provider"));
        }
      })();
    },

    cancel(accountId: string, generationId: string): void {
      const state = active.get(keyOf(accountId, generationId));
      queueMicrotask(() => {
        if (state !== undefined) void finalize(state, "cancelled", state.text);
        else void cancelFromDurableState(accountId, generationId);
      });
    },

    timeout(accountId: string, generationId: string): void {
      const state = active.get(keyOf(accountId, generationId));
      queueMicrotask(() => {
        if (state !== undefined) {
          void finalize(
            state,
            "failed",
            "",
            { code: "generation_timeout", retryable: true },
          );
        } else {
          void failInterrupted(accountId, generationId, {
            code: "generation_timeout",
            retryable: true,
          });
        }
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
