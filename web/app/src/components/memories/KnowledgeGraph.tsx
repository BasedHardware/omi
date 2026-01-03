'use client';

import { useRef, useCallback, useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { motion, AnimatePresence } from 'framer-motion';
import { RefreshCw, Loader2, Network, X, ExternalLink, RotateCcw, Tag, ZoomIn, ZoomOut, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useKnowledgeGraph, NODE_COLORS, type GraphNode } from '@/hooks/useKnowledgeGraph';
import type { KnowledgeGraphNodeType } from '@/types/conversation';
import SpriteText from 'three-spritetext';

// Dynamically import ForceGraph3D to avoid SSR issues
// Using react-force-graph-3d (standalone package) instead of react-force-graph
// to avoid A-Frame VR dependency issues
const ForceGraph3D = dynamic(() => import('react-force-graph-3d'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full">
      <Loader2 className="w-8 h-8 text-purple-primary animate-spin" />
    </div>
  ),
});

// Sphere boundary radius - all nodes will be contained within this
const SPHERE_RADIUS = 200;
const INITIAL_CAMERA_DISTANCE = 400;

interface KnowledgeGraphProps {
  onNodeSelect?: (nodeId: string, memoryIds: string[]) => void;
}

export function KnowledgeGraph({ onNodeSelect }: KnowledgeGraphProps) {
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Set<string>>(new Set());

  const {
    graphData,
    loading,
    error,
    rebuilding,
    selectedNode,
    rebuild,
    selectNode,
    getConnectedNodes,
  } = useKnowledgeGraph();

  // Update dimensions on resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  // Apply sphere containment force after graph initializes
  useEffect(() => {
    if (graphRef.current) {
      // Add a custom force to keep nodes within a sphere
      graphRef.current.d3Force('center', null); // Remove default center force

      // Add radial containment force
      graphRef.current.d3Force('bound', () => {
        if (!graphRef.current) return;
        const nodes = graphRef.current.graphData()?.nodes || [];
        nodes.forEach((node: any) => {
          const dist = Math.sqrt((node.x || 0) ** 2 + (node.y || 0) ** 2 + (node.z || 0) ** 2);
          if (dist > SPHERE_RADIUS) {
            const scale = SPHERE_RADIUS / dist;
            node.x = (node.x || 0) * scale;
            node.y = (node.y || 0) * scale;
            node.z = (node.z || 0) * scale;
          }
        });
      });

      // Increase charge (repulsion) to spread nodes more evenly
      graphRef.current.d3Force('charge')?.strength(-120);

      // Add stronger link distance
      graphRef.current.d3Force('link')?.distance(30);
    }
  }, [graphData]);

  // Reset camera to initial position
  const resetView = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.cameraPosition(
        { x: 0, y: 0, z: INITIAL_CAMERA_DISTANCE },
        { x: 0, y: 0, z: 0 },
        1000
      );
      selectNode(null);
      setSearchQuery('');
      setSearchResults(new Set());
    }
  }, [selectNode]);

  // Zoom in
  const zoomIn = useCallback(() => {
    if (graphRef.current) {
      const currentPos = graphRef.current.cameraPosition();
      const newZ = Math.max(currentPos.z * 0.7, 50); // Zoom in by 30%, min 50
      graphRef.current.cameraPosition(
        { x: currentPos.x * 0.7, y: currentPos.y * 0.7, z: newZ },
        { x: 0, y: 0, z: 0 },
        500
      );
    }
  }, []);

  // Zoom out
  const zoomOut = useCallback(() => {
    if (graphRef.current) {
      const currentPos = graphRef.current.cameraPosition();
      const newZ = Math.min(currentPos.z * 1.4, 800); // Zoom out by 40%, max 800
      graphRef.current.cameraPosition(
        { x: currentPos.x * 1.4, y: currentPos.y * 1.4, z: newZ },
        { x: 0, y: 0, z: 0 },
        500
      );
    }
  }, []);

  // Search for nodes
  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query);

    if (!query.trim() || !graphData) {
      setSearchResults(new Set());
      return;
    }

    const lowerQuery = query.toLowerCase();
    const matchingNodeIds = new Set<string>();

    // Find nodes that match the search query
    graphData.nodes.forEach((node) => {
      if (
        node.label.toLowerCase().includes(lowerQuery) ||
        node.aliases.some((alias) => alias.toLowerCase().includes(lowerQuery))
      ) {
        matchingNodeIds.add(node.id);
        // Also add connected nodes
        const connected = getConnectedNodes(node.id);
        connected.forEach((n) => matchingNodeIds.add(n.id));
      }
    });

    setSearchResults(matchingNodeIds);

    // If there's exactly one matching node (not counting connections), focus on it
    const directMatches = graphData.nodes.filter(
      (node) =>
        node.label.toLowerCase().includes(lowerQuery) ||
        node.aliases.some((alias) => alias.toLowerCase().includes(lowerQuery))
    );

    if (directMatches.length === 1 && graphRef.current) {
      const node = directMatches[0];
      const nodePos = { x: node.x || 0, y: node.y || 0, z: node.z || 0 };
      const distance = 100;
      const distFromOrigin = Math.hypot(nodePos.x, nodePos.y, nodePos.z) || 1;
      const distRatio = 1 + distance / distFromOrigin;
      graphRef.current.cameraPosition(
        {
          x: nodePos.x * distRatio,
          y: nodePos.y * distRatio,
          z: nodePos.z * distRatio,
        },
        nodePos,
        1000
      );
    }
  }, [graphData, getConnectedNodes]);

  // Handle node click
  const handleNodeClick = useCallback((node: GraphNode) => {
    selectNode(node);
    onNodeSelect?.(node.id, node.memoryIds);

    // Focus on node with animation - zoom in closer
    if (graphRef.current) {
      const distance = 80;
      const nodePos = { x: node.x || 0, y: node.y || 0, z: node.z || 0 };
      const distFromOrigin = Math.hypot(nodePos.x, nodePos.y, nodePos.z) || 1;
      const distRatio = 1 + distance / distFromOrigin;
      graphRef.current.cameraPosition(
        {
          x: nodePos.x * distRatio,
          y: nodePos.y * distRatio,
          z: nodePos.z * distRatio,
        },
        nodePos,
        1000
      );
    }
  }, [selectNode, onNodeSelect]);

  // Get connected node IDs for highlighting
  const connectedNodeIds = useCallback((nodeId: string): Set<string> => {
    const connected = getConnectedNodes(nodeId);
    return new Set([nodeId, ...connected.map(n => n.id)]);
  }, [getConnectedNodes]);

  // Check if a node should show its label
  const shouldShowLabel = useCallback((node: GraphNode): boolean => {
    if (showAllLabels) return true;
    // Show labels for search results
    if (searchResults.size > 0 && searchResults.has(node.id)) return true;
    if (!selectedNode) return false;
    // Show label for selected node and its direct connections
    const connected = connectedNodeIds(selectedNode.id);
    return connected.has(node.id);
  }, [showAllLabels, selectedNode, connectedNodeIds, searchResults]);

  // Custom node rendering with labels
  const nodeThreeObject = useCallback((node: GraphNode) => {
    if (!shouldShowLabel(node)) return undefined;

    const sprite = new SpriteText(node.label);
    sprite.color = '#ffffff';
    sprite.textHeight = 4;
    sprite.backgroundColor = 'rgba(0, 0, 0, 0.6)';
    sprite.padding = 1.5;
    sprite.borderRadius = 2;
    return sprite;
  }, [shouldShowLabel]);

  // Get node color with highlight effect
  const getNodeColor = useCallback((node: GraphNode) => {
    // If searching, highlight search results
    if (searchResults.size > 0) {
      if (searchResults.has(node.id)) {
        return node.color; // Full color for search matches
      }
      return `${node.color}10`; // Very dim for non-matches
    }

    // If a node is selected, highlight it and connections
    if (selectedNode) {
      const connected = connectedNodeIds(selectedNode.id);
      if (connected.has(node.id)) {
        return node.color; // Full color for selected and connected
      }
      // Dim non-connected nodes significantly
      return `${node.color}15`; // ~8% opacity - very dim
    }
    return node.color;
  }, [selectedNode, connectedNodeIds, searchResults]);

  // Get link opacity
  const getLinkOpacity = useCallback((link: any) => {
    if (!selectedNode) return 0.3;

    const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
    const targetId = typeof link.target === 'object' ? link.target.id : link.target;

    if (sourceId === selectedNode.id || targetId === selectedNode.id) {
      return 0.8;
    }
    return 0.1;
  }, [selectedNode]);

  // Empty state
  if (!loading && (!graphData || graphData.nodes.length <= 1)) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <div className="w-20 h-20 rounded-full bg-bg-tertiary flex items-center justify-center mb-4">
          <Network className="w-10 h-10 text-text-quaternary" />
        </div>
        <h3 className="text-lg font-medium text-text-primary mb-2">Knowledge graph is empty</h3>
        <p className="text-sm text-text-tertiary max-w-sm mb-4">
          Add more memories to build your personal knowledge network.
        </p>
        <button
          onClick={rebuild}
          disabled={rebuilding}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg',
            'bg-purple-primary text-white text-sm font-medium',
            'hover:bg-purple-secondary transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        >
          {rebuilding ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          {rebuilding ? 'Rebuilding...' : 'Rebuild Graph'}
        </button>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative w-full h-full bg-bg-primary overflow-hidden">
      {/* Graph */}
      {graphData && (
        <ForceGraph3D
          ref={graphRef}
          graphData={graphData as any}
          width={dimensions.width}
          height={dimensions.height}
          backgroundColor="#0F0F0F"
          nodeLabel={(node: any) => node.label}
          nodeColor={getNodeColor as any}
          nodeVal={(node: any) => node.val}
          nodeOpacity={0.9}
          nodeThreeObject={nodeThreeObject as any}
          nodeThreeObjectExtend={true}
          linkOpacity={getLinkOpacity as any}
          linkWidth={1}
          linkColor={() => '#8B5CF680'}
          onNodeClick={handleNodeClick as any}
          onBackgroundClick={() => selectNode(null)}
          enableNodeDrag={true}
          enableNavigationControls={true}
          showNavInfo={false}
          cooldownTicks={200}
          d3AlphaDecay={0.01}
          d3VelocityDecay={0.2}
        />
      )}

      {/* Search bar - top left */}
      <div className="absolute top-4 left-4 w-64">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-quaternary" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search nodes..."
            className={cn(
              'w-full pl-9 pr-8 py-2 rounded-lg',
              'bg-bg-tertiary/80 backdrop-blur-sm border border-bg-quaternary',
              'text-sm text-text-primary',
              'focus:outline-none focus:ring-2 focus:ring-purple-primary/50',
              'placeholder:text-text-quaternary'
            )}
          />
          {searchQuery && (
            <button
              onClick={() => handleSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-text-quaternary hover:text-text-primary"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
        {searchResults.size > 0 && (
          <p className="mt-1 text-xs text-text-quaternary">
            {searchResults.size} nodes found
          </p>
        )}
      </div>

      {/* Controls - top right */}
      <div className="absolute top-4 right-4 flex items-center gap-2">
        {/* Labels toggle */}
        <button
          onClick={() => setShowAllLabels(!showAllLabels)}
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-lg',
            'backdrop-blur-sm border transition-colors',
            showAllLabels
              ? 'bg-purple-primary/20 border-purple-primary/50 text-purple-primary'
              : 'bg-bg-tertiary/80 border-bg-quaternary text-text-secondary hover:text-text-primary'
          )}
          title={showAllLabels ? 'Hide labels' : 'Show all labels'}
        >
          <Tag className="w-4 h-4" />
          <span className="text-sm">Labels</span>
        </button>

        {/* Reset view */}
        <button
          onClick={resetView}
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-lg',
            'bg-bg-tertiary/80 backdrop-blur-sm border border-bg-quaternary',
            'text-text-secondary hover:text-text-primary',
            'transition-colors'
          )}
          title="Reset view"
        >
          <RotateCcw className="w-4 h-4" />
          <span className="text-sm">Reset</span>
        </button>

        {/* Rebuild */}
        <button
          onClick={rebuild}
          disabled={rebuilding}
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-lg',
            'bg-bg-tertiary/80 backdrop-blur-sm border border-bg-quaternary',
            'text-text-secondary hover:text-text-primary',
            'transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
          title="Rebuild knowledge graph"
        >
          {rebuilding ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          <span className="text-sm">Rebuild</span>
        </button>
      </div>

      {/* Zoom controls - right side */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 flex flex-col gap-2">
        <button
          onClick={zoomIn}
          className={cn(
            'p-2 rounded-lg',
            'bg-bg-tertiary/80 backdrop-blur-sm border border-bg-quaternary',
            'text-text-secondary hover:text-text-primary',
            'transition-colors'
          )}
          title="Zoom in"
        >
          <ZoomIn className="w-5 h-5" />
        </button>
        <button
          onClick={zoomOut}
          className={cn(
            'p-2 rounded-lg',
            'bg-bg-tertiary/80 backdrop-blur-sm border border-bg-quaternary',
            'text-text-secondary hover:text-text-primary',
            'transition-colors'
          )}
          title="Zoom out"
        >
          <ZoomOut className="w-5 h-5" />
        </button>
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 p-3 rounded-lg bg-bg-tertiary/80 backdrop-blur-sm border border-bg-quaternary">
        <p className="text-xs text-text-quaternary mb-2">Node Types</p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {(Object.entries(NODE_COLORS) as [KnowledgeGraphNodeType | 'user', string][]).map(([type, color]) => (
            <div key={type} className="flex items-center gap-2">
              <div
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span className="text-xs text-text-tertiary capitalize">
                {type === 'user' ? 'You' : type}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Controls hint */}
      <div className="absolute bottom-4 right-4 text-xs text-text-quaternary">
        Drag to rotate • Scroll to zoom • Click node to select
      </div>

      {/* Selected node panel */}
      <AnimatePresence>
        {selectedNode && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className={cn(
              'absolute bottom-20 left-4 right-4 max-w-md',
              'p-4 rounded-xl',
              'bg-bg-tertiary/90 backdrop-blur-md border border-bg-quaternary',
              'shadow-strong'
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div
                  className="w-4 h-4 rounded-full flex-shrink-0"
                  style={{ backgroundColor: selectedNode.color }}
                />
                <div>
                  <h4 className="font-medium text-text-primary">{selectedNode.label}</h4>
                  <p className="text-xs text-text-quaternary capitalize">{selectedNode.nodeType}</p>
                </div>
              </div>
              <button
                onClick={() => selectNode(null)}
                className="p-1 rounded-md text-text-tertiary hover:text-text-primary hover:bg-bg-quaternary transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {selectedNode.aliases.length > 0 && (
              <div className="mt-2">
                <p className="text-xs text-text-quaternary mb-1">Also known as:</p>
                <div className="flex flex-wrap gap-1">
                  {selectedNode.aliases.map((alias, i) => (
                    <span
                      key={i}
                      className="px-2 py-0.5 rounded text-xs bg-bg-quaternary text-text-tertiary"
                    >
                      {alias}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between mt-3 pt-3 border-t border-bg-quaternary">
              <span className="text-sm text-text-tertiary">
                {selectedNode.memoryIds.length} related memories
              </span>
              {selectedNode.memoryIds.length > 0 && onNodeSelect && (
                <button
                  onClick={() => onNodeSelect(selectedNode.id, selectedNode.memoryIds)}
                  className={cn(
                    'flex items-center gap-1 px-2 py-1 rounded-md text-xs',
                    'text-purple-primary hover:bg-purple-primary/10',
                    'transition-colors'
                  )}
                >
                  View Memories
                  <ExternalLink className="w-3 h-3" />
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Loading overlay */}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-bg-primary/80">
          <Loader2 className="w-8 h-8 text-purple-primary animate-spin" />
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="absolute top-4 left-4 right-4 p-3 rounded-lg bg-error/10 border border-error/30 text-error text-sm">
          {error}
        </div>
      )}
    </div>
  );
}
