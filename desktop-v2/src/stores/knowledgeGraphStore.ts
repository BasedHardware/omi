import { create } from "zustand";
import { useAuthStore } from "./authStore";
import { api } from "../services/api";

export type NodeType = "person" | "place" | "thing" | "concept" | "organization";

export interface KnowledgeNode {
  id: string;
  label: string;
  node_type: NodeType;
  aliases?: string[];
  memory_ids?: string[];
}

export interface KnowledgeEdge {
  id: string;
  source_id: string;
  target_id: string;
  label: string;
  memory_ids?: string[];
}

interface GraphResponse {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
}

interface GraphState {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  isLoading: boolean;
  isRebuilding: boolean;
  hasLoaded: boolean;
  error: string | null;
  loadGraph: () => Promise<void>;
  rebuildGraph: () => Promise<void>;
}

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_ATTEMPTS = 30;

export const useKnowledgeGraphStore = create<GraphState>((set, get) => ({
  nodes: [],
  edges: [],
  isLoading: false,
  isRebuilding: false,
  hasLoaded: false,
  error: null,

  loadGraph: async () => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    set({ isLoading: true, error: null });
    try {
      const data = await api.get<GraphResponse>("/v1/knowledge-graph");
      set({
        nodes: Array.isArray(data?.nodes) ? data.nodes : [],
        edges: Array.isArray(data?.edges) ? data.edges : [],
        isLoading: false,
        hasLoaded: true,
      });
    } catch (error) {
      console.error("Failed to load knowledge graph:", error);
      set({ isLoading: false, hasLoaded: true, error: String(error) });
    }
  },

  rebuildGraph: async () => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;
    if (get().isRebuilding) return;

    set({ isRebuilding: true, error: null });
    try {
      await api.post("/v1/knowledge-graph/rebuild", {});
    } catch (error) {
      console.error("Failed to trigger rebuild:", error);
      set({ isRebuilding: false, error: String(error) });
      return;
    }

    const previousNodeCount = get().nodes.length;
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      try {
        const data = await api.get<GraphResponse>("/v1/knowledge-graph");
        const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
        const edges = Array.isArray(data?.edges) ? data.edges : [];
        if (nodes.length !== previousNodeCount || edges.length > 0) {
          set({ nodes, edges, hasLoaded: true, isRebuilding: false });
          return;
        }
      } catch (error) {
        console.warn("Poll failed:", error);
      }
    }

    try {
      const data = await api.get<GraphResponse>("/v1/knowledge-graph");
      set({
        nodes: Array.isArray(data?.nodes) ? data.nodes : [],
        edges: Array.isArray(data?.edges) ? data.edges : [],
        hasLoaded: true,
        isRebuilding: false,
      });
    } catch (error) {
      set({ isRebuilding: false, error: String(error) });
    }
  },
}));
