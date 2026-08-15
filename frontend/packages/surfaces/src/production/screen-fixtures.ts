import type { StoreStatus } from "@omi-core/domain";
import type {
  PlatformScreenBridgeAccess,
  PlatformScreenStatus,
  ScreenDaySpanSummary,
  ScreenOcrAttachment,
  ScreenRetentionDays,
  ScreenTextSearchHit,
  ScreenTimelineFrame,
} from "@omi-core/adapters-platform";
import type { ProductionScreenStore, ScreenFrameImageState } from "./ProductionScreenStore.js";
import {
  adjacentCaptureDay,
  calendarDayFromInstant,
  frameAtCursor,
  groupScreenSearchHits,
  screenEmptyKind,
  type ScreenPlaybackRate,
} from "./screen-presentation.js";

export const SCREEN_FIXTURE_STATES = [
  "loading",
  "ready",
  "never-enabled",
  "permission-denied",
  "day-empty",
  "search-miss",
  "bridge-absent",
  "recovered",
  "retention-unlimited",
  "bytes-unknown",
] as const;
export type ScreenFixtureState = (typeof SCREEN_FIXTURE_STATES)[number];

const DAY_A = "2026-08-04";
const DAY_B = "2026-08-07";

const OCR_HARBORLINE: ScreenOcrAttachment = Object.freeze({
  full_text: "Harborline Cafe Saturday noon table for Mira Vale and Jordan Hale.",
  blocks: Object.freeze([
    Object.freeze({ id: "0", text: "Harborline Cafe", x: 0.08, y: 0.12, w: 0.4, h: 0.08, confidence: 0.98 }),
    Object.freeze({ id: "1", text: "Saturday noon table for Mira Vale and Jordan Hale.", x: 0.08, y: 0.22, w: 0.7, h: 0.1, confidence: 0.94 }),
  ]),
});

const OCR_CEDAR: ScreenOcrAttachment = Object.freeze({
  full_text: "Pack rain shells, two water bottles, and the Northbridge Library field guide.",
  blocks: Object.freeze([
    Object.freeze({ id: "0", text: "Pack rain shells", x: 0.1, y: 0.18, w: 0.5, h: 0.08, confidence: 0.96 }),
    Object.freeze({ id: "1", text: "two water bottles, and the Northbridge Library field guide.", x: 0.1, y: 0.28, w: 0.72, h: 0.12, confidence: 0.91 }),
  ]),
});

const OCR_FABLE: ScreenOcrAttachment = Object.freeze({
  full_text: "Sable Wren pinned the Fable and Wick window sketch next to the Wickwater crate list.",
  blocks: Object.freeze([
    Object.freeze({ id: "0", text: "Fable and Wick window sketch", x: 0.15, y: 0.2, w: 0.6, h: 0.1, confidence: 0.97 }),
    Object.freeze({ id: "1", text: "Wickwater crate list", x: 0.15, y: 0.4, w: 0.45, h: 0.08, confidence: 0.93 }),
  ]),
});

function frame(
  id: string,
  capturedAt: string,
  appBundleId: string,
  appName: string,
  windowTitle: string,
  offset: number,
): ScreenTimelineFrame {
  return Object.freeze({
    id,
    capture_session_id: "harborline-weekend-demo",
    captured_at: capturedAt,
    app_bundle_id: appBundleId,
    app_name: appName,
    window_title: windowTitle,
    device_name: "Demo Mac",
    client_device_id: "demo-mac-1",
    frame_ref: Object.freeze({ kind: "chunk", path: `chunks/demo/${id}.hevc`, offset }),
    dhash: `demo-dhash-${id}`,
  });
}

const FRAME_HARBORLINE = frame(
  "demo-screen-harborline-reservation",
  "2026-08-07T11:30:00.000Z",
  "com.apple.Safari",
  "Safari",
  "Harborline Cafe — Saturday table",
  0,
);
const FRAME_CEDAR = frame(
  "demo-screen-cedar-packing",
  "2026-08-07T11:50:00.000Z",
  "com.apple.Notes",
  "Notes",
  "Cedar Loop packing",
  12_000,
);
const FRAME_FABLE = frame(
  "demo-screen-fable-wick-sketch",
  "2026-08-04T11:58:00.000Z",
  "com.apple.Preview",
  "Preview",
  "Fable and Wick window sketch",
  4_000,
);

const OCR_BY_ID: Readonly<Record<string, ScreenOcrAttachment>> = Object.freeze({
  [FRAME_HARBORLINE.id]: OCR_HARBORLINE,
  [FRAME_CEDAR.id]: OCR_CEDAR,
  [FRAME_FABLE.id]: OCR_FABLE,
});

