/** Platform Screen HTTP + native bridge -> the surface's closed Rewind vocabulary. */

import type { StoreStatus } from "@omi-core/domain";
import type { Env } from "@omi-core/kernel";
import type { QueueStatus } from "@omi-core/sync";
import {
  SCREEN_RETENTION_DEFAULT_DAYS,
  SCREEN_SEARCH_DEBOUNCE_MS,
  asPlatformScreenHttpClient,
  coerceScreenRetentionDays,
  createUnavailableScreenBridge,
  fetchScreenDays,
  fetchScreenRetention,
  fetchScreenRetired,
  fetchScreenSearch,
  fetchScreenTimeline,
  putScreenRetention,
  type PlatformScreenBridgeAccess,
  type PlatformScreenHttpClient,
  type PlatformScreenStatus,
  type ScreenDaySpanSummary,
  type ScreenOcrAttachment,
  type ScreenRetentionDays,
  type ScreenTextSearchHit,
  type ScreenTimelineFrame,
} from "@omi-core/adapters-platform";
import type { HttpClient } from "@omi-core/contracts";
import type { ProductionScreenStore, ScreenCaptureTone, ScreenFrameImageState } from "./ProductionScreenStore.js";
import {
  adjacentCaptureDay,
  calendarDayFromInstant,
  frameAtCursor,
  groupScreenSearchHits,
  playbackTickMs,
  screenEmptyKind,
  type ScreenPlaybackRate,
  type ScreenSearchGroup,
} from "./screen-presentation.js";

const IDLE_QUEUE: QueueStatus = { phase: "idle", pendingCount: 0 };

const EMPTY_DAYS: ScreenDaySpanSummary = {
  days: [],
  oldest_captured_at: null,
  newest_captured_at: null,
  frame_count: 0,
};

function captureTone(status: PlatformScreenStatus | null, bridgeAvailable: boolean): ScreenCaptureTone {
  if (!bridgeAvailable || status === null) return "red";
  if (status.state === "recording") return "green";
  if (status.state === "paused" || status.state === "starting") return "amber";
  return "red";
}

