import { createInMemoryLocalServiceStores } from "../app-facing";
import type { ChatAttachmentContentPort } from "./attachment-content";
import {
  type ChatGenerationContextSource,
} from "./generation-context";
import {
  createChatGenerationSupervisor,
  type ChatGenerationFailureCode,
} from "./generation-supervisor";
import {
  createScriptedChatGenerationSource,
  registerChatGenerationSourceCapability,
  readChatGenerationSourceCapability,
  type ChatGenerationScheduler,
  type ChatGenerationSource,
  type ChatGenerationSourceCapabilityReceipt,
  type ScriptedChatGenerationStep,
} from "./generation-source";
import type {
  ChatGenerationEvent,
  ChatGenerationEventsStore,
} from "../stores/chat-generation-events-store";
import type { ChatMessageRecord } from "../stores/chat-messages-store";

/** Small deterministic scheduler used by Chat scenarios and unit tests. */
export class DeterministicChatGenerationScheduler implements ChatGenerationScheduler {
  private readonly timers = new Map<number, { readonly at: number; readonly callback: () => void }>();
  private nextId = 1;
  private currentTime = 0;

  get now(): number {
    return this.currentTime;
  }

  setTimeout(callback: () => void, delayMs: number): number {
    if (!Number.isSafeInteger(delayMs) || delayMs < 0) throw new TypeError("invalid delay");
    const id = this.nextId++;
    this.timers.set(id, { at: this.currentTime + delayMs, callback });
    return id;
  }

  clearTimeout(handle: unknown): void {
    if (typeof handle === "number") this.timers.delete(handle);
  }

  /** Runs one timer in insertion order, advancing virtual time to its deadline. */
  runNext(): boolean {
    const next = [...this.timers.entries()]
      .sort(([leftId, left], [rightId, right]) => left.at - right.at || leftId - rightId)[0];
    if (next === undefined) return false;
    this.timers.delete(next[0]);
    this.currentTime = next[1].at;
    next[1].callback();
    return true;
  }

  get pending(): number {
    return this.timers.size;
  }
}

export interface ChatGenerationScenario {
  readonly generationId?: string;
  readonly prompt: string;
  readonly context?: readonly string[];
  readonly script?: readonly ScriptedChatGenerationStep[];
  readonly sourceErrorAtMs?: number;
  readonly contextError?: boolean;
  readonly attachmentError?: boolean;
  readonly cancelAtMs?: number;
  readonly timeoutAtMs?: number;
  readonly callbackFault?: "delta";
}

export interface ChatGenerationScenarioTraceEntry {
  readonly atMs: number;
  readonly kind: ChatGenerationEvent["frame"]["kind"];
  readonly text?: string;
  readonly errorCode?: ChatGenerationFailureCode;
}

export interface ChatGenerationScenarioResult {
  readonly capability: ChatGenerationSourceCapabilityReceipt;
  readonly trace: readonly ChatGenerationScenarioTraceEntry[];
  readonly terminal: "done" | "failed" | "cancelled" | null;
}

const SCENARIO_ACCOUNT = "scenario-account";

const scenarioMessage = (scenario: ChatGenerationScenario, generationId: string): ChatMessageRecord =>
  Object.freeze({
    id: `human-${generationId}`,
    text: scenario.prompt,
    sender: "human",
    type: "text",
    createdAt: 0,
    updatedAt: 0,
    chatSessionId: null,
    appId: null,
    journalRevision: 1,
    payloadHash: `sha256:scenario-${generationId}`,
    messageSource: "chat_scenario",
    rating: null,
    reported: false,
    revision: `revision-human-${generationId}`,
    attachments: Object.freeze([]),
  });

const sourceWithFault = (
  scenario: ChatGenerationScenario,
  scheduler: DeterministicChatGenerationScheduler,
): ChatGenerationSource => {
  const scripted = createScriptedChatGenerationSource(scenario.script ?? [], scheduler);
  const source: ChatGenerationSource = Object.freeze({
    capability: scripted.capability,
    start(input) {
      const run = scripted.start(input);
      const errorTimer = scenario.sourceErrorAtMs === undefined
        ? null
        : scheduler.setTimeout(() => input.onError(new Error("scenario provider fault")), scenario.sourceErrorAtMs);
      return Object.freeze({
        cancel(): void {
          run.cancel();
          if (errorTimer !== null) scheduler.clearTimeout(errorTimer);
        },
      });
    },
  });
  return registerChatGenerationSourceCapability(source, {
    tier: "deterministic-scripted",
    adapter: "scripted-chat-generation",
    deterministic: true,
  });
};

const contextFor = (
  scenario: ChatGenerationScenario,
): ChatGenerationContextSource => Object.freeze({
  async load() {
    if (scenario.contextError === true) throw new Error("scenario context fault");
    return Object.freeze([...(scenario.context ?? [])]);
  },
});