const SEARCH_HARBORLINE: ScreenTextSearchHit = Object.freeze({
  frame_id: FRAME_HARBORLINE.id,
  captured_at: FRAME_HARBORLINE.captured_at,
  app_bundle_id: FRAME_HARBORLINE.app_bundle_id,
  app_name: FRAME_HARBORLINE.app_name,
  window_title: FRAME_HARBORLINE.window_title,
  snippet: "<<Harborline>> Cafe Saturday noon table for Mira Vale and Jordan Hale.",
  matched_block_ids: Object.freeze(["0"]),
  rank: 1.2,
});

function statusFor(state: ScreenFixtureState): StoreStatus {
  const phase = state === "loading" ? "initial-loading" : "ready";
  const hasSavedData = state === "ready"
    || state === "day-empty"
    || state === "search-miss"
    || state === "bridge-absent"
    || state === "recovered"
    || state === "retention-unlimited"
    || state === "bytes-unknown";
  return {
    refresh: { phase, hasSavedData },
    queue: { phase: "idle", pendingCount: 0 },
  };
}

function daysFor(state: ScreenFixtureState): ScreenDaySpanSummary {
  if (state === "never-enabled" || state === "permission-denied" || state === "loading") {
    return { days: [], oldest_captured_at: null, newest_captured_at: null, frame_count: 0 };
  }
  if (state === "day-empty") {
    return {
      days: [DAY_A, DAY_B],
      oldest_captured_at: FRAME_FABLE.captured_at,
      newest_captured_at: FRAME_CEDAR.captured_at,
      frame_count: 3,
    };
  }
  return {
    days: [DAY_A, DAY_B],
    oldest_captured_at: FRAME_FABLE.captured_at,
    newest_captured_at: FRAME_CEDAR.captured_at,
    frame_count: 3,
  };
}

function timelineFor(state: ScreenFixtureState, day: string): readonly ScreenTimelineFrame[] {
  if (state === "never-enabled" || state === "permission-denied" || state === "loading") return [];
  if (state === "day-empty") return [];
  if (day === DAY_A) return [FRAME_FABLE];
  return [FRAME_HARBORLINE, FRAME_CEDAR];
}

function captureFor(state: ScreenFixtureState): PlatformScreenStatus | null {
  if (state === "bridge-absent") return null;
  if (state === "permission-denied") {
    return Object.freeze({
      state: "idle",
      reason: null,
      permission: "denied",
      framesStored: 0,
      bytesOnDisk: null,
      lastCaptureAt: null,
    });
  }
  if (state === "never-enabled" || state === "loading") {
    return Object.freeze({
      state: "idle",
      reason: null,
      permission: "granted",
      framesStored: 0,
      bytesOnDisk: null,
      lastCaptureAt: null,
    });
  }
  if (state === "recovered") {
    return Object.freeze({
      state: "error",
      reason: "index-incomplete",
      permission: "granted",
      framesStored: 3,
      bytesOnDisk: 2_400_000_000,
      lastCaptureAt: FRAME_CEDAR.captured_at,
    });
  }
  if (state === "bytes-unknown") {
    return Object.freeze({
      state: "recording",
      reason: null,
      permission: "granted",
      framesStored: 3,
      bytesOnDisk: null,
      lastCaptureAt: FRAME_CEDAR.captured_at,
    });
  }
  return Object.freeze({
    state: state === "ready" ? "recording" : "idle",
    reason: null,
    permission: "granted",
    framesStored: 3,
    bytesOnDisk: 2_400_000_000,
    lastCaptureAt: FRAME_CEDAR.captured_at,
  });
}

function delayed(callbacks: { ms: number; fn: () => void; active: boolean }[], ms: number, fn: () => void): () => void {
  const pending = { ms, fn, active: true };
  callbacks.push(pending);
  return () => { pending.active = false; };
}

