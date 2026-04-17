import { create } from "zustand";
import { listen } from "@tauri-apps/api/event";
import { useAuthStore } from "./authStore";
import { api } from "../services/api";
import {
  getLocalSegments,
  listLocalSessions,
  type LocalSegment,
  type LocalSession,
} from "../services/audioCapture";
import type { AppResponse } from "../types/app";

export interface ActionItem {
  description: string;
  completed: boolean;
}

/**
 * Sync status for a conversation.
 *  - `"synced"`       — lives in the backend and (optionally) locally.
 *  - `"syncing"`      — local-only, currently being uploaded or queued for upload.
 *  - `"failed"`       — local-only, upload failed after retries (user can trigger manual retry).
 *  - `"local_only"`   — still recording, or never attempted upload.
 */
export type ConversationSyncStatus = "synced" | "syncing" | "failed" | "local_only";

export interface Conversation {
  /**
   * Backend conversation id, OR a synthetic id for local-only meetings
   * formatted as `local_<localSessionId>` so React keys don't collide.
   */
  id: string;
  structured: {
    title: string;
    overview: string;
    emoji?: string;
    category?: string;
    action_items?: ActionItem[];
  };
  created_at: string;
  updated_at: string;
  started_at?: string;
  finished_at?: string;
  transcript_segments?: TranscriptSegment[];
  starred?: boolean;
  apps_results?: AppResponse[];
  /** Present when this conversation has a local SQLite row tracking it. */
  syncStatus?: ConversationSyncStatus;
  /** Local SQLite session id. Present whenever `syncStatus` is set. */
  localId?: number | null;
}

export interface TranscriptSegment {
  text: string;
  speaker: string;
  start: number;
  end: number;
}

function mapLocalStatus(session: LocalSession): ConversationSyncStatus {
  switch (session.status) {
    case "pending_upload":
    case "uploading":
      return "syncing";
    case "failed":
      return "failed";
    case "recording":
      return "local_only";
    case "completed":
      // Completed without a backend_id shouldn't happen in practice — treat
      // it as local-only so the UI shows *something* rather than hiding it.
      return session.backend_id ? "synced" : "local_only";
    default:
      return "local_only";
  }
}

function localSessionToConversation(session: LocalSession): Conversation {
  const isRecording = session.status === "recording";
  const title = isRecording ? "Recording…" : "Saving meeting…";
  const startedAt = session.started_at || session.created_at;
  const finishedAt = session.finished_at || session.updated_at;
  return {
    id: `local_${session.id}`,
    structured: {
      title,
      overview: "",
      emoji: undefined,
      category: undefined,
      action_items: [],
    },
    created_at: startedAt,
    updated_at: session.updated_at,
    started_at: startedAt,
    finished_at: finishedAt,
    transcript_segments: [],
    starred: false,
    apps_results: [],
    syncStatus: mapLocalStatus(session),
    localId: session.id,
  };
}

function localSegmentToTranscript(seg: LocalSegment): TranscriptSegment {
  return {
    text: seg.text,
    speaker: seg.speaker,
    start: seg.start_time,
    end: seg.end_time,
  };
}

const STALE_MS = 30_000;

interface ConversationState {
  conversations: Conversation[];
  isLoading: boolean;
  selectedConversation: Conversation | null;
  isLoadingDetail: boolean;
  searchQuery: string;
  lastFetchedAt: number | null;
  loadConversations: (force?: boolean) => Promise<void>;
  searchConversations: (query: string) => void;
  selectConversation: (conversation: Conversation | null) => void;
  refreshSelectedConversation: () => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [],
  isLoading: false,
  selectedConversation: null,
  isLoadingDetail: false,
  searchQuery: "",
  lastFetchedAt: null,

  loadConversations: async (force = false) => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    const { lastFetchedAt, conversations } = get();
    if (!force && lastFetchedAt && Date.now() - lastFetchedAt < STALE_MS && conversations.length > 0) {
      return;
    }

    set({ isLoading: true });

    // Kick off both fetches in parallel. Local sessions are best-effort — if
    // the plugin isn't ready yet, we still want to render the backend list.
    const backendPromise = api
      .get<Conversation[]>(
        "/v1/conversations?limit=50&offset=0&statuses=completed&include_discarded=false",
      )
      .catch((error) => {
        console.error("Failed to load conversations:", error);
        return [] as Conversation[];
      });

    const localPromise = listLocalSessions().catch((error) => {
      console.error("Failed to list local sessions:", error);
      return [] as LocalSession[];
    });