const traceOf = (
  events: readonly ChatGenerationEvent[],
): readonly ChatGenerationScenarioTraceEntry[] => Object.freeze(events
  .filter((event) => event.frame.kind !== "accepted")
  .map((event) => {
    const frame = event.frame;
    if (frame.kind === "delta" || frame.kind === "snapshot") {
      return Object.freeze({ atMs: event.createdAt, kind: frame.kind, text: frame.text });
    }
    if (frame.kind === "failed") {
      const errorCode: ChatGenerationFailureCode = [
        "generation_provider_failed",
        "generation_context_failed",
        "generation_attachment_failed",
        "generation_interrupted",
        "generation_timeout",
      ].includes(frame.error.code)
        ? frame.error.code as ChatGenerationFailureCode
        : "generation_provider_failed";
      return Object.freeze({ atMs: event.createdAt, kind: frame.kind, errorCode });
    }
    return Object.freeze({ atMs: event.createdAt, kind: frame.kind });
  }));

/**
 * Runs one declarative Chat lifecycle without wall-clock sleeps. The returned
 * trace is durable-event based, so rerunning the same scenario is byte-stable.
 */
export const runChatGenerationScenario = async (
  scenario: ChatGenerationScenario,
): Promise<ChatGenerationScenarioResult> => {
  const generationId = scenario.generationId ?? "scenario-generation";
  const scheduler = new DeterministicChatGenerationScheduler();
  const stores = createInMemoryLocalServiceStores();
  const baseEvents = stores.chatEvents;
  let callbackFaultInjected = scenario.callbackFault === "delta";
  const events: ChatGenerationEventsStore = scenario.callbackFault === undefined
    ? baseEvents
    : Object.freeze({
        append(input) {
          if (input.frame.kind === "delta" && callbackFaultInjected) {
            callbackFaultInjected = false;
            throw new Error("scenario callback fault");
          }
          return baseEvents.append(input);
        },
        listAfter: baseEvents.listAfter,
        readLifecycle: baseEvents.readLifecycle,
        listUnterminated: baseEvents.listUnterminated,
        requestCancellation: baseEvents.requestCancellation,
        reset: baseEvents.reset,
      });
  const source = sourceWithFault(scenario, scheduler);
  const attachments: ChatAttachmentContentPort = scenario.attachmentError === true
    ? Object.freeze({
        loadForGeneration(): never {
          throw new Error("scenario attachment fault");
        },
      })
    : stores.chatAttachments;
  const supervisor = createChatGenerationSupervisor({
    source,
    context: contextFor(scenario),
    messages: stores.chatMessages,
    events,
    finalization: stores.chatFinalization,
    attachments,
    nowEpochMilliseconds: () => scheduler.now,
    assistantMessageId: (_accountId, id) => `assistant-${id}`,
    eventId: (_accountId, id, kind, sequence) => `event-${id}-${kind}-${sequence}`,
    revision: (_accountId, id, hash) => `revision-${id}-${hash}`,
  });
  if (scenario.cancelAtMs !== undefined) {
    scheduler.setTimeout(() => supervisor.cancel(SCENARIO_ACCOUNT, generationId), scenario.cancelAtMs);
  }
  if (scenario.timeoutAtMs !== undefined) {
    scheduler.setTimeout(() => supervisor.timeout?.(SCENARIO_ACCOUNT, generationId), scenario.timeoutAtMs);
  }
  const admission = stores.chatAdmission.admit({
    accountId: SCENARIO_ACCOUNT,
    message: scenarioMessage(scenario, generationId),
    generationId,
    acceptedEventId: `event-${generationId}-accepted`,
    admittedAt: scheduler.now,
    attachmentIds: [],
  });
  if (admission.kind !== "created") throw new TypeError(`scenario admission failed: ${admission.kind}`);
  supervisor.onAdmitted({
    accountId: SCENARIO_ACCOUNT,
    stored: admission.stored,
    acceptedEvent: admission.acceptedEvent,
    bearerToken: "scenario-token",
  });

  // Context loading and terminalization are Promise callbacks. Flush those
  // microtasks between virtual timer turns without introducing real sleeps.
  let idleTurns = 0;
  for (let turns = 0; turns < 1_000; turns += 1) {
    await Promise.resolve();
    await Promise.resolve();
    const ran = scheduler.runNext();
    await Promise.resolve();
    const current = baseEvents.listAfter(SCENARIO_ACCOUNT, generationId, null) ?? [];
    const hasTerminal = current.some((event) =>
      event.frame.kind === "done" || event.frame.kind === "failed" || event.frame.kind === "cancelled");
    if (hasTerminal && scheduler.pending === 0) break;
    if (ran) idleTurns = 0;
    else if ((idleTurns += 1) > 10 && scheduler.pending === 0) break;
  }
  await Promise.resolve();
  const durable = baseEvents.listAfter(SCENARIO_ACCOUNT, generationId, null) ?? [];
  const terminal = durable.filter((event) =>
    event.frame.kind === "done" || event.frame.kind === "failed" || event.frame.kind === "cancelled");
  return Object.freeze({
    capability: readChatGenerationSourceCapability(source),
    trace: traceOf(durable),
    terminal: terminal.length === 1 ? terminal[0]!.frame.kind as "done" | "failed" | "cancelled" : null,
  });
};
