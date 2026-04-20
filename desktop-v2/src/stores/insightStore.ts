/**
 * Insight store — TypeScript port of Swift `InsightStorage`.
 *
 * Insights are persisted server-side as memories tagged with "tips" (plus a
 * category tag like "productivity"). This store provides a filtered view of
 * the local memory DB plus backend memories, so the Insights page can render
 * without re-implementing the sync logic the memory store already handles.
 *
 * Backend contract (GET /v3/memories?tags=tips):
 *   - content → insight text
 *   - headline / reasoning / source_app / confidence → per-insight metadata
 *   - context_summary / current_activity → context shown in detail sheet
 *   - tags → `["tips", "<category>"]`
 *   - is_dismissed flag supported server-side
 *
 * The store reads from:
 *   1. Local sqlite via `get_memories_by_tag("tips")` — immediate/offline.
 *   2. Backend via `/v3/memories?tags=tips&include_dismissed=true` — authoritative.
 * Results are merged by id (backend wins when both exist).
 */

import { create } from "zustand";
import { invoke } from "@tauri-apps/api/core";
import { useAuthStore } from "./authStore";
import { api } from "../services/api";

export type InsightCategory =
  | "productivity"
  | "communication"
  | "learning"
  | "health"
  | "other";

export const INSIGHT_CATEGORIES: InsightCategory[] = [
  "productivity",
  "communication",
  "learning",
  "health",
  "other",
];

export const INSIGHT_CATEGORY_LABEL: Record<InsightCategory, string> = {
  productivity: "Productivity",
  communication: "Communication",
  learning: "Learning",
  health: "Health",
  other: "Other",
};

/** What the Insights page consumes. */
export interface StoredInsight {
  id: string;
  content: string;
  headline: string | null;
  reasoning: string | null;
  category: InsightCategory;
  sourceApp: string;
  confidence: number;
  contextSummary: string;
  currentActivity: string;
  createdAt: string;
  isRead: boolean;
  isDismissed: boolean;
  /** True when this record only exists in the local DB (not yet on backend). */
  _localOnly?: boolean;
}

// ---------------------------------------------------------------------------
// Wire types
// ---------------------------------------------------------------------------

interface LocalMemoryRow {
  id: string;
  content: string;
  category?: string | null;
  source_app?: string | null;
  headline?: string | null;
  reasoning?: string | null;
  confidence?: number | null;
  context_summary?: string | null;
  current_activity?: string | null;
  tags_json?: string | null;
  backend_id?: string | null;
  backend_synced: boolean;
  is_dismissed: boolean;
  deleted: boolean;
  created_at: string;
  updated_at: string;
}

interface BackendMemory {
  id: string;
  content: string;
  category?: string;
  tags?: string[];
  source_app?: string | null;
  headline?: string | null;
  reasoning?: string | null;
  confidence?: number | null;
  context_summary?: string | null;
  current_activity?: string | null;
  is_read?: boolean | null;
  is_dismissed?: boolean | null;
  created_at: string;
  updated_at?: string;
}

// ---------------------------------------------------------------------------
// Mapping
// ---------------------------------------------------------------------------

function parseTags(tagsJson: string | null | undefined): string[] {
  if (!tagsJson) return [];
  try {
    const arr = JSON.parse(tagsJson);
    if (Array.isArray(arr)) return arr.filter((t): t is string => typeof t === "string");
  } catch {
    // ignore
  }
  return [];
}

function categoryFromTags(tags: string[]): InsightCategory {
  for (const t of tags) {
    if (t === "tips") continue;
    const lower = t.toLowerCase();
    if (
      lower === "productivity" ||
      lower === "communication" ||
      lower === "learning" ||
      lower === "health" ||
      lower === "other"
    ) {
      return lower as InsightCategory;
    }
  }
  return "other";
}

function localToInsight(row: LocalMemoryRow): StoredInsight {
  const tags = parseTags(row.tags_json);
  return {
    id: row.id,
    content: row.content,
    headline: row.headline ?? null,
    reasoning: row.reasoning ?? null,
    category: categoryFromTags(tags),
    sourceApp: row.source_app ?? "Unknown",
    confidence: row.confidence ?? 0.5,
    contextSummary: row.context_summary ?? "",
    currentActivity: row.current_activity ?? "",
    createdAt: row.created_at,
    isRead: false, // local DB doesn't track read state
    isDismissed: row.is_dismissed,
    _localOnly: !row.backend_synced,
  };
}

