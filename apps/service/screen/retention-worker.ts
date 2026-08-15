// domain-pending(DIV-DOMAPPS-007)
// domain-pending(UNK-DOMAPPS-001)

import type {
  ScreenRetentionSweepReport,
  ScreenStore,
} from "../stores/screen-store";

/** Parity with the legacy desktop sweep: at most every six hours. */
export const SCREEN_RETENTION_INTERVAL_MS = 6 * 60 * 60 * 1000;

export interface ScreenRetentionTimer {
  unref?: () => void;
}

export interface ScreenRetentionWorker {
  readonly sweep: () => ScreenRetentionSweepReport;
  readonly stop: () => void;
}

export interface ScreenRetentionWorkerInput {
  readonly store: ScreenStore;
  readonly now: () => string;
  /** 0 disables the repeating timer; boot sweep still runs. */
  readonly intervalMs?: number;
  readonly schedule?: (
    tick: () => void,
    intervalMs: number,
  ) => ScreenRetentionTimer & { readonly close?: () => void };
  readonly clear?: (timer: ScreenRetentionTimer) => void;
}

/**
 * Enforces the owner's retention setting against rows the service owns
 * (frame metadata + OCR). Chunk files stay on the client; retired frame_refs
 * are listed from the store so the native lane can garbage-collect them.
 */
export const createScreenRetentionWorker = (
  input: ScreenRetentionWorkerInput,
): ScreenRetentionWorker => {
  const intervalMs = input.intervalMs ?? SCREEN_RETENTION_INTERVAL_MS;
  if (!Number.isFinite(intervalMs) || intervalMs < 0) {
    throw new TypeError("invalid screen retention interval");
  }
  const sweep = (): ScreenRetentionSweepReport => input.store.sweepRetention(input.now());
  sweep();
  if (intervalMs === 0) {
    return Object.freeze({ sweep, stop: () => {} });
  }
  const schedule = input.schedule ?? ((tick, ms) => {
    const timer = setInterval(tick, ms);
    timer.unref?.();
    return timer;
  });
  const timer = schedule(sweep, intervalMs);
  timer.unref?.();
  const clear = input.clear ?? ((handle) => {
    clearInterval(handle as ReturnType<typeof setInterval>);
  });
  let stopped = false;
  return Object.freeze({
    sweep,
    stop: () => {
      if (stopped) return;
      stopped = true;
      clear(timer);
    },
  });
};
