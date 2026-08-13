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

/** Production LLM providers plug in here; the supervisor owns all wire behavior. */
export interface ChatGenerationSource {
  start(input: ChatGenerationSourceInput): ChatGenerationSourceRun;
}

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
): ChatGenerationSource => {
  const steps = Object.freeze(script.map(validateStep));
  return Object.freeze({
    start(input): ChatGenerationSourceRun {
      let cancelled = false;
      const timers: ReturnType<typeof setTimeout>[] = [];
      let elapsed = 0;
      for (const [index, step] of steps.entries()) {
        elapsed += step.delayMs;
        timers.push(setTimeout(() => {
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
        timers.push(setTimeout(() => {
          if (!cancelled) input.onComplete();
        }, 0));
      }
      return Object.freeze({
        cancel(): void {
          cancelled = true;
          for (const timer of timers) clearTimeout(timer);
        },
      });
    },
  });
};
