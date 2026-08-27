'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { createSignal } from '@tschk/moonshine';
import { useSignalValue } from '@/lib/signals';
import type { KnowledgeGraph, KnowledgeGraphNodeType } from '@/types/conversation';
import { getKnowledgeGraph, rebuildKnowledgeGraph } from '@/features/memories/api';

export const NODE_COLORS: Record<KnowledgeGraphNodeType | 'user', string> = {
  person: '#00FFFF',
  place: '#00FF9D',
  organization: '#FFA500',
  thing: '#A855F7',
  concept: '#3B82F6',
  user: '#FFFFFF',
};

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface GraphNode {
  id: string;
  label: string;
  nodeType: KnowledgeGraphNodeType | 'user';
  color: string;
  aliases: string[];
  memoryIds: string[];
  val: number;
  x?: number;
  y?: number;
  z?: number;
}

export interface GraphLink {
  id: string;
  source: string;
  target: string;
  label: string;
  memoryIds: string[];
}

export interface UseKnowledgeGraphReturn {
  graphData: GraphData | null;
  loading: boolean;
  error: string | null;
  rebuilding: boolean;
  selectedNode: GraphNode | null;
  refresh: () => Promise<void>;
  rebuild: () => Promise<void>;
  selectNode: (node: GraphNode | null) => void;
  getNodeById: (id: string) => GraphNode | undefined;
  getConnectedNodes: (nodeId: string) => GraphNode[];
  getNodeMemoryCount: (nodeId: string) => number;
}

function toGraphData(rawData: KnowledgeGraph): GraphData {
  const userNode: GraphNode = {
    id: 'user',
    label: 'You',
    nodeType: 'user',
    color: '#FFFFFF',
    aliases: [],
    memoryIds: [],
    val: 40,
  };

  const nodes: GraphNode[] = [
    userNode,
    ...rawData.nodes.map(
      (node): GraphNode => ({
        id: node.id,
        label: node.label,
        nodeType: node.node_type,
        color: NODE_COLORS[node.node_type] || NODE_COLORS.thing,
        aliases: node.aliases,
        memoryIds: node.memory_ids,
        val: Math.max(3, Math.min(10, node.memory_ids.length * 2)),
      }),
    ),
  ];

  const links: GraphLink[] = rawData.edges.map((edge): GraphLink => ({
    id: edge.id,
    source: edge.source_id,
    target: edge.target_id,
    label: edge.label,
    memoryIds: edge.memory_ids,
  }));

  const nodesWithConnections = new Set(links.flatMap((l) => [l.source, l.target]));

  rawData.nodes.forEach((node) => {
    if (!nodesWithConnections.has(node.id)) {
      links.push({
        id: `user-${node.id}`,
        source: 'user',
        target: node.id,
        label: 'related to',
        memoryIds: node.memory_ids,
      });
    }
  });

  return { nodes, links };
}

export function createKnowledgeGraphStore() {
  const rawData = createSignal<KnowledgeGraph | null>(null);
  const loading = createSignal(true);
  const error = createSignal<string | null>(null);
  const rebuilding = createSignal(false);
  const selectedNode = createSignal<GraphNode | null>(null);

  const load = async () => {
    loading.set(true);
    error.set(null);
    try {
      rawData.set(await getKnowledgeGraph());
    } catch (err) {
      error.set(err instanceof Error ? err.message : 'Failed to load knowledge graph');
    } finally {
      loading.set(false);
    }
  };

  const rebuild = async () => {
    rebuilding.set(true);
    error.set(null);
    try {
      await rebuildKnowledgeGraph();
      await new Promise((resolve) => setTimeout(resolve, 2000));
      await load();
    } catch (err) {
      error.set(err instanceof Error ? err.message : 'Failed to rebuild knowledge graph');
    } finally {
      rebuilding.set(false);
    }
  };

  return { rawData, loading, error, rebuilding, selectedNode, load, rebuild };
}

export function useKnowledgeGraph(): UseKnowledgeGraphReturn {
  const store = useMemo(() => createKnowledgeGraphStore(), []);

  useEffect(() => {
    void store.load();
  }, [store]);

  const rawData = useSignalValue(store.rawData);
  const loading = useSignalValue(store.loading);
  const error = useSignalValue(store.error);
  const rebuilding = useSignalValue(store.rebuilding);
  const selectedNode = useSignalValue(store.selectedNode);

  const graphData = useMemo(() => (rawData ? toGraphData(rawData) : null), [rawData]);

  const getNodeById = useCallback(
    (id: string): GraphNode | undefined => graphData?.nodes.find((n) => n.id === id),
    [graphData],
  );

  const getConnectedNodes = useCallback(
    (nodeId: string): GraphNode[] => {
      if (!graphData) return [];

      const connectedIds = new Set<string>();
      graphData.links.forEach((link) => {
        if (
          link.source === nodeId ||
          (typeof link.source === 'object' && (link.source as GraphNode).id === nodeId)
        ) {
          const targetId =
            typeof link.target === 'object' ? (link.target as GraphNode).id : link.target;
          connectedIds.add(targetId);
        }
        if (
          link.target === nodeId ||
          (typeof link.target === 'object' && (link.target as GraphNode).id === nodeId)
        ) {
          const sourceId =
            typeof link.source === 'object' ? (link.source as GraphNode).id : link.source;
          connectedIds.add(sourceId);
        }
      });

      return graphData.nodes.filter((n) => connectedIds.has(n.id));
    },
    [graphData],
  );

  const getNodeMemoryCount = useCallback(
    (nodeId: string): number => getNodeById(nodeId)?.memoryIds.length || 0,
    [getNodeById],
  );

  return {
    graphData,
    loading,
    error,
    rebuilding,
    selectedNode,
    refresh: useCallback(() => store.load(), [store]),
    rebuild: useCallback(() => store.rebuild(), [store]),
    selectNode: useCallback((node: GraphNode | null) => store.selectedNode.set(node), [store]),
    getNodeById,
    getConnectedNodes,
    getNodeMemoryCount,
  };
}
