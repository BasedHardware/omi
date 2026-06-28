import { lazy, Suspense } from 'react'
import type { BrainGraphProps } from './BrainGraph'
import { ErrorBoundary } from '../ui/ErrorBoundary'

// Lazy wrapper so the heavy 3D stack (three + @react-three/fiber + drei +
// d3-force-3d, ~1MB) is code-split out of the initial renderer bundle and only
// downloaded/evaluated when a brain map actually mounts (Memories / Onboarding).
// This shrinks window:created→renderer:eval, the dominant startup phase.
const BrainGraphImpl = lazy(() =>
  import('./BrainGraph').then((m) => ({ default: m.BrainGraph }))
)

// The 3D brain map is the only WebGL surface in the app, so it's the first thing
// to fail if the GPU process is unhealthy (e.g. a contended/locked Chromium GPU
// cache when two instances share a profile) or if its code-split chunk fails to
// load. Contain that here so a failure degrades to a blank pane instead of
// crashing the whole screen (onboarding has no other error boundary above it).
export function BrainGraph(props: BrainGraphProps): React.JSX.Element {
  return (
    <ErrorBoundary label="BrainGraph" fallback={<div className="h-full w-full" aria-hidden />}>
      <Suspense fallback={<div className="h-full w-full" aria-hidden />}>
        <BrainGraphImpl {...props} />
      </Suspense>
    </ErrorBoundary>
  )
}