/** Deterministic, read-safe Rewind store used by production tests and `?polish=1`. */
export function fixtureScreenStore(state: ScreenFixtureState): ProductionScreenStore & {
  runDebounce(): void;
  runPlaybackTick(): void;
} {
  const status = statusFor(state);
  let days = daysFor(state);
  let selectedDay: string | null = state === "day-empty" ? "2026-08-06" : (days.days.at(-1) ?? null);
  let timeline: ScreenTimelineFrame[] = selectedDay ? [...timelineFor(state, selectedDay)] : [];
  let frameCursor = 0;
  let searchInput = state === "search-miss" ? "no-such-place" : "";
  let searchHits: ScreenTextSearchHit[] = [];
  let selectedGroupIndex = 0;
  let matchedBlockIds: readonly string[] = [];
  let retentionDays: ScreenRetentionDays = state === "retention-unlimited" ? 0 : 7;
  let exclusions: string[] = state === "ready" ? ["com.example.secret"] : [];
  let playbackRate: ScreenPlaybackRate = 1;
  let playing = false;
  let capture = captureFor(state);
  const delayedCallbacks: { ms: number; fn: () => void; active: boolean }[] = [];
  const listeners = new Set<() => void>();
  const notify = (): void => { for (const listener of listeners) listener(); };
  const bridgeAvailable = state !== "bridge-absent";
  const captureEverEnabled = state !== "never-enabled" && state !== "permission-denied" && state !== "loading";
  const png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
  let frameImage: ScreenFrameImageState = !bridgeAvailable
    ? { kind: "unavailable" }
    : timeline.length === 0
      ? { kind: "absent" }
      : { kind: "ready", image: { pngBase64: png, width: 1280, height: 800 } };

  const loadDay = (day: string): void => {
    selectedDay = day;
    timeline = [...timelineFor(state, day)];
    frameCursor = 0;
    frameImage = !bridgeAvailable
      ? { kind: "unavailable" }
      : timeline.length === 0
        ? { kind: "absent" }
        : { kind: "ready", image: { pngBase64: png, width: 1280, height: 800 } };
  };

  const applySearch = (query: string): void => {
    if (query.trim() === "") {
      searchHits = [];
      matchedBlockIds = [];
      return;
    }
    if (state === "search-miss" || query === "no-such-place") {
      searchHits = [];
      matchedBlockIds = [];
      return;
    }
    const needle = query.toLowerCase();
    searchHits = [SEARCH_HARBORLINE].filter((hit) =>
      hit.snippet.toLowerCase().includes(needle) || hit.app_name.toLowerCase().includes(needle),
    );
    const first = searchHits[0];
    if (first !== undefined) {
      matchedBlockIds = first.matched_block_ids;
      const day = calendarDayFromInstant(first.captured_at);
      if (day !== null) loadDay(day);
      const index = timeline.findIndex((row) => row.id === first.frame_id);
      if (index >= 0) frameCursor = index;
    }
  };

  if (state === "search-miss") applySearch(searchInput);

  const store: ProductionScreenStore & { runDebounce(): void; runPlaybackTick(): void } = {
    status: () => status,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async refresh() { notify(); },
    days: () => days,
    selectedDay: () => selectedDay,
    async selectDay(day) { loadDay(day); notify(); },
    async jumpDay(direction) {
      const next = adjacentCaptureDay(days.days, selectedDay ?? "", direction);
      if (next === null) return;
      loadDay(next);
      notify();
    },
    timeline: () => timeline,
    frameCursor: () => frameCursor,
    selectedFrame: () => frameAtCursor(timeline, frameCursor),
    selectFrame(index) {
      playing = false;
      frameCursor = timeline.length === 0 ? 0 : Math.min(Math.max(0, index), timeline.length - 1);
      notify();
    },
    stepFrame(delta) {
      store.selectFrame(frameCursor + delta);
    },
    searchQuery: () => searchInput,
    setSearchQuery(query) {
      searchInput = query;
      delayed(delayedCallbacks, 300, () => {
        applySearch(searchInput);
        notify();
      });
      notify();
    },
    searchHits: () => searchHits,
    searchGroups: () => groupScreenSearchHits(searchHits),
    selectedGroupIndex: () => selectedGroupIndex,
    async selectSearchGroup(index) {
      const groups = groupScreenSearchHits(searchHits);
      if (groups.length === 0) return;
      selectedGroupIndex = Math.min(Math.max(0, index), groups.length - 1);
      const hit = groups[selectedGroupIndex]?.hits[0];
      if (hit === undefined) return;
      matchedBlockIds = hit.matched_block_ids;
      const day = calendarDayFromInstant(hit.captured_at);
      if (day !== null) loadDay(day);
      const frameIndex = timeline.findIndex((row) => row.id === hit.frame_id);
      if (frameIndex >= 0) frameCursor = frameIndex;
      notify();
    },
    async stepSearchGroup(delta) {
      await store.selectSearchGroup(selectedGroupIndex + delta);
    },
    matchedBlockIds: () => matchedBlockIds,
    ocrForSelectedFrame() {
      const selected = frameAtCursor(timeline, frameCursor);
      return selected ? OCR_BY_ID[selected.id] ?? null : null;
    },
    frameImage: () => frameImage,
    playbackRate: () => playbackRate,
    setPlaybackRate(rate) { playbackRate = rate; notify(); },
    playing: () => playing,
    play() {
      if (timeline.length === 0) return;
      playing = true;
      delayed(delayedCallbacks, 200, () => {
        if (!playing) return;
        if (frameCursor >= timeline.length - 1) {
          playing = false;
          notify();
          return;
        }
        frameCursor += 1;
        notify();
      });
      notify();
    },
    pause() { playing = false; notify(); },
    unwind() {
      if (playing) {
        playing = false;
        notify();
        return;
      }
      if (searchInput !== "") {
        searchInput = "";
        searchHits = [];
        matchedBlockIds = [];
        notify();
      }
    },
    emptyKind: () => screenEmptyKind({
      phase: status.refresh.phase,
      permission: capture?.permission ?? "undetermined",
      captureEverEnabled,
      historyFrameCount: days.frame_count,
      dayFrameCount: timeline.length,
      searchQuery: searchInput,
      searchHitCount: searchHits.length,
    }),
    captureStatus: () => capture,
    captureTone: () => {
      if (!bridgeAvailable || capture === null) return "red";
      if (capture.state === "recording") return "green";
      if (capture.state === "paused" || capture.state === "starting") return "amber";
      return "red";
    },
    bridgeAvailable: () => bridgeAvailable,
    captureEverEnabled: () => captureEverEnabled,
    async startCapture() {
      if (!bridgeAvailable || capture === null) return;
      capture = { ...capture, state: "recording" };
      notify();
    },
    async stopCapture() {
      if (!bridgeAvailable || capture === null) return;
      capture = { ...capture, state: "idle" };
      notify();
    },
    async requestPermission() {
      if (capture === null) return;
      capture = { ...capture, permission: "granted" };
      notify();
    },
    async openSettings() {},
    async rebuildIndex() { return { frames: days.frame_count, chunks: 1 }; },
    retentionDays: () => retentionDays,
    async setRetentionDays(next) { retentionDays = next; notify(); },
    exclusions: () => exclusions,
    async setExclusions(bundleIds) { exclusions = [...bundleIds]; notify(); },
    async addExclusion(bundleId) { await store.setExclusions([...exclusions, bundleId]); },
    async removeExclusion(bundleId) { await store.setExclusions(exclusions.filter((id) => id !== bundleId)); },
    async resetExclusions() { await store.setExclusions([]); },
    framesStored: () => capture?.framesStored ?? days.frame_count,
    bytesOnDisk: () => capture?.bytesOnDisk ?? null,
    async openFrame(frameId) {
      for (const day of days.days) {
        loadDay(day);
        const index = timeline.findIndex((row) => row.id === frameId);
        if (index >= 0) {
          frameCursor = index;
          notify();
          return true;
        }
      }
      return false;
    },
    selectedFrameRef: () => frameAtCursor(timeline, frameCursor)?.frame_ref ?? null,
    engineState: () => capture?.state ?? null,
    permission: () => capture?.permission ?? null,
    bridge: (): PlatformScreenBridgeAccess => bridgeAvailable
      ? {
          available: true,
          snapshot: () => capture ?? {
            state: "idle",
            reason: null,
            permission: "undetermined",
            framesStored: 0,
            bytesOnDisk: null,
            lastCaptureAt: null,
          },
          subscribe: () => () => {},
          async refresh() {},
          async start() { return { sessionId: "fixture", state: "recording" }; },
          async stop() { return { state: "idle" }; },
          async frameImage() { return { pngBase64: png, width: 1280, height: 800 }; },
          async exclusionsList() { return { bundleIds: exclusions }; },
          async exclusionsSet(bundleIds) { return { bundleIds: [...bundleIds] }; },
          async retentionSet(next) { return { days: next, retiredFrameRefs: [] }; },
          async rebuildIndex() { return { frames: days.frame_count, chunks: 1 }; },
          async requestPermission() { return { permission: "granted" }; },
          async openSettings() { return { opened: true }; },
        }
      : { available: false },
    runDebounce() {
      const pending = delayedCallbacks.find((entry) => entry.active && entry.ms === 300);
      if (pending === undefined) return;
      pending.active = false;
      pending.fn();
    },
    runPlaybackTick() {
      const pending = delayedCallbacks.find((entry) => entry.active && entry.ms === 200);
      if (pending === undefined) return;
      pending.active = false;
      pending.fn();
    },
  };
  return store;
}