export function createPlatformProductionScreenStore(options: {
  readonly http: HttpClient | PlatformScreenHttpClient;
  readonly env: Env;
  readonly bridge?: PlatformScreenBridgeAccess;
  readonly initialDay?: string | null;
  readonly initialFrameId?: string | null;
}): ProductionScreenStore {
  const http = asPlatformScreenHttpClient(options.http as HttpClient);
  const bridge = options.bridge ?? createUnavailableScreenBridge();
  const listeners = new Set<() => void>();
  let status: StoreStatus = {
    refresh: { phase: "initial-loading", hasSavedData: false },
    queue: IDLE_QUEUE,
  };
  let days = EMPTY_DAYS;
  let selectedDay: string | null = options.initialDay ?? null;
  let timeline: readonly ScreenTimelineFrame[] = [];
  let frameCursor = 0;
  let searchInput = "";
  let searchHits: readonly ScreenTextSearchHit[] = [];
  let selectedGroupIndex = 0;
  let matchedBlockIds: readonly string[] = [];
  let retentionDays: ScreenRetentionDays = SCREEN_RETENTION_DEFAULT_DAYS;
  let exclusions: readonly string[] = [];
  let playbackRate: ScreenPlaybackRate = 1;
  let playing = false;
  let captureEverEnabled = false;
  let frameImage: ScreenFrameImageState = { kind: "absent" };
  let imageGeneration = 0;
  let cancelSearch: (() => void) | null = null;
  let cancelPlayback: (() => void) | null = null;
  let unsubscribeBridge: (() => void) | null = null;
  let openedFrameId = options.initialFrameId ?? null;
  const ocrByFrameId = new Map<string, ScreenOcrAttachment>();

  const notify = (): void => {
    for (const listener of listeners) listener();
  };

  const captureStatus = (): PlatformScreenStatus | null => {
    return bridge.available ? bridge.snapshot() : null;
  };

  const hasSavedData = (): boolean => days.frame_count > 0 || timeline.length > 0 || searchHits.length > 0;

  const applyCaptureEnabled = (): void => {
    const snapshot = captureStatus();
    if ((snapshot?.framesStored ?? 0) > 0 || days.frame_count > 0) captureEverEnabled = true;
    if (snapshot?.state === "recording" || snapshot?.state === "paused" || snapshot?.state === "starting") {
      captureEverEnabled = true;
    }
  };

  const emptyKind = () => screenEmptyKind({
    phase: status.refresh.phase,
    permission: captureStatus()?.permission ?? "undetermined",
    captureEverEnabled,
    historyFrameCount: days.frame_count,
    dayFrameCount: timeline.length,
    searchQuery: searchInput,
    searchHitCount: searchHits.length,
  });

  const loadTimeline = async (day: string): Promise<void> => {
    const page = await fetchScreenTimeline(http, day);
    if (page.kind !== "page") {
      timeline = [];
      frameCursor = 0;
      frameImage = { kind: "absent" };
      return;
    }
    timeline = page.value.frames;
    if (openedFrameId !== null) {
      const index = timeline.findIndex((frame) => frame.id === openedFrameId);
      frameCursor = index >= 0 ? index : 0;
      if (index >= 0) openedFrameId = null;
    } else {
      frameCursor = timeline.length === 0 ? 0 : Math.min(frameCursor, timeline.length - 1);
    }
  };

  const loadFrameImage = (): void => {
    const frame = frameAtCursor(timeline, frameCursor);
    if (frame === null) {
      frameImage = { kind: "absent" };
      return;
    }
    if (!bridge.available) {
      frameImage = { kind: "unavailable" };
      return;
    }
    const generation = ++imageGeneration;
    frameImage = { kind: "loading" };
    void bridge.frameImage({ frameRef: frame.frame_ref }).then(
      (image) => {
        if (generation !== imageGeneration) return;
        frameImage = { kind: "ready", image };
        notify();
      },
      () => {
        if (generation !== imageGeneration) return;
        frameImage = { kind: "unavailable" };
        notify();
      },
    );
  };

  const selectedHitBlocks = (): readonly string[] => {
    const frame = frameAtCursor(timeline, frameCursor);
    if (frame === null || searchInput.trim() === "") return [];
    const hit = searchHits.find((row) => row.frame_id === frame.id);
    return hit?.matched_block_ids ?? matchedBlockIds;
  };

  const stopPlayback = (): void => {
    playing = false;
    cancelPlayback?.();
    cancelPlayback = null;
  };

  const schedulePlayback = (): void => {
    cancelPlayback?.();
    cancelPlayback = null;
    if (!playing || timeline.length === 0) return;
    cancelPlayback = options.env.delay(playbackTickMs(playbackRate), () => {
      cancelPlayback = null;
      if (!playing) return;
      if (frameCursor >= timeline.length - 1) {
        stopPlayback();
        notify();
        return;
      }
      frameCursor += 1;
      matchedBlockIds = selectedHitBlocks();
      loadFrameImage();
      notify();
      schedulePlayback();
    });
  };

  const selectFrameIndex = (index: number): void => {
    if (timeline.length === 0) {
      frameCursor = 0;
      frameImage = { kind: "absent" };
      return;
    }
    frameCursor = Math.min(Math.max(0, index), timeline.length - 1);
    matchedBlockIds = selectedHitBlocks();
    loadFrameImage();
  };

  const runSearch = async (query: string): Promise<void> => {
    if (query.trim() === "") {
      searchHits = [];
      selectedGroupIndex = 0;
      matchedBlockIds = [];
      notify();
      return;
    }
    const page = await fetchScreenSearch(http, query);
    if (page.kind !== "page") {
      searchHits = [];
      selectedGroupIndex = 0;
      return;
    }
    searchHits = page.value.hits;
    selectedGroupIndex = 0;
    const groups = groupScreenSearchHits(searchHits);
    const first = groups[0]?.hits[0];
    if (first !== undefined) {
      matchedBlockIds = first.matched_block_ids;
      const day = calendarDayFromInstant(first.captured_at);
      if (day !== null && day !== selectedDay) {
        selectedDay = day;
        await loadTimeline(day);
      }
      const index = timeline.findIndex((frame) => frame.id === first.frame_id);
      if (index >= 0) selectFrameIndex(index);
      else loadFrameImage();
    }
  };

  const refreshAll = async (): Promise<void> => {
    const previous = status.refresh.hasSavedData;
    status = {
      refresh: {
        phase: previous || days.frame_count > 0 ? "refreshing" : "initial-loading",
        hasSavedData: previous,
      },
      queue: IDLE_QUEUE,
    };
    notify();
    if (bridge.available) {
      try {
        await bridge.refresh();
      } catch {
        // Bridge refresh failure must not be rewritten as permission-denied.
      }
    }
    const [daySpan, retention] = await Promise.all([
      fetchScreenDays(http),
      fetchScreenRetention(http),
    ]);
    if (daySpan.kind === "page") {
      days = daySpan.value;
    } else if (daySpan.kind === "auth-invalid" || daySpan.kind === "unavailable" || daySpan.kind === "unreadable") {
      status = {
        refresh: { phase: hasSavedData() ? "saved-but-refresh-failed" : "unavailable", hasSavedData: hasSavedData() },
        queue: IDLE_QUEUE,
      };
      applyCaptureEnabled();
      notify();
      return;
    }
    if (retention.kind === "page") retentionDays = retention.value.days;
    await fetchScreenRetired(http);
    applyCaptureEnabled();
    if (bridge.available) {
      try {
        const listed = await bridge.exclusionsList();
        exclusions = listed.bundleIds;
      } catch {
        exclusions = [];
      }
    }
    if (selectedDay === null) {
      selectedDay = days.days.at(-1) ?? days.days[0] ?? null;
    }
    if (selectedDay !== null) await loadTimeline(selectedDay);
    if (openedFrameId !== null && timeline.every((frame) => frame.id !== openedFrameId)) {
      for (const day of [...days.days].reverse()) {
        await loadTimeline(day);
        if (timeline.some((frame) => frame.id === openedFrameId)) {
          selectedDay = day;
          break;
        }
      }
    }
    selectFrameIndex(frameCursor);
    if (searchInput.trim() !== "") await runSearch(searchInput);
    status = {
      refresh: { phase: "ready", hasSavedData: hasSavedData() },
      queue: IDLE_QUEUE,
    };
    applyCaptureEnabled();
    notify();
  };

  if (bridge.available) {
    unsubscribeBridge = bridge.subscribe(() => {
      applyCaptureEnabled();
      notify();
    });
  }

  const store: ProductionScreenStore = {
    status: () => status,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) {
          cancelSearch?.();
          stopPlayback();
          unsubscribeBridge?.();
          unsubscribeBridge = null;
        }
      };
    },
    refresh: refreshAll,
    days: () => days,
    selectedDay: () => selectedDay,
    async selectDay(day) {
      selectedDay = day;
      await loadTimeline(day);
      selectFrameIndex(0);
      notify();
    },
    async jumpDay(direction) {
      const next = adjacentCaptureDay(days.days, selectedDay ?? "", direction);
      if (next === null) return;
      await store.selectDay(next);
    },
    timeline: () => timeline,
    frameCursor: () => frameCursor,
    selectedFrame: () => frameAtCursor(timeline, frameCursor),
    selectFrame(index) {
      stopPlayback();
      selectFrameIndex(index);
      notify();
    },
    stepFrame(delta) {
      stopPlayback();
      selectFrameIndex(frameCursor + delta);
      notify();
    },
    searchQuery: () => searchInput,
    setSearchQuery(query) {
      searchInput = query;
      cancelSearch?.();
      cancelSearch = options.env.delay(SCREEN_SEARCH_DEBOUNCE_MS, () => {
        cancelSearch = null;
        void runSearch(searchInput).then(() => notify());
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
      if (day !== null && day !== selectedDay) {
        selectedDay = day;
        await loadTimeline(day);
      }
      const frameIndex = timeline.findIndex((frame) => frame.id === hit.frame_id);
      if (frameIndex >= 0) selectFrameIndex(frameIndex);
      notify();
    },
    async stepSearchGroup(delta) {
      await store.selectSearchGroup(selectedGroupIndex + delta);
    },
    matchedBlockIds: () => selectedHitBlocks(),
    ocrForSelectedFrame() {
      const frame = frameAtCursor(timeline, frameCursor);
      if (frame === null) return null;
      return ocrByFrameId.get(frame.id) ?? null;
    },
    frameImage: () => frameImage,
    playbackRate: () => playbackRate,
    setPlaybackRate(rate) {
      playbackRate = rate;
      if (playing) schedulePlayback();
      notify();
    },
    playing: () => playing,
    play() {
      if (timeline.length === 0) return;
      playing = true;
      schedulePlayback();
      notify();
    },
    pause() {
      stopPlayback();
      notify();
    },
    unwind() {
      if (playing) {
        stopPlayback();
        notify();
        return;
      }
      if (searchInput !== "") {
        searchInput = "";
        searchHits = [];
        selectedGroupIndex = 0;
        matchedBlockIds = [];
        cancelSearch?.();
        cancelSearch = null;
        notify();
      }
    },
    emptyKind,
    captureStatus,
    captureTone: () => captureTone(captureStatus(), bridge.available),
    bridgeAvailable: () => bridge.available,
    captureEverEnabled: () => captureEverEnabled,
    async startCapture() {
      if (!bridge.available) return;
      await bridge.start();
      captureEverEnabled = true;
      notify();
    },
    async stopCapture() {
      if (!bridge.available) return;
      await bridge.stop();
      notify();
    },
    async requestPermission() {
      if (!bridge.available) return;
      await bridge.requestPermission();
      notify();
    },
    async openSettings() {
      if (!bridge.available) return;
      await bridge.openSettings();
    },
    async rebuildIndex() {
      if (!bridge.available) return null;
      const result = await bridge.rebuildIndex();
      notify();
      return result;
    },
    retentionDays: () => retentionDays,
    async setRetentionDays(daysValue) {
      const coerced = coerceScreenRetentionDays(daysValue);
      const written = await putScreenRetention(http, coerced);
      if (written.kind === "saved") retentionDays = written.setting.days;
      else retentionDays = coerced;
      if (bridge.available) {
        try {
          await bridge.retentionSet(retentionDays);
        } catch {
          // Shell sweep is best-effort beside the service write.
        }
      }
      notify();
    },
    exclusions: () => exclusions,
    async setExclusions(bundleIds) {
      const next = [...new Set(bundleIds.map((id) => id.trim()).filter((id) => id.length > 0))];
      if (bridge.available) {
        const result = await bridge.exclusionsSet(next);
        exclusions = result.bundleIds;
      } else {
        exclusions = next;
      }
      notify();
    },
    async addExclusion(bundleId) {
      await store.setExclusions([...exclusions, bundleId]);
    },
    async removeExclusion(bundleId) {
      await store.setExclusions(exclusions.filter((id) => id !== bundleId));
    },
    async resetExclusions() {
      await store.setExclusions([]);
    },
    framesStored: () => captureStatus()?.framesStored ?? days.frame_count,
    bytesOnDisk: () => captureStatus()?.bytesOnDisk ?? null,
    async openFrame(frameId) {
      openedFrameId = frameId;
      if (timeline.some((frame) => frame.id === frameId)) {
        selectFrameIndex(timeline.findIndex((frame) => frame.id === frameId));
        openedFrameId = null;
        notify();
        return true;
      }
      await refreshAll();
      return timeline.some((frame) => frame.id === frameId);
    },
    selectedFrameRef: () => frameAtCursor(timeline, frameCursor)?.frame_ref ?? null,
    engineState: () => captureStatus()?.state ?? null,
    permission: () => captureStatus()?.permission ?? null,
    bridge: () => bridge,
  };
  return store;
}
