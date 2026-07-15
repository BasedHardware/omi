import { ArrowLeft, Brain, Loader2, RefreshCw } from 'lucide-react'
import type { KnowledgeGraph } from '../../../../shared/types'
import { BrainGraph } from './LazyBrainGraph'
import { EmptyState } from '../ui/EmptyState'

// Full-screen, INTERACTIVE (orbit/pan/zoom) home for the shared BrainGraph. This
// is a promotion of the small non-interactive "Brain Map" card on the Memories
// tab to a full-bleed scene with camera control, mirroring macOS's
// MemoryGraphPage chrome (floating close + rebuild over the 3D scene). It renders
// the SAME data the inline card shows (see the KnowledgeGraph page — it sources
// the graph from the same useMemoryGraph path), just interactive and full-bleed.
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

  return (
    // BrainGraph's root is `absolute inset-0`, so the host must be positioned.
    // Flat dark fill (no .glass backdrop-filter) — layering a WebGL canvas over a
    // blurred surface pins the GPU re-blending on every unrelated repaint (same
    // reason the Memories card uses a solid tint).
    <div className="relative h-full w-full overflow-hidden bg-black/40">
      {hasGraph ? (
        <BrainGraph interactive graph={graph} centerNodeId={centerNodeId} frameLoop="always" />
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
        {rebuild && hasGraph && (
          <button
            onClick={rebuild}
            disabled={rebuilding}
            className="pointer-events-auto btn-ghost px-3 py-2 disabled:opacity-40"
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
  )
}
