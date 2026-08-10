// domain-pending(DIV-DOMCORE-012)

import type { ListenTranscriptSegment } from "../stores/listen-store";

export interface TranscriptionEmission {
  readonly segment: ListenTranscriptSegment;
  /** Real provider time consumed by this accepted transcript result. */
  readonly consumedSeconds: number;
}

export interface TranscriptionConnection {
  writeAudio(chunk: Uint8Array): void;
  /** Stops accepting new audio; already accepted work is allowed to settle. */
  finish(): void;
}

export interface TranscriptionSource {
  connect(input: {
    readonly sessionId: string;
    readonly sampleRate: number;
    readonly codec: string;
    readonly channels: number;
    readonly onEmission: (emission: TranscriptionEmission) => void;
    readonly onError: (error: unknown) => void;
  }): TranscriptionConnection;
}

export interface ScriptedTranscriptionStep {
  /** Provider-like latency after the corresponding binary audio frame. */
  readonly delayMs: number;
  readonly text: string;
  readonly start: number;
  readonly end: number;
  readonly isUser?: boolean;
  readonly consumedSeconds?: number;
}

const DEFAULT_SCRIPT: readonly ScriptedTranscriptionStep[] = Object.freeze([
  Object.freeze({ delayMs: 25, text: "Local transcription is connected.", start: 0, end: 1 }),
  Object.freeze({ delayMs: 40, text: "This segment arrived with real timing.", start: 1, end: 2 }),
]);

const validateStep = (step: ScriptedTranscriptionStep): ScriptedTranscriptionStep => {
  const consumed = step.consumedSeconds ?? step.end - step.start;
  if (!Number.isInteger(step.delayMs) || step.delayMs < 0
    || typeof step.text !== "string"
    || !Number.isFinite(step.start) || step.start < 0
    || !Number.isFinite(step.end) || step.end < step.start
    || !Number.isFinite(consumed) || consumed < 0) {
    throw new TypeError("invalid scripted transcription step");
  }
  return Object.freeze({ ...step });
};

/**
 * Deterministic local STT adapter.
 *
 * One binary audio frame advances one script step. Emission uses a real timer,
 * and cursors live at the adapter level so reconnecting the same durable
 * session never reuses an id for different content.
 */
export const createScriptedTranscriptionSource = (
  script: readonly ScriptedTranscriptionStep[] = DEFAULT_SCRIPT,
): TranscriptionSource => {
  const steps = Object.freeze(script.map(validateStep));
  const cursors = new Map<string, number>();

  return Object.freeze({
    connect(input): TranscriptionConnection {
      let accepting = true;
      return Object.freeze({
        writeAudio(chunk: Uint8Array): void {
          if (!accepting || chunk.byteLength <= 2) return;
          const index = cursors.get(input.sessionId) ?? 0;
          const step = steps[index];
          if (step === undefined) return;
          cursors.set(input.sessionId, index + 1);
          setTimeout(() => {
            try {
              input.onEmission(Object.freeze({
                segment: Object.freeze({
                  id: `${input.sessionId}:scripted:${String(index + 1).padStart(4, "0")}`,
                  text: step.text,
                  is_user: step.isUser ?? false,
                  start: step.start,
                  end: step.end,
                }),
                consumedSeconds: step.consumedSeconds ?? step.end - step.start,
              }));
            } catch (error) {
              input.onError(error);
            }
          }, step.delayMs);
        },

        finish(): void {
          accepting = false;
        },
      });
    },
  });
};
