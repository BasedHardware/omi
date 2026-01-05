'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import type { KnowledgeGraph, KnowledgeGraphNode, KnowledgeGraphEdge, KnowledgeGraphNodeType } from '@/types/conversation';
import { getKnowledgeGraph, rebuildKnowledgeGraph } from '@/lib/api';

// Node colors matching mobile app
export const NODE_COLORS: Record<KnowledgeGraphNodeType | 'user', string> = {
  person: '#00FFFF',      // Cyan
  place: '#00FF9D',       // Green
  organization: '#FFA500', // Orange
  thing: '#A855F7',       // Purple
  concept: '#3B82F6',     // Blue
  user: '#FFFFFF',        // White (center node)
};

// Graph data format for react-force-graph
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
  val: number; // Node size
  // Position properties added by force-graph during simulation
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
  // Actions
  refresh: () => Promise<void>;
  rebuild: () => Promise<void>;
  selectNode: (node: GraphNode | null) => void;
  // Helpers
  getNodeById: (id: string) => GraphNode | undefined;
  getConnectedNodes: (nodeId: string) => GraphNode[];
  getNodeMemoryCount: (nodeId: string) => number;
}

export function useKnowledgeGraph(): UseKnowledgeGraphReturn {
  const [rawData, setRawData] = useState<KnowledgeGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const initialFetchDone = useRef(false);

  // Transform raw data to graph format
  const graphData = useMemo((): GraphData | null => {
    if (!rawData) return null;

    // Create user node as the center - make it large and white
    const userNode: GraphNode = {
      id: 'user',
      label: 'You',
      nodeType: 'user',
      color: '#FFFFFF', // Pure white
      aliases: [],
      memoryIds: [],
      val: 40, // Much larger size for center node
    };

    // Transform nodes
    const nodes: GraphNode[] = [
      userNode,
      ...rawData.nodes.map((node): GraphNode => ({
        id: node.id,
        label: node.label,
        nodeType: node.node_type,
        color: NODE_COLORS[node.node_type] || NODE_COLORS.thing,
        aliases: node.aliases,
        memoryIds: node.memory_ids,
        val: Math.max(3, Math.min(10, node.memory_ids.length * 2)), // Size based on memory count
      })),
    ];

    // Transform edges/links
    const links: GraphLink[] = rawData.edges.map((edge): GraphLink => ({
      id: edge.id,
      source: edge.source_id,
      target: edge.target_id,
      label: edge.label,
      memoryIds: edge.memory_ids,
    }));

    // Add links from user to all nodes (so they cluster around the center)
    const nodesWithConnections = new Set(links.flatMap((l) => [l.source, l.target]));

    // For nodes without connections, link them directly to user
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
  }, [rawData]);

  // Fetch graph data
  const fetchGraph = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getKnowledgeGraph();
      setRawData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load knowledge graph');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    if (!initialFetchDone.current) {
      initialFetchDone.current = true;
      fetchGraph();
    }
  }, [fetchGraph]);

  // Refresh
  const refresh = useCallback(async () => {
    initialFetchDone.current = true;
    await fetchGraph();
  }, [fetchGraph]);

  // Rebuild graph
  const rebuild = useCallback(async () => {
    try {
      setRebuilding(true);
      setError(null);
      await rebuildKnowledgeGraph();
      // Wait a bit then refresh to get updated data
      await new Promise((resolve) => setTimeout(resolve, 2000));
      await fetchGraph();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rebuild knowledge graph');
    } finally {
      setRebuilding(false);
    }
  }, [fetchGraph]);

  // Select node
  const selectNode = useCallback((node: GraphNode | null) => {
    setSelectedNode(node);
  }, []);

  // Get node by ID
  const getNodeById = useCallback((id: string): GraphNode | undefined => {
    return graphData?.nodes.find((n) => n.id === id);
  }, [graphData]);

  // Get connected nodes
  const getConnectedNodes = useCallback((nodeId: string): GraphNode[] => {
    if (!graphData) return [];

    const connectedIds = new Set<string>();
    graphData.links.forEach((link) => {
      if (link.source === nodeId || (typeof link.source === 'object' && (link.source as GraphNode).id === nodeId)) {
        const targetId = typeof link.target === 'object' ? (link.target as GraphNode).id : link.target;
        connectedIds.add(targetId);
      }
      if (link.target === nodeId || (typeof link.target === 'object' && (link.target as GraphNode).id === nodeId)) {
        const sourceId = typeof link.source === 'object' ? (link.source as GraphNode).id : link.source;
        connectedIds.add(sourceId);
      }
    });

    return graphData.nodes.filter((n) => connectedIds.has(n.id));
  }, [graphData]);

  // Get memory count for node
  const getNodeMemoryCount = useCallback((nodeId: string): number => {
    const node = getNodeById(nodeId);
    return node?.memoryIds.length || 0;
  }, [getNodeById]);

  return {
    graphData,
    loading,
    error,
    rebuilding,
    selectedNode,
    refresh,
    rebuild,
    selectNode,
    getNodeById,
    getConnectedNodes,
    getNodeMemoryCount,
  };
}
