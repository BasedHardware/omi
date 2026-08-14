import type { StoreStatus } from "@omi-core/domain";
import type { PlatformListenPreflightSnapshot } from "@omi-core/adapters-platform";
import type { ListenEntitlementSnapshot, TranscriptSegment } from "@omi-core/wire-listen";
import type { CaptureState, ProductionListenStore } from "./ProductionListenStore.js";

export const LISTEN_FIXTURE_STATES = [
  "loading", "empty", "ready", "error", "offline", "busy", "complete",
] as const;
export type ListenFixtureState = (typeof LISTEN_FIXTURE_STATES)[number];

const PREFLIGHT: PlatformListenPreflightSnapshot = Object.freeze({
  permission: "granted",
  device: Object.freeze({ state: "available", label: "Default microphone" }),
  recovery: null,
});

const ENTITLEMENT: ListenEntitlementSnapshot = Object.freeze({
  source: "entitlement",
  status: "approaching_limit",
  captureContinuing: true,
  remaining: null,
  usage: Object.freeze({ amount: 420, unit: "seconds" }),
  limit: Object.freeze({ kind: "unmetered" }),
  reason: null,
  upgradeTarget: null,
  suggestedAction: null,
});

const CEILING_ENTITLEMENT: ListenEntitlementSnapshot = Object.freeze({
  source: "entitlement",
  status: "limit_reached",
  captureContinuing: false,
  remaining: Object.freeze({ amount: 0, unit: "seconds" }),
  usage: null,
  limit: Object.freeze({ kind: "metered", amount: 420, unit: "seconds" }),
  reason: "free_tier_transcription_limit",
  upgradeTarget: null,
  suggestedAction: null,
});

const SEGMENTS: readonly TranscriptSegment[] = Object.freeze([
  Object.freeze({ id: "fixture-listen-one", text: "The review should stay focused on the one decision that matters.", speaker: "You", is_user: true, start: 0, end: 4 }),
  Object.freeze({ id: "fixture-listen-two", text: "We will keep the shell behavior shared and verify the native boundaries separately.", speaker: "Omi", is_user: false, start: 5, end: 10 }),
]);

function captureFor(state: ListenFixtureState): CaptureState {
  switch (state) {
    case "loading": return { kind: "loading" };
    case "error": return { kind: "error", retryable: true, untranscribedSeconds: 0 };
    case "offline": return { kind: "offline-buffering", elapsedSeconds: 420, bufferedSeconds: 90, untranscribedSeconds: 90 };
    case "busy": return { kind: "capturing", elapsedSeconds: 420, untranscribedSeconds: 18 };
    case "complete": return { kind: "stopped-at-ceiling", untranscribedSeconds: 0 };
    default: return { kind: "idle" };
  }
}

function statusFor(state: ListenFixtureState): StoreStatus {
  const phase = state === "loading"
    ? "initial-loading"
    : state === "error"
      ? "unavailable"
      : state === "offline"
        ? "saved-but-refresh-failed"
        : "ready";
  const hasSavedData = state === "ready" || state === "offline" || state === "busy" || state === "complete";
  return {
    refresh: { phase, hasSavedData },
    queue: { phase: state === "busy" ? "sending" : "idle", pendingCount: state === "busy" ? 1 : 0 },
  };
}

function segmentsFor(state: ListenFixtureState): readonly TranscriptSegment[] {
  if (state === "ready") return SEGMENTS.slice(0, 1);
  if (state === "offline" || state === "busy" || state === "complete") return SEGMENTS;
  return [];
}

/** Deterministic, read-safe Listen store used only by `?polish=1` QA routes. */
export function fixtureListenStore(state: ListenFixtureState): ProductionListenStore {
  let capture = captureFor(state);
  const status = statusFor(state);
  const segments = segmentsFor(state);
  const listeners = new Set<() => void>();
  const notify = (): void => listeners.forEach((listener) => listener());
  return {
    status: () => status,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    async refresh() { notify(); },
    captureState: () => capture,
    transcriptSegments: () => segments,
    entitlementState: () => state === "loading" || state === "error"
      ? null
      : state === "complete"
        ? CEILING_ENTITLEMENT
        : ENTITLEMENT,
    preflight: () => state === "error"
      ? Object.freeze({ permission: "unavailable", device: Object.freeze({ state: "unavailable", label: null }), recovery: null })
      : PREFLIGHT,
    async start() { capture = { kind: "capturing", elapsedSeconds: 0, untranscribedSeconds: 0 }; notify(); },
    async stop() { capture = { kind: "idle" }; notify(); },
  };
}
