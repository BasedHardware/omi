import type { ChatGenerationAttachmentDescriptor } from "./attachment-content";
import type { ChatGenerationMemoryContext } from "./generation-context";

export interface ChatGenerationSourceInput {
  readonly generationId: string;
  readonly prompt: string;
  /** Authorized memory context; providers must preserve its incompleteness semantics. */
  readonly context: ChatGenerationMemoryContext;
  readonly attachments: readonly ChatGenerationAttachmentDescriptor[];
  readonly onDelta: (text: string) => void;
  readonly onComplete: () => void;
  readonly onError: (error: unknown) => void;
}

export interface ChatGenerationSourceRun {
  cancel(): void;
}

/** A timer seam kept deliberately smaller than any platform timer API. */
export interface ChatGenerationScheduler {
  setTimeout(callback: () => void, delayMs: number): unknown;
  clearTimeout(handle: unknown): void;
}

export interface ChatGenerationSourceCapabilityReceipt {
  readonly tier: "deterministic-scripted" | "real-provider" | "unknown";
  readonly adapter: string;
  readonly deterministic: boolean;
}

/**
 * Providers may report a self-declared tier; this is an internal declaration,
 * never proof that a provider is live or that a model was contacted.
 */
export interface ChatGenerationSource {
  readonly capability?: ChatGenerationSourceCapabilityReceipt;
  start(input: ChatGenerationSourceInput): ChatGenerationSourceRun;
}

export const realtimeChatGenerationScheduler: ChatGenerationScheduler = Object.freeze({
  setTimeout: (callback, delayMs) => setTimeout(callback, delayMs),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
});

const UNKNOWN_CAPABILITY: ChatGenerationSourceCapabilityReceipt = Object.freeze({
  tier: "unknown",
  adapter: "unreported",
  deterministic: false,
});

const CAPABILITY_KEYS = Object.freeze(["adapter", "deterministic", "tier"]);
const SAFE_ADAPTER = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/u;

const unknownCapability = (): ChatGenerationSourceCapabilityReceipt => UNKNOWN_CAPABILITY;

const canonicalCapability = (candidate: unknown): ChatGenerationSourceCapabilityReceipt => {
  try {
    if (candidate === null || typeof candidate !== "object") return unknownCapability();
    const prototype = Object.getPrototypeOf(candidate);
    if (prototype !== Object.prototype && prototype !== null) return unknownCapability();
    const keys = Reflect.ownKeys(candidate);
    if (keys.length !== CAPABILITY_KEYS.length
      || keys.some((key) => typeof key !== "string" || !CAPABILITY_KEYS.includes(key))) {
      return unknownCapability();
    }
    const descriptors = Object.getOwnPropertyDescriptors(candidate);
    const adapterDescriptor = descriptors.adapter;
    const deterministicDescriptor = descriptors.deterministic;
    const tierDescriptor = descriptors.tier;
    if (adapterDescriptor === undefined || deterministicDescriptor === undefined
      || tierDescriptor === undefined || !("value" in adapterDescriptor)
      || !("value" in deterministicDescriptor) || !("value" in tierDescriptor)) {
      return unknownCapability();
    }
    const adapter = adapterDescriptor.value;
    const deterministic = deterministicDescriptor.value;
    const tier = tierDescriptor.value;
    if (typeof adapter !== "string" || !SAFE_ADAPTER.test(adapter)
      || typeof deterministic !== "boolean"
      || (tier !== "deterministic-scripted" && tier !== "real-provider" && tier !== "unknown")
      || (tier === "deterministic-scripted" && deterministic !== true)
      || (tier !== "deterministic-scripted" && deterministic !== false)) {
      return unknownCapability();
    }
    return Object.freeze({ tier, adapter, deterministic });
  } catch {
    return unknownCapability();
  }
};

export const readChatGenerationSourceCapability = (
  source: ChatGenerationSource,
): ChatGenerationSourceCapabilityReceipt => {
  try {
    // Capability declarations are untrusted input. Read only an own data
    // descriptor so inherited values and accessor/proxy getters cannot run
    // while a receipt is being inspected.
    if (source === null || typeof source !== "object") return unknownCapability();
    const descriptor = Object.getOwnPropertyDescriptor(source, "capability");
    if (descriptor === undefined || !("value" in descriptor)) return unknownCapability();
    return canonicalCapability(descriptor.value);
  } catch {
    return unknownCapability();
  }
};

export interface ScriptedChatGenerationStep {
  readonly delayMs: number;
  readonly text: string;
}

const DEFAULT_SCRIPT: readonly ScriptedChatGenerationStep[] = Object.freeze([
  Object.freeze({ delayMs: 25, text: "Local generation " }),
  Object.freeze({ delayMs: 40, text: "is connected." }),
]);

const validateStep = (step: ScriptedChatGenerationStep): ScriptedChatGenerationStep => {
  if (!Number.isSafeInteger(step.delayMs) || step.delayMs < 0
    || typeof step.text !== "string" || step.text.length === 0) {
    throw new TypeError("invalid scripted chat generation step");
  }
  return Object.freeze({ delayMs: step.delayMs, text: step.text });
};

/** Deterministic dev adapter with provider-like, real elapsed timing. */
export const createScriptedChatGenerationSource = (
  script: readonly ScriptedChatGenerationStep[] = DEFAULT_SCRIPT,
  scheduler: ChatGenerationScheduler = realtimeChatGenerationScheduler,
): ChatGenerationSource => {
  const steps = Object.freeze(script.map(validateStep));
  return Object.freeze({
    capability: Object.freeze({
      tier: "deterministic-scripted" as const,
      adapter: "scripted-chat-generation",
      deterministic: true,
    }),
    start(input): ChatGenerationSourceRun {
      let cancelled = false;
      const timers: unknown[] = [];
      let elapsed = 0;
      for (const [index, step] of steps.entries()) {
        elapsed += step.delayMs;
        timers.push(scheduler.setTimeout(() => {
          if (cancelled) return;
          try {
            input.onDelta(step.text);
            if (index === steps.length - 1) input.onComplete();
          } catch (error) {
            input.onError(error);
          }
        }, elapsed));
      }
      if (steps.length === 0) {
        timers.push(scheduler.setTimeout(() => {
          if (!cancelled) input.onComplete();
        }, 0));
      }
      return Object.freeze({
        cancel(): void {
          cancelled = true;
          for (const timer of timers) scheduler.clearTimeout(timer);
        },
      });
    },
  });
};
