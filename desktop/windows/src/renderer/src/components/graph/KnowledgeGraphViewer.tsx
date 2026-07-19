import { useMemo, useState } from 'react'
import { ArrowLeft, Brain, Loader2, RefreshCw } from 'lucide-react'
import type { KnowledgeGraph } from '../../../../shared/types'
import { BrainGraph } from './LazyBrainGraph'
import { EmptyState } from '../ui/EmptyState'
import { capGraph, isCapped, DEFAULT_NODE_CAP } from '../../lib/graphDisplay'

// Full-screen, INTERACTIVE (orbit/pan/zoom) home for the shared BrainGraph. This
// is a promotion of the small non-interactive "Brain Map" card on the Memories
// tab to a full-bleed scene with camera control, mirroring macOS's
// MemoryGraphPage chrome (floating close + rebuild over the 3D scene). It renders
// the SAME data the inline card shows (see the KnowledgeGraph page — it sources
// the graph from the same useMemoryGraph path), just interactive and full-bleed.
//
// Density control: a real account's graph is large (measured: ~188 nodes / ~474
// edges, one 226-degree hub, ~40% degree-1 leaves) — drawn whole it is an
// unreadable, laggy hairball. By default we show the DEFAULT_NODE_CAP most
// connected nodes (edges pruned to that set) so the scene is legible and fast;
// "Show all" renders the complete graph on demand, so no data is ever silently
// hidden. Label declutter (only the top hubs + hovered/selected nodes are named)
// is handled inside BrainGraph.
//
// Presentational on purpose: all data/nav come in as props so this renders under
// jsdom (the BrainGraph WebGL canvas is mocked in the test) for the populated and
// empty-graph paths.
export function KnowledgeGraphViewer(props: {
  graph: KnowledgeGraph
  centerNodeId?: string
  onClose: () => void
  rebuild?: () => void
  rebuilding?: boolean
}): React.JSX.Element {
  const { graph, centerNodeId, onClose, rebuild, rebuilding } = props
  const hasGraph = graph.nodes.length > 0
  const [showAll, setShowAll] = useState(false)

  // The full graph stays reachable: showAll lifts the cap entirely (capGraph
  // returns the same graph ref, so the sim re-lays out the complete set). When
  // capped we feed only the top-N; edges are pruned to the visible nodes.
  const cap = showAll ? Infinity : DEFAULT_NODE_CAP
  const visibleGraph = useMemo(() => capGraph(graph, cap, centerNodeId), [graph, cap, centerNodeId])
  const capsBite = isCapped(graph, DEFAULT_NODE_CAP)

  return (
    // BrainGraph's root is `absolute inset-0`, so the host must be positioned.
    // Flat dark fill (no .glass backdrop-filter) — layering a WebGL canvas over a
    // blurred surface pins the GPU re-blending on every unrelated repaint (same
    // reason the Memories card uses a solid tint).
    <div className="relative h-full w-full overflow-hidden bg-black/40">
      {hasGraph ? (
        <BrainGraph
          interactive
          graph={visibleGraph}
          centerNodeId={centerNodeId}
          // demand + GraphPulseThrottle caps the render rate (~30fps idle / ~60fps
          // while orbiting or hovering) instead of the display refresh rate. On a
          // 240Hz monitor 'always' rendered a gentle pulse 240x/sec for no benefit;
          // the pulse choreography is unchanged, just capped. See GraphPulseThrottle.
          frameLoop="demand"
          labelMode="declutter"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <EmptyState
            icon={Brain}
            title="Your brain map is empty"
            description="The map appears once you have enough linked memories. Keep talking to Omi — or rebuild to re-derive it from your latest memories."
            action={
              rebuild && (
                <button
                  onClick={rebuild}
                  disabled={rebuilding}
                  className="btn-primary px-4 py-2 disabled:opacity-40"
                >
                  {rebuilding ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  Rebuild
                </button>
              )
            }
          />
        </div>
      )}

      {/* Floating controls over the scene (macOS MemoryGraphPage parity). Sit
          above the canvas and stay clickable even while OrbitControls owns the
          rest of the pointer surface. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between p-4">
        <div className="pointer-events-auto flex items-center gap-2">
          <button
            onClick={onClose}
            className="btn-ghost p-2"
            title="Back to Memories"
            aria-label="Back"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <span className="font-display text-lg font-bold tracking-tight text-white">
            Brain Map
          </span>
        </div>
        <div className="pointer-events-auto flex items-center gap-2">
          {hasGraph && capsBite && (
            <button
              onClick={() => setShowAll((v) => !v)}
              className="btn-ghost px-3 py-2"
              title={
                showAll
                  ? 'Show only the most connected nodes'
                  : 'Render every node in your brain map'
              }
              aria-pressed={showAll}
            >
              {showAll ? `Show key ${DEFAULT_NODE_CAP}` : `Show all ${graph.nodes.length}`}
            </button>
          )}
          {rebuild && hasGraph && (
            <button
              onClick={rebuild}
              disabled={rebuilding}
              className="btn-ghost px-3 py-2 disabled:opacity-40"
              title="Rebuild the brain map from your latest memories"
            >
              {rebuilding ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Rebuild
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
