import { lazy, Suspense } from 'react'
import type { BrainGraphProps } from './BrainGraph'
import { ErrorBoundary } from '../ui/ErrorBoundary'
import { BrainGraphFallback } from './BrainGraphFallback'

// Lazy wrapper so the heavy 3D stack (three + @react-three/fiber + drei +
// d3-force-3d, ~1MB) is code-split out of the initial renderer bundle and only
// downloaded/evaluated when a brain map actually mounts (Memories / Onboarding).
// This shrinks window:created→renderer:eval, the dominant startup phase.
const BrainGraphImpl = lazy(() => import('./BrainGraph').then((m) => ({ default: m.BrainGraph })))

// This boundary now only guards the LAZY LOAD itself (a code-split chunk that
// fails to download / evaluate). The WebGL failure modes are all handled inside
// BrainGraph: a lost context by useWebglRecovery (remounts its canvas subtree), an
// unavailable context and a throwing three.js renderer by its own probe + inner
// ErrorBoundary → BrainGraphFallback. That coverage applies to this lazy path and
// to Onboarding's direct mount alike. A failed chunk degrades to the same static
// mark rather than a blank pane, so the screen never shows an empty black hole.
export function BrainGraph(props: BrainGraphProps): React.JSX.Element {
  return (
    <ErrorBoundary label="LazyBrainGraph" fallback={<BrainGraphFallback />}>
      <Suspense fallback={<div className="h-full w-full" aria-hidden />}>
        <BrainGraphImpl {...props} />
      </Suspense>
    </ErrorBoundary>
  )
}
