import { create } from "zustand";
import { nanoid } from "nanoid";
import {
  takeScreenshotWithOcr,
  getActiveWindow,
  getRecentScreenshots,
  getScreenshotImage,
  getScreenshotById,
  searchScreenshots,
  searchScreenshotsSemantic,
  deleteAllScreenshots as deleteAllScreenshotsIpc,
  deleteScreenshotById as deleteScreenshotByIdIpc,
} from "@/services/rewind";
import type { CaptureConfig } from "@/services/rewind";
import { embedText } from "@/services/embeddingService";
import {
  backfillScreenshotEmbeddings,
  embedAndSaveScreenshot,
} from "@/services/rewindEmbeddings";
import { isCommercialTime, watchCommercialTime } from "@/utils/commercialTime";
import { useFocusStore } from "@/stores/focusStore";

// Re-export for consumers.
export type { CaptureConfig };

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Screenshot {
  /** Database row ID (0 for unsaved screenshots not yet persisted). */
  dbId: number;
  /** Client-side unique ID (for React keys). */
  id: string;
  /** Base64-encoded JPEG data — loaded lazily; empty string means not yet loaded. */
  data: string;
  timestamp: string;
  width: number;
  height: number;
  appName: string;
  windowTitle: string;
  ocrText?: string;
  /** Why this row is in a result set: literal keyword hit (FTS), or meaning match (vector). */
  matchType?: "keyword" | "semantic";
  /** Cosine similarity for semantic hits (for debugging/sorting). */
  matchScore?: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_SCREENSHOTS = 1000;
/** Number of most-recent screenshots to eagerly load image data for on mount. */
const EAGER_LOAD_COUNT = 20;

// ---------------------------------------------------------------------------
// State shape
// ---------------------------------------------------------------------------

interface RewindState {
  /** User intent — true when the user has turned Rewind on (may still be paused outside commercial hours). */
  rewindEnabled: boolean;
  /** True when we're inside the commercial-time window (work hours). */
  inCommercialHours: boolean;
  /** Whether continuous capture is currently running. */
  isCapturing: boolean;
  /** Timestamp (ms) of when the current active capture started. null when not running. */
  captureStartedAt: number | null;
  /** Array of captured screenshots, newest first. */
  screenshots: Screenshot[];
  /** Currently viewed screenshot. */
  selectedScreenshot: Screenshot | null;
  /** Current search query text. */
  searchQuery: string;
  /** Screenshots matching the current search query. */
  searchResults: Screenshot[];
  /** True while a search IPC call is in flight. */
  isSearching: boolean;
  /** Capture configuration. */
  captureConfig: CaptureConfig;
  /** Whether an async operation is in progress. */
  isLoading: boolean;
  /** True while the initial DB history is being loaded. */
  isLoadingHistory: boolean;
  /** Timestamp of last successful loadCaptureState — used as a freshness gate. */
  lastFetchedAt: number | null;

  // Actions
  toggleRewind: () => Promise<void>;
  startCapture: () => Promise<void>;
  stopCapture: () => Promise<void>;
  takeSnapshot: () => Promise<void>;
  selectScreenshot: (id: string | null) => Promise<void>;
  search: (query: string) => Promise<void>;
  clearSearch: () => void;
  loadCaptureState: (force?: boolean) => Promise<void>;
  loadMore: (offset: number) => Promise<void>;
  updateConfig: (config: Partial<CaptureConfig>) => void;
  deleteScreenshot: (id: string) => void;
  clearAllScreenshots: () => Promise<void>;
  /** Cancel any in-flight eager image decode loop (e.g. when leaving Rewind). */
  cancelImageLoad: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Handle for the polling interval so we can clear it on stop. */
let captureIntervalId: ReturnType<typeof setInterval> | null = null;

/** Freshness window for loadCaptureState — DB rows + eager image decode. */
const STALE_MS = 30_000;

/** Token for the in-flight eager image decode loop. Bumping this aborts the prior loop. */
let imageLoadToken = 0;

/**
 * Normalise a timestamp string to ISO-8601.
 * Handles both ISO strings and legacy raw-millis strings (e.g. "1713052512000").
 */
function normalizeTimestamp(ts: string): string {
  // If it looks like a pure number (unix millis), convert it.
  if (/^\d{10,}$/.test(ts.trim())) {
    return new Date(Number(ts)).toISOString();
  }
  // Already ISO or some parseable format — validate it.
  const d = new Date(ts);
  if (isNaN(d.getTime())) {
    // Last resort: return current time so UI doesn't break.
    return new Date().toISOString();
  }
  return ts;
}

/** Convert a DB row (metadata only) to a Screenshot with empty data. */
function rowToScreenshot(row: {
  id: number;
  timestamp: string;
  app_name: string;
  window_title: string;
  ocr_text: string | null;
  width: number;
  height: number;
}): Screenshot {
  return {
    dbId: row.id,
    id: `db-${row.id}`,
    data: "",
    timestamp: normalizeTimestamp(row.timestamp),
    width: row.width,
    height: row.height,
    appName: row.app_name,
    windowTitle: row.window_title,
    ocrText: row.ocr_text ?? undefined,
  };
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useRewindStore = create<RewindState>((set, get) => ({
  rewindEnabled: true,
  inCommercialHours: isCommercialTime(),
  isCapturing: false,
  captureStartedAt: null,
  screenshots: [],
  selectedScreenshot: null,
  searchQuery: "",
  searchResults: [],
  isSearching: false,
  captureConfig: { interval_ms: 3000, quality: 80, max_width: 3000 },
  isLoading: false,
  isLoadingHistory: false,
  lastFetchedAt: null,

  // -------------------------------------------------------------------------
  // cancelImageLoad — bumps the token so any in-flight eager decode aborts.
  // -------------------------------------------------------------------------
  cancelImageLoad: () => {
    imageLoadToken += 1;
  },

  // -------------------------------------------------------------------------
  // loadCaptureState — called on Rewind mount to populate history from DB.
  // Gated by STALE_MS so revisits within the window skip the IPC + decode.
  // -------------------------------------------------------------------------
  loadCaptureState: async (force = false) => {
    const { lastFetchedAt, screenshots: existing } = get();
    if (!force && lastFetchedAt && Date.now() - lastFetchedAt < STALE_MS && existing.length > 0) {
      return;
    }

    set({ isLoadingHistory: true });
    try {
      const rows = await getRecentScreenshots(100, 0);
      if (rows.length === 0) {
        set({ isLoadingHistory: false, lastFetchedAt: Date.now() });
        return;
      }

      // Build Screenshot objects (data is empty for all; we lazy-load below).
      const screenshots = rows.map(rowToScreenshot);

      set({ screenshots, isLoadingHistory: false, lastFetchedAt: Date.now() });

      // Eagerly fetch image data sequentially so we can abort mid-loop when
      // the user navigates away. A new call (or cancelImageLoad) bumps the
      // token, causing this loop to bail out without further setState calls.
      const myToken = ++imageLoadToken;
      const startEagerLoad = () => {
        void (async () => {
          for (let i = 0; i < Math.min(EAGER_LOAD_COUNT, screenshots.length); i++) {
            if (myToken !== imageLoadToken) return;
            const s = screenshots[i];
            if (s.dbId <= 0) continue;
            try {
              const data = await getScreenshotImage(s.dbId);
              if (myToken !== imageLoadToken) return;
              if (!data) continue;
              set((state) => {
                const idx = state.screenshots.findIndex((x) => x.dbId === s.dbId);
                if (idx === -1) return state;
                const next = state.screenshots.slice();
                next[idx] = { ...next[idx], data };
                return { screenshots: next };
              });
            } catch {
              // Ignore individual failures — metadata still renders.
            }
          }
        })();
      };

      // Defer to idle so the next paint (often a different screen) goes first.
      const idle = (window as Window & { requestIdleCallback?: (cb: () => void) => void })
        .requestIdleCallback;
      if (typeof idle === "function") {
        idle(startEagerLoad);
      } else {
        setTimeout(startEagerLoad, 0);
      }

      // Catch up on embeddings for any OCR'd screenshots that missed the
      // capture-time embed (pre-feature rows, transient proxy failures, etc).
      backfillScreenshotEmbeddings().catch((e) =>
        console.warn("[Rewind] embedding backfill failed:", e),
      );
    } catch (err) {
      console.error("[Rewind] loadCaptureState failed:", err);
      set({ isLoadingHistory: false });
    }
  },

  // -------------------------------------------------------------------------
  // loadMore — pagination for history
  // -------------------------------------------------------------------------
  loadMore: async (offset: number) => {
    try {
      const rows = await getRecentScreenshots(50, offset);
      if (rows.length === 0) return;

      const newScreenshots = rows.map(rowToScreenshot);

      set((state) => {
        // Avoid duplicates by dbId.
        const existingIds = new Set(state.screenshots.map((s) => s.dbId));
        const deduped = newScreenshots.filter((s) => !existingIds.has(s.dbId));
        return {
          screenshots: [...state.screenshots, ...deduped].slice(0, MAX_SCREENSHOTS),
        };
      });
    } catch (err) {
      console.error("[Rewind] loadMore failed:", err);
    }
  },

  // -------------------------------------------------------------------------
  // toggleRewind — flip user intent; capture is gated by commercial hours.
  // When turning Rewind on, focus monitoring is auto-enabled too; when
  // turning it off, we stop focus if the user didn't enable it independently.
  // -------------------------------------------------------------------------
  toggleRewind: async () => {
    const { rewindEnabled } = get();
    if (rewindEnabled) {
      await get().stopCapture();
      set({ rewindEnabled: false });
      const focus = useFocusStore.getState();
      if (focus.focusEnabled) focus.stopFocusMonitoring();
    } else {
      set({ rewindEnabled: true });
      await get().startCapture();
      const focus = useFocusStore.getState();
      if (!focus.focusEnabled) focus.startFocusMonitoring();
    }
  },

  // -------------------------------------------------------------------------
  // startCapture — JS-side polling that calls the Rust plugin
  // -------------------------------------------------------------------------
  startCapture: async () => {
    if (get().isCapturing) return;
    if (!get().inCommercialHours) {
      // Outside commercial hours — watcher will start us when hours open.
      return;
    }

    const config = get().captureConfig;
    set({ isCapturing: true, captureStartedAt: Date.now() });

    // `max_width` is the *storage* cap. The Rust side captures at native
    // resolution internally, runs OCR on the native pixels (Vision needs
    // them to read small UI text correctly), and only then downscales to
    // this width before persisting / returning the JPEG to us. So we get
    // accurate OCR without paying native-res storage cost.
    const captureConfig = { ...config, max_width: 1280 };
    const intervalMs = config.interval_ms ?? 3000;

    let tickRunning = false;

    captureIntervalId = setInterval(async () => {
      if (tickRunning || !get().isCapturing) return;
      tickRunning = true;
      try {
        const [ocrResult, windowInfo] = await Promise.all([
          takeScreenshotWithOcr(captureConfig),
          getActiveWindow(),
        ]);

        // db_id is null when the Rust side detected a duplicate frame (dHash).
        // Skip adding to the timeline — the screen hasn't meaningfully changed.
        if (ocrResult.db_id == null) {
          return;
        }

        const screenshot: Screenshot = {
          dbId: ocrResult.db_id,
          id: nanoid(),
          data: ocrResult.image,
          timestamp: new Date().toISOString(),
          width: 0,
          height: 0,
          appName: windowInfo.app_name,
          windowTitle: windowInfo.window_title,
          ocrText: ocrResult.ocr_text || undefined,
        };

        set((state) => {
          const updated = [screenshot, ...state.screenshots].slice(0, MAX_SCREENSHOTS);
          return { screenshots: updated };
        });

        // Fire-and-forget semantic embedding. Failure is non-fatal — the
        // row stays in the DB and the backfill loop will pick it up later.
        if (ocrResult.ocr_text) {
          embedAndSaveScreenshot(
            ocrResult.db_id,
            ocrResult.ocr_text,
            windowInfo.app_name,
            windowInfo.window_title,
          ).catch((e) => console.warn("[Rewind] embed failed:", e));
        }
      } catch (err) {
        console.error("[Rewind] capture tick failed:", err);
      } finally {
        tickRunning = false;
      }
    }, intervalMs);
  },

  // -------------------------------------------------------------------------
  // stopCapture
  // -------------------------------------------------------------------------
  stopCapture: async () => {
    if (captureIntervalId !== null) {
      clearInterval(captureIntervalId);
      captureIntervalId = null;
    }
    set({ isCapturing: false, captureStartedAt: null });
  },

  // -------------------------------------------------------------------------
  // takeSnapshot — manual one-shot capture
  // -------------------------------------------------------------------------
  takeSnapshot: async () => {
    set({ isLoading: true });
    try {
      const config = get().captureConfig;
      const [ocrResult, windowInfo] = await Promise.all([
        takeScreenshotWithOcr(config),
        getActiveWindow(),
      ]);

      const screenshot: Screenshot = {
        dbId: ocrResult.db_id ?? 0,
        id: nanoid(),
        data: ocrResult.image,
        timestamp: new Date().toISOString(),
        width: 0,
        height: 0,
        appName: windowInfo.app_name,
        windowTitle: windowInfo.window_title,
        ocrText: ocrResult.ocr_text || undefined,
      };

      set((state) => {
        const updated = [screenshot, ...state.screenshots].slice(0, MAX_SCREENSHOTS);
        return { screenshots: updated, isLoading: false };
      });

      // Fire-and-forget semantic embedding for manual snapshots too.
      if (ocrResult.db_id != null && ocrResult.ocr_text) {
        embedAndSaveScreenshot(
          ocrResult.db_id,
          ocrResult.ocr_text,
          windowInfo.app_name,
          windowInfo.window_title,
        ).catch((e) => console.warn("[Rewind] embed failed:", e));
      }
    } catch (err) {
      console.error("[Rewind] takeSnapshot failed:", err);
      set({ isLoading: false });
    }
  },

  // -------------------------------------------------------------------------
  // selectScreenshot — lazy-loads image data if not already in memory
  // -------------------------------------------------------------------------
  selectScreenshot: async (id: string | null) => {
    if (id === null) {
      set({ selectedScreenshot: null });
      return;
    }

    const found = get().screenshots.find((s) => s.id === id);
    if (!found) {
      // Also check search results.
      const fromSearch = get().searchResults.find((s) => s.id === id) ?? null;
      if (!fromSearch) return;
      set({ selectedScreenshot: fromSearch });
      return;
    }

    // If image data is already loaded, select immediately.
    if (found.data) {
      set({ selectedScreenshot: found });
      return;
    }

    // Lazy-load the image from the DB.
    if (found.dbId > 0) {
      try {
        const data = await getScreenshotImage(found.dbId);
        const updated = { ...found, data };

        set((state) => {
          const screenshots = state.screenshots.map((s) => (s.id === id ? updated : s));
          return { screenshots, selectedScreenshot: updated };
        });
      } catch (err) {
        console.error("[Rewind] lazy image load failed:", err);
        // Select without data so the UI still shows metadata.
        set({ selectedScreenshot: found });
      }
    } else {
      set({ selectedScreenshot: found });
    }
  },

  // -------------------------------------------------------------------------
  // search — hybrid FTS5 + cosine-similarity search (mirrors Swift's
  // `RewindViewModel.performSearch`). FTS hits come first; vector-only hits
  // above the 0.5 similarity threshold are appended, dedup'd by dbId.
  // -------------------------------------------------------------------------
  search: async (query: string) => {
    set({ searchQuery: query, isSearching: true });

    if (!query.trim()) {
      set({ searchResults: [], isSearching: false });
      return;
    }

    try {
      // Run FTS and query-embedding in parallel. Embedding failure is
      // non-fatal — the FTS path still works offline.
      const [ftsRows, queryVec] = await Promise.all([
        searchScreenshots(query, 50),
        embedText(query, "RETRIEVAL_QUERY").catch(() => null),
      ]);

      const semanticHits = queryVec
        ? await searchScreenshotsSemantic(queryVec, 50, 0.5).catch(() => [])
        : [];

      const inMemoryById = new Map(get().screenshots.map((s) => [s.dbId, s]));

      // FTS results first, preserving BM25 order from Rust. Tag each as a
      // keyword hit so the UI can render the "Text match" badge.
      const ftsResults: Screenshot[] = ftsRows.map((row) => {
        const base = inMemoryById.get(row.id) ?? rowToScreenshot(row);
        return { ...base, matchType: "keyword" as const, matchScore: undefined };
      });
      const ftsIds = new Set(ftsRows.map((r) => r.id));

      // Vector-only hits — skip any already in the FTS set. If the row
      // isn't in-memory, fetch its metadata so it renders.
      const semanticOnly: Screenshot[] = [];
      for (const hit of semanticHits) {
        if (ftsIds.has(hit.id)) continue;
        let base = inMemoryById.get(hit.id);
        if (!base) {
          const row = await getScreenshotById(hit.id).catch(() => null);
          if (!row) continue;
          base = rowToScreenshot(row);
        }
        semanticOnly.push({
          ...base,
          matchType: "semantic",
          matchScore: hit.similarity,
        });
      }

      set({ searchResults: [...ftsResults, ...semanticOnly], isSearching: false });
    } catch (err) {
      console.error("[Rewind] search failed:", err);
      set({ isSearching: false });
    }
  },

  // -------------------------------------------------------------------------
  // clearSearch
  // -------------------------------------------------------------------------
  clearSearch: () => {
    set({ searchQuery: "", searchResults: [], isSearching: false });
  },

  // -------------------------------------------------------------------------
  // updateConfig
  // -------------------------------------------------------------------------
  updateConfig: (config) => {
    set((state) => ({
      captureConfig: { ...state.captureConfig, ...config },
    }));
  },

  // -------------------------------------------------------------------------
  // deleteScreenshot — removes from memory and DB
  // -------------------------------------------------------------------------
  deleteScreenshot: (id: string) => {
    const target = get().screenshots.find((s) => s.id === id);
    // Fire-and-forget DB delete if the screenshot has a dbId.
    if (target && target.dbId > 0) {
      deleteScreenshotByIdIpc(target.dbId).catch((e) =>
        console.error("[Rewind] DB delete failed:", e)
      );
    }
    set((state) => {
      const screenshots = state.screenshots.filter((s) => s.id !== id);
      const selectedScreenshot = state.selectedScreenshot?.id === id ? null : state.selectedScreenshot;
      const searchResults = state.searchQuery ? state.searchResults.filter((s) => s.id !== id) : state.searchResults;
      return { screenshots, selectedScreenshot, searchResults };
    });
  },

  // -------------------------------------------------------------------------
  // clearAllScreenshots — wipe everything from DB and memory
  // -------------------------------------------------------------------------
  clearAllScreenshots: async () => {
    try {
      const count = await deleteAllScreenshotsIpc();
      console.info(`[Rewind] Deleted ${count} screenshots from DB`);
    } catch (e) {
      console.error("[Rewind] clearAll DB failed:", e);
    }
    set({
      screenshots: [],
      selectedScreenshot: null,
      searchResults: [],
      searchQuery: "",
    });
  },
}));

// ---------------------------------------------------------------------------
// Commercial-time watcher — pauses capture outside work hours, resumes when
// the window reopens if the user had Rewind enabled.
// ---------------------------------------------------------------------------

watchCommercialTime(async (isOpen) => {
  const { rewindEnabled, isCapturing, startCapture, stopCapture } =
    useRewindStore.getState();
  useRewindStore.setState({ inCommercialHours: isOpen });

  if (isOpen) {
    if (rewindEnabled && !isCapturing) {
      await startCapture();
    }
  } else {
    if (isCapturing) {
      await stopCapture();
    }
  }
});