    try {
      const [backendRaw, localSessions] = await Promise.all([
        backendPromise,
        localPromise,
      ]);
      const backend = Array.isArray(backendRaw) ? backendRaw : [];

      // Index local sessions by backend_id so we can attach sync metadata
      // to already-synced backend conversations.
      const localByBackendId = new Map<string, LocalSession>();
      for (const s of localSessions) {
        if (s.backend_id) localByBackendId.set(s.backend_id, s);
      }

      const hydratedBackend: Conversation[] = backend.map((c) => {
        const local = localByBackendId.get(c.id);
        if (!local) return c;
        return {
          ...c,
          localId: local.id,
          syncStatus: "synced",
        };
      });

      // Local-only rows: any local session whose backend_id is missing or
      // doesn't match a backend row we know about.
      const backendIds = new Set(backend.map((c) => c.id));
      const localOnly = localSessions
        .filter(
          (s) => !s.backend_id || !backendIds.has(s.backend_id),
        )
        .map(localSessionToConversation);

      // Prepend local-only so in-progress / syncing meetings float to the top.
      // Sort by started_at DESC so the newest pending one is first.
      localOnly.sort((a, b) => {
        const ta = new Date(a.started_at || a.created_at).getTime();
        const tb = new Date(b.started_at || b.created_at).getTime();
        return tb - ta;
      });

      set({
        conversations: [...localOnly, ...hydratedBackend],
        isLoading: false,
        lastFetchedAt: Date.now(),
      });
    } catch (error) {
      console.error("Failed to merge conversations:", error);
      set({ isLoading: false });
    }
  },

  searchConversations: (query: string) => {
    set({ searchQuery: query });
    if (!query.trim()) {
      get().loadConversations();
    }
  },

  selectConversation: async (conversation: Conversation | null) => {
    if (!conversation) {
      set({ selectedConversation: null });
      return;
    }

    // Show the conversation from the list immediately
    set({ selectedConversation: conversation, isLoadingDetail: true });

    const isLocalOnly =
      !!conversation.localId &&
      (!conversation.syncStatus ||
        conversation.syncStatus === "syncing" ||
        conversation.syncStatus === "failed" ||
        conversation.syncStatus === "local_only") &&
      // A local-only conversation always has our `local_` id prefix.
      typeof conversation.id === "string" &&
      conversation.id.startsWith("local_");

    if (isLocalOnly && conversation.localId != null) {
      // Hydrate transcript segments from local SQLite.
      try {
        const segments = await getLocalSegments(conversation.localId);
        const detail: Conversation = {
          ...conversation,
          transcript_segments: segments.map(localSegmentToTranscript),
        };
        // Only apply if the user hasn't navigated away mid-fetch.
        if (get().selectedConversation?.id === conversation.id) {
          set({ selectedConversation: detail, isLoadingDetail: false });
        }
      } catch (error) {
        console.error("Failed to load local segments:", error);
        if (get().selectedConversation?.id === conversation.id) {
          set({ isLoadingDetail: false });
        }
      }
      return;
    }

    // Backend-backed conversation — fetch full detail (includes transcript_segments)
    try {
      const detail = await api.get<Conversation>(
        `/v1/conversations/${conversation.id}`,
      );
      // Preserve any sync metadata we already attached during merge.
      const merged: Conversation = {
        ...detail,
        localId: conversation.localId ?? detail.localId,
        syncStatus: conversation.syncStatus ?? detail.syncStatus,
      };
      if (get().selectedConversation?.id === conversation.id) {
        set({ selectedConversation: merged, isLoadingDetail: false });
      }
    } catch (error) {
      console.error("Failed to load conversation detail:", error);
      set({ isLoadingDetail: false });
    }
  },

  deleteConversation: async (id: string) => {
    await api.delete(`/v1/conversations/${id}`);
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      selectedConversation:
        state.selectedConversation?.id === id ? null : state.selectedConversation,
    }));
  },

  refreshSelectedConversation: async () => {
    const current = get().selectedConversation;
    if (!current) return;
    // Local-only rows don't exist on the backend yet — nothing to refresh.
    if (typeof current.id === "string" && current.id.startsWith("local_")) return;
    try {
      const detail = await api.get<Conversation>(
        `/v1/conversations/${current.id}`,
      );
      // Guard against the user navigating away mid-refetch.
      if (get().selectedConversation?.id === detail.id) {
        set({
          selectedConversation: {
            ...detail,
            localId: current.localId ?? detail.localId,
            syncStatus: current.syncStatus ?? detail.syncStatus,
          },
        });
      }
    } catch (error) {
      console.error("Failed to refresh conversation detail:", error);
    }
  },
}));

// ---------------------------------------------------------------------------
// Background sync subscription
// ---------------------------------------------------------------------------
//
// When the Rust-side retry service successfully uploads a local session, it
// emits `meeting:synced`. We reload the merged list so the local-only
// placeholder gets replaced by the backend-hydrated conversation.

interface MeetingSyncedEvent {
  session_id: number;
  backend_id: string;
}

listen<MeetingSyncedEvent>("meeting:synced", () => {
  void useConversationStore.getState().loadConversations(true);
})
  .then(() => console.log("[Conversations] subscribed to meeting:synced"))
  .catch((err) => {
    console.error("[Conversations] failed to subscribe to meeting:synced:", err);
  });
