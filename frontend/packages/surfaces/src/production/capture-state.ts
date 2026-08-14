/**
 * Closed union. Every capture state is user-visible and named (hard rule 6).
 * Owned here so this module stays free of relative imports; the surface port
 * re-exports the type.
 */
export type CaptureState =
  | { readonly kind: "loading" }
  | { readonly kind: "idle" }
  | {
      readonly kind: "capturing";
      readonly elapsedSeconds: number;
      readonly untranscribedSeconds: number;
    }
  | {
      readonly kind: "paused-for-entitlement";
      readonly elapsedSeconds: number;
      readonly untranscribedSeconds: number;
    }
  | {
      readonly kind: "offline-buffering";
      readonly elapsedSeconds: number;
      readonly bufferedSeconds: number;
      readonly untranscribedSeconds: number;
    }
  | { readonly kind: "stopped-at-ceiling"; readonly untranscribedSeconds: number }
  | {
      readonly kind: "error";
      readonly retryable: boolean;
      readonly untranscribedSeconds: number;
    };

/** Title keys used by describeCapture — all are zero-argument catalog entries. */
export type CaptureTitleKey =
  | "listen.stateLoading"
  | "listen.stateIdle"
  | "listen.stateCapturing"
  | "listen.statePausedEntitlement"
  | "listen.stateOfflineBuffering"
  | "listen.stateStoppedAtCeiling"
  | "listen.errorTitle";

/** Body keys used by describeCapture — all are zero-argument catalog entries. */
export type CaptureBodyKey =
  | "listen.stateLoadingBody"
  | "listen.stateIdleBody"
  | "listen.stateCapturingBody"
  | "listen.statePausedEntitlementBody"
  | "listen.stateOfflineBufferingBody"
  | "listen.stateStoppedAtCeilingBody"
  | "common.unknownError";

export type CaptureDescription = {
  readonly titleKey: CaptureTitleKey;
  readonly bodyKey: CaptureBodyKey;
  /** True when audio is still being captured right now. */
  readonly capturing: boolean;
  /** Must be announced assertively (`role="alert"`). */
  readonly loud: boolean;
  /** Seconds awaiting transcription; 0 when nothing is waiting. */
  readonly backlogSeconds: number;
  readonly canStart: boolean;
  readonly canStop: boolean;
};

/**
 * Map a capture state to presentation flags and catalog keys.
 *
 * The four live / stopped modes are deliberately non-interchangeable: an idle
 * presentation must never stand in for a storage-ceiling stop (silent frame
 * drop), and an entitlement pause must never look like a stop (audio is still
 * being buffered).
 */
export function describeCapture(state: CaptureState): CaptureDescription {
  switch (state.kind) {
    case "loading":
      return {
        titleKey: "listen.stateLoading",
        bodyKey: "listen.stateLoadingBody",
        capturing: false,
        loud: false,
        backlogSeconds: 0,
        canStart: false,
        canStop: false,
      };
    case "idle":
      return {
        titleKey: "listen.stateIdle",
        bodyKey: "listen.stateIdleBody",
        capturing: false,
        loud: false,
        backlogSeconds: 0,
        canStart: true,
        canStop: false,
      };
    case "capturing":
      return {
        titleKey: "listen.stateCapturing",
        bodyKey: "listen.stateCapturingBody",
        capturing: true,
        loud: false,
        backlogSeconds: state.untranscribedSeconds,
        canStart: false,
        canStop: true,
      };
    case "paused-for-entitlement":
      return {
        titleKey: "listen.statePausedEntitlement",
        bodyKey: "listen.statePausedEntitlementBody",
        capturing: true,
        loud: false,
        backlogSeconds: state.untranscribedSeconds,
        canStart: false,
        canStop: true,
      };
    case "offline-buffering":
      return {
        titleKey: "listen.stateOfflineBuffering",
        bodyKey: "listen.stateOfflineBufferingBody",
        capturing: true,
        loud: false,
        backlogSeconds: state.untranscribedSeconds,
        canStart: false,
        canStop: true,
      };
    case "stopped-at-ceiling":
      return {
        titleKey: "listen.stateStoppedAtCeiling",
        bodyKey: "listen.stateStoppedAtCeilingBody",
        capturing: false,
        loud: true,
        backlogSeconds: state.untranscribedSeconds,
        canStart: false,
        canStop: false,
      };
    case "error":
      return {
        titleKey: "listen.errorTitle",
        // No listen.errorBody in the frozen catalog — closest shared copy.
        bodyKey: "common.unknownError",
        capturing: false,
        loud: !state.retryable,
        backlogSeconds: state.untranscribedSeconds,
        canStart: state.retryable,
        canStop: false,
      };
    default: {
      const _exhaustive: never = state;
      throw new Error(`unhandled capture kind: ${JSON.stringify(_exhaustive)}`);
    }
  }
}

/**
 * Convert a backlog duration in seconds to hours for `listen.backlogHours`.
 *
 * Rounding rule: ceil to whole hours so any non-zero backlog reports at least
 * one hour. A backlog that exists must never render as "nothing waiting"
 * (`Math.floor(seconds / 3600)` would collapse one minute to 0). Zero stays 0.
 */
export function backlogHours(seconds: number): number {
  if (!Number.isFinite(seconds) || seconds <= 0) return 0;
  return Math.ceil(seconds / 3600);
}