function backendToInsight(m: BackendMemory): StoredInsight {
  const tags = m.tags ?? [];
  return {
    id: m.id,
    content: m.content,
    headline: m.headline ?? null,
    reasoning: m.reasoning ?? null,
    category: categoryFromTags(tags),
    sourceApp: m.source_app ?? "Unknown",
    confidence: m.confidence ?? 0.5,
    contextSummary: m.context_summary ?? "",
    currentActivity: m.current_activity ?? "",
    createdAt: m.created_at,
    isRead: m.is_read ?? false,
    isDismissed: m.is_dismissed ?? false,
  };
}

/** Merge backend (authoritative) with local-only insights (not yet synced). */
function merge(backend: StoredInsight[], local: StoredInsight[]): StoredInsight[] {
  const seen = new Set(backend.map((i) => i.id));
  const combined = [...backend, ...local.filter((i) => !seen.has(i.id))];
  combined.sort((a, b) => {
    const ta = new Date(a.createdAt).getTime();
    const tb = new Date(b.createdAt).getTime();
    return tb - ta;
  });
  return combined;
}

// ---------------------------------------------------------------------------
// Backend helpers
// ---------------------------------------------------------------------------

const TIPS_TAG = "tips";

async function fetchBackendInsights(): Promise<StoredInsight[]> {
  try {
    const data = await api.get<BackendMemory[]>(
      `/v3/memories?limit=100&tags=${TIPS_TAG}&include_dismissed=true`,
    );
    if (!Array.isArray(data)) return [];
    return data.map(backendToInsight);
  } catch (err) {
    console.warn("[InsightStore] backend fetch failed:", err);
    return [];
  }
}

