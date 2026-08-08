import type { QueuePhase, QueueStatus } from "@omi-core/sync";
import type { RefreshPhase, StoreStatus } from "@omi-core/domain";
import type { CaptureState } from "./capture-state.js";
import type { ProductionListenStore } from "./ProductionListenStore.js";

/** Fixed fixture clock — never derived from the wall clock. */
export const FIXED_NOW = Date.UTC(2026, 7, 7, 12, 0, 0);

export const LISTEN_FIXTURE_STATES = [
  "idle",
  "capturing",
  "paused-for-entitlement",
  "offline-buffering",
  "stopped-at-ceiling",
  "error-retryable",
  "error-permanent",
  "unavailable",
] as const;

export type ListenFixtureState = (typeof LISTEN_FIXTURE_STATES)[number];

/** Deterministic elapsed / backlog samples used by every non-idle fixture. */
const FIXTURE_ELAPSED_SECONDS = 600;
const FIXTURE_UNTRANSCRIBED_SECONDS = 10_800;
const FIXTURE_BUFFERED_SECONDS = 300;
const FIXTURE_CEILING_UNTRANSCRIBED_SECONDS = 7_200;
const FIXTURE_CAPTURING_ELAPSED_SECONDS = 125;

function queue(phase: QueuePhase): QueueStatus {
  return { phase, pendingCount: phase === "idle" ? 0 : 1 };
}

function captureFor(state: ListenFixtureState): CaptureState {
  switch (state) {
    case "idle":
    case "unavailable":
      return { kind: "idle" };
    case "capturing":
      return { kind: "capturing", elapsedSeconds: FIXTURE_CAPTURING_ELAPSED_SECONDS };
    case "paused-for-entitlement":
      return {
        kind: "paused-for-entitlement",
        elapsedSeconds: FIXTURE_ELAPSED_SECONDS,
        untranscribedSeconds: FIXTURE_UNTRANSCRIBED_SECONDS,
      };
    case "offline-buffering":
      return {
        kind: "offline-buffering",
        elapsedSeconds: FIXTURE_ELAPSED_SECONDS,
        bufferedSeconds: FIXTURE_BUFFERED_SECONDS,
        untranscribedSeconds: FIXTURE_UNTRANSCRIBED_SECONDS,
      };
    case "stopped-at-ceiling":
      return {
        kind: "stopped-at-ceiling",
        untranscribedSeconds: FIXTURE_CEILING_UNTRANSCRIBED_SECONDS,
      };
    case "error-retryable":
      return { kind: "error", retryable: true };
    case "error-permanent":
      return { kind: "error", retryable: false };
  }
}

export function fixtureListenStore(state: ListenFixtureState, now = FIXED_NOW): ProductionListenStore {
  void now;
  let capture: CaptureState = captureFor(state);
  const refreshPhase: RefreshPhase = state === "unavailable" ? "unavailable" : "ready";
  const status: StoreStatus = {
    refresh: { phase: refreshPhase, hasSavedData: state !== "unavailable" },
    queue: queue("idle"),
  };
  const listeners = new Set<() => void>();
  const notify = (): void => {
    listeners.forEach((listener) => listener());
  };

  return {
    status() {
      return status;
    },
    captureState() {
      return capture;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async refresh() {
      notify();
    },
    async start() {
      if (capture.kind !== "idle" && !(capture.kind === "error" && capture.retryable)) {
        throw new Error("fixture start refused");
      }
      capture = { kind: "capturing", elapsedSeconds: FIXTURE_CAPTURING_ELAPSED_SECONDS };
      notify();
    },
    async stop() {
      if (
        capture.kind !== "capturing" &&
        capture.kind !== "paused-for-entitlement" &&
        capture.kind !== "offline-buffering"
      ) {
        throw new Error("fixture stop refused");
      }
      capture = { kind: "idle" };
      notify();
    },
  };
}
