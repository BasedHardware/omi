/** Platform Listen client evidence -> the surface's closed capture vocabulary. */

import type { PlatformListenCaptureClient } from "@omi-core/adapters-platform";
import type { StoreStatus } from "@omi-core/domain";
import type { Env } from "@omi-core/kernel";
import type { QueueStatus } from "@omi-core/sync";
import type { ListenEntitlementSnapshot, TranscriptSegment } from "@omi-core/wire-listen";
import type { ProductionListenStore } from "./ProductionListenStore.js";
import type { CaptureState } from "./capture-state.js";

const IDLE_QUEUE: QueueStatus = { phase: "idle", pendingCount: 0 };

function elapsedSeconds(startedAt: number | null, now: number): number {
  if (startedAt === null) return 0;
  return Math.max(0, Math.floor((now - startedAt) / 1_000));
}

function lastTranscribedSecond(segments: readonly TranscriptSegment[]): number {
  let last = 0;
  for (const segment of segments) {
    if (Number.isFinite(segment.end)) last = Math.max(last, segment.end);
  }
  return last;
}

function untranscribedSeconds(elapsed: number, segments: readonly TranscriptSegment[]): number {
  return Math.max(0, Math.ceil(elapsed - lastTranscribedSecond(segments)));
}

/**
 * Pure state fold. Entitlement pause wins over connectivity because its audio
 * is explicitly still buffering; reserved close 4020 and non-continuing
 * entitlement states win over idle/error because capture stopped at a named
 * ceiling. No `limit.amount` sentinel participates — callers branch on
 * `limit.kind` when presenting the ceiling.
 */
export function platformListenCaptureState(
  client: PlatformListenCaptureClient,
  now: number,
): CaptureState {
  const transport = client.snapshot();
  if (!transport.captureRequested) return { kind: "idle" };

  const stream = client.stream();
  const segments = stream.getTranscriptSegments();
  const elapsed = elapsedSeconds(transport.startedAt, transport.stoppedAt ?? now);
  const backlog = untranscribedSeconds(elapsed, segments);
  const entitlement = stream.getEntitlementState();

  const closeAdvice = stream.getListenCaptureCloseAdvice();
  if (closeAdvice?.entitlementExhaustion) {
    return { kind: "stopped-at-ceiling", untranscribedSeconds: backlog };
  }

  if (
    entitlement !== null
    && entitlement.status === "limit_reached"
    && entitlement.captureContinuing
  ) {
    return {
      kind: "paused-for-entitlement",
      elapsedSeconds: elapsed,
      untranscribedSeconds: backlog,
    };
  }

  if (
    entitlement !== null
    && !entitlement.captureContinuing
    && (entitlement.status === "limit_reached" || entitlement.status === "upgrade_required")
  ) {
    return { kind: "stopped-at-ceiling", untranscribedSeconds: backlog };
  }

  if (transport.phase === "reconnecting") {
    const bufferedSeconds = transport.disconnectedAt === null
      ? 0
      : Math.max(0, Math.floor((now - transport.disconnectedAt) / 1_000));
    return {
      kind: "offline-buffering",
      elapsedSeconds: elapsed,
      bufferedSeconds,
      untranscribedSeconds: Math.max(backlog, bufferedSeconds),
    };
  }

  if (transport.phase === "failed") {
    return {
      kind: "error",
      retryable: transport.failureRetryable ?? true,
      untranscribedSeconds: backlog,
    };
  }

  return { kind: "capturing", elapsedSeconds: elapsed, untranscribedSeconds: backlog };
}

function status(client: PlatformListenCaptureClient): StoreStatus {
  const snapshot = client.snapshot();
  const hasSavedData = client.stream().getTranscriptSegments().length > 0;
  const phase = snapshot.phase;
  return {
    refresh: {
      phase:
        phase === "connecting"
          ? "refreshing"
          : phase === "reconnecting" || phase === "failed"
            ? hasSavedData ? "saved-but-refresh-failed" : "unavailable"
            : "ready",
      hasSavedData,
    },
    queue: IDLE_QUEUE,
  };
}

/** Compose the transport client into the exact port rendered by ListenProduction. */
export function createPlatformProductionListenStore(
  client: PlatformListenCaptureClient,
  env: Env,
): ProductionListenStore {
  const listeners = new Set<() => void>();
  let unsubscribeClient: (() => void) | null = null;
  let cancelTick: (() => void) | null = null;

  const clockIsRunning = (): boolean => {
    const snapshot = client.snapshot();
    return snapshot.captureRequested && snapshot.stoppedAt === null;
  };
  const notify = (): void => {
    for (const listener of listeners) listener();
  };
  const scheduleTick = (): void => {
    if (listeners.size === 0 || !clockIsRunning()) {
      cancelTick?.();
      cancelTick = null;
      return;
    }
    if (cancelTick !== null) return;
    cancelTick = env.delay(1_000, () => {
      cancelTick = null;
      notify();
      scheduleTick();
    });
  };
  const clientChanged = (): void => {
    scheduleTick();
    notify();
  };

  return {
    status: () => status(client),
    subscribe(listener) {
      listeners.add(listener);
      if (unsubscribeClient === null) unsubscribeClient = client.subscribe(clientChanged);
      scheduleTick();
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) {
          cancelTick?.();
          cancelTick = null;
          unsubscribeClient?.();
          unsubscribeClient = null;
        }
      };
    },
    refresh: () => client.refresh(),
    captureState: () => platformListenCaptureState(client, env.now()),
    transcriptSegments: () => client.stream().getTranscriptSegments(),
    entitlementState: (): ListenEntitlementSnapshot | null => client.stream().getEntitlementState(),
    start: () => client.start(),
    stop: () => client.stop(),
  };
}