async function fetchLocalInsights(): Promise<StoredInsight[]> {
  try {
    const rows = await invoke<LocalMemoryRow[]>("get_memories_by_tag", {
      tag: TIPS_TAG,
      limit: 200,
    });
    if (!Array.isArray(rows)) return [];
    return rows.filter((r) => !r.deleted).map(localToInsight);
  } catch (err) {
    console.warn("[InsightStore] local fetch failed:", err);
    return [];
  }
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

const STALE_MS = 30_000;

interface PrependPayload {
  id: string;
  content: string;
  category: InsightCategory;
  sourceApp: string;
  confidence: number;
  headline: string | null;
  reasoning: string | null;
  contextSummary: string;
  currentActivity: string;
  createdAt: string;
}

interface InsightState {
  insights: StoredInsight[];
  isLoading: boolean;
  query: string;
  categoryFilter: InsightCategory | null;
  showDismissed: boolean;
  lastFetchedAt: number | null;

  load: (force?: boolean) => Promise<void>;
  prependLocalInsight: (payload: PrependPayload) => void;
  markAsRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  dismissInsight: (id: string) => Promise<void>;
  deleteInsight: (id: string) => Promise<void>;
  clearAll: () => Promise<void>;
  setQuery: (q: string) => void;
  setCategoryFilter: (c: InsightCategory | null) => void;
  setShowDismissed: (v: boolean) => void;

  /** Insights after applying search + category filters + dismissed toggle. */
  filtered: () => StoredInsight[];
  /** All non-dismissed insights (used for counts). */
  visible: () => StoredInsight[];
  /** Unread + not-dismissed count. */
  unreadCount: () => number;
  /** How many insights match a given category (respecting showDismissed). */
  countForCategory: (c: InsightCategory | null) => number;
}

export const useInsightStore = create<InsightState>((set, get) => ({
  insights: [],
  isLoading: false,
  query: "",
  categoryFilter: null,
  showDismissed: false,
  lastFetchedAt: null,

  setQuery: (q) => set({ query: q }),
  setCategoryFilter: (c) => set({ categoryFilter: c }),
  setShowDismissed: (v) => set({ showDismissed: v }),

  load: async (force = false) => {
    const { lastFetchedAt, insights } = get();
    if (
      !force &&
      lastFetchedAt &&
      Date.now() - lastFetchedAt < STALE_MS &&
      insights.length > 0
    ) {
      return;
    }

    set({ isLoading: true });

    const token = useAuthStore.getState().idToken;
    const [backendList, localList] = await Promise.all([
      token ? fetchBackendInsights() : Promise.resolve<StoredInsight[]>([]),
      fetchLocalInsights(),
    ]);

    set({
      insights: merge(backendList, localList),
      isLoading: false,
      lastFetchedAt: Date.now(),
    });
  },

  prependLocalInsight: (payload) => {
    const entry: StoredInsight = {
      id: payload.id,
      content: payload.content,
      headline: payload.headline,
      reasoning: payload.reasoning,
      category: payload.category,
      sourceApp: payload.sourceApp,
      confidence: payload.confidence,
      contextSummary: payload.contextSummary,
      currentActivity: payload.currentActivity,
      createdAt: payload.createdAt,
      isRead: false,
      isDismissed: false,
      _localOnly: true,
    };
    const { insights } = get();
    if (insights.some((i) => i.id === entry.id)) return;
    set({ insights: [entry, ...insights] });
  },

  markAsRead: async (id) => {
    const prev = get().insights;
    set({
      insights: prev.map((i) => (i.id === id ? { ...i, isRead: true } : i)),
    });
    const token = useAuthStore.getState().idToken;
    if (!token) return;
    try {
      await api.post(`/v3/memories/${id}/read`, { is_read: true });
    } catch (err) {
      console.warn("[InsightStore] markAsRead failed:", err);
    }
  },

  markAllRead: async () => {
    const prev = get().insights;
    set({ insights: prev.map((i) => ({ ...i, isRead: true })) });
    const token = useAuthStore.getState().idToken;
    if (!token) return;
    try {
      await api.post("/v3/memories/mark-all-read", {});
    } catch (err) {
      console.warn("[InsightStore] markAllRead failed:", err);
    }
  },

  dismissInsight: async (id) => {
    const prev = get().insights;
    set({
      insights: prev.map((i) => (i.id === id ? { ...i, isDismissed: true } : i)),
    });
    const target = prev.find((i) => i.id === id);
    if (target?._localOnly) {
      try {
        await invoke("dismiss_memory", { id });
      } catch (err) {
        console.warn("[InsightStore] local dismiss failed:", err);
      }
      return;
    }
    const token = useAuthStore.getState().idToken;
    if (!token) return;
    try {
      await api.post(`/v3/memories/${id}/read`, { is_dismissed: true });
    } catch (err) {
      console.warn("[InsightStore] dismiss failed:", err);
    }
  },

  deleteInsight: async (id) => {
    const prev = get().insights;
    const target = prev.find((i) => i.id === id);
    set({ insights: prev.filter((i) => i.id !== id) });

    if (target?._localOnly) {
      try {
        await invoke("delete_memory", { id, hard: false });
      } catch (err) {
        console.warn("[InsightStore] local delete failed:", err);
        set({ insights: prev });
      }
      return;
    }

    const token = useAuthStore.getState().idToken;
    if (!token) {
      set({ insights: prev });
      return;
    }
    try {
      await api.delete(`/v3/memories/${id}`);
    } catch (err) {
      console.warn("[InsightStore] delete failed:", err);
      set({ insights: prev });
    }
  },

  clearAll: async () => {
    const prev = get().insights;
    set({ insights: [] });
    for (const insight of prev) {
      if (insight._localOnly) {
        try {
          await invoke("delete_memory", { id: insight.id, hard: false });
        } catch {
          // ignore
        }
        continue;
      }
      try {
        await api.delete(`/v3/memories/${insight.id}`);
      } catch {
        // ignore
      }
    }
  },

  visible: () => get().insights.filter((i) => !i.isDismissed),

  filtered: () => {
    const { insights, query, categoryFilter, showDismissed } = get();
    const normalized = query.trim().toLowerCase();
    let result = showDismissed ? insights : insights.filter((i) => !i.isDismissed);
    if (categoryFilter !== null) {
      result = result.filter((i) => i.category === categoryFilter);
    }
    if (normalized.length > 0) {
      result = result.filter((i) => {
        const content = i.content.toLowerCase();
        const context = i.contextSummary.toLowerCase();
        const activity = i.currentActivity.toLowerCase();
        return (
          content.includes(normalized) ||
          context.includes(normalized) ||
          activity.includes(normalized)
        );
      });
    }
    return result;
  },

  unreadCount: () =>
    get().insights.filter((i) => !i.isRead && !i.isDismissed).length,

  countForCategory: (c) => {
    const { insights, showDismissed } = get();
    const base = showDismissed ? insights : insights.filter((i) => !i.isDismissed);
    if (c === null) return base.length;
    return base.filter((i) => i.category === c).length;
  },
}));
