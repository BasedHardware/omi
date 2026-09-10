import type { GenerationEvent } from "./wire";

export const CHAT_GENERATION_SSE_HEARTBEAT_INTERVAL_MS = 5_000;
export const CHAT_GENERATION_SSE_HEARTBEAT = ": heartbeat\n\n";

export function openLiveGenerationSse(
  encode: (event: GenerationEvent) => string,
  existing: readonly GenerationEvent[],
  subscribe: (listener: (event: GenerationEvent) => void) => () => void,
  isTerminal: (event: GenerationEvent) => boolean,
  heartbeatIntervalMs: number = CHAT_GENERATION_SSE_HEARTBEAT_INTERVAL_MS
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let unsubscribe: (() => void) | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  const stop = (): void => {
    if (stopped) return;
    stopped = true;
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    unsubscribe?.();
  };
  return new ReadableStream<Uint8Array>({
    start(controller) {
      const armHeartbeat = (): void => {
        if (heartbeatIntervalMs <= 0 || stopped) return;
        if (timer !== undefined) clearTimeout(timer);
        timer = setTimeout(() => {
          if (stopped) return;
          try {
            controller.enqueue(encoder.encode(CHAT_GENERATION_SSE_HEARTBEAT));
            armHeartbeat();
          } catch {
            stop();
          }
        }, heartbeatIntervalMs);
      };
      const emit = (event: GenerationEvent): void => {
        controller.enqueue(encoder.encode(encode(event)));
        armHeartbeat();
      };
      for (const event of existing) emit(event);
      if (existing.length === 0) armHeartbeat();
      unsubscribe = subscribe((event) => {
        if (stopped) return;
        try {
          emit(event);
          if (isTerminal(event)) {
            stop();
            controller.close();
          }
        } catch {
          stop();
        }
      });
    },
    cancel() {
      stop();
    },
  });
}
