import { lazy, Suspense, useRef } from 'react'
import type { BrainGraphProps } from './BrainGraph'
import { ErrorBoundary } from '../ui/ErrorBoundary'
import { useWebglRecovery } from '../../lib/useWebglRecovery'

// Lazy wrapper so the heavy 3D stack (three + @react-three/fiber + drei +
// d3-force-3d, ~1MB) is code-split out of the initial renderer bundle and only
// downloaded/evaluated when a brain map actually mounts (Memories / Onboarding).
// This shrinks window:created→renderer:eval, the dominant startup phase.
const BrainGraphImpl = lazy(() => import('./BrainGraph').then((m) => ({ default: m.BrainGraph })))

// The 3D brain map is the only WebGL surface in the app, so it's the first thing
// to fail if the GPU process is unhealthy (e.g. a contended/locked Chromium GPU
// cache when two instances share a profile) or if its code-split chunk fails to
// load. Two layers of containment here:
//   • ErrorBoundary — a throw below (failed lazy chunk, three init error)
//     degrades to a blank pane instead of crashing the whole screen (onboarding
//     has no other boundary above it).
//   • useWebglRecovery — a LOST WebGL context (GPU-process crash or SwiftShader
//     churn) doesn't throw; it leaves the <canvas> painted as Chromium's
//     broken-image placeholder (white box + sad face). The hook remounts the
//     subtree on context loss so a fresh canvas/context replaces the broken one.
//     Keying the ErrorBoundary on the same key also clears a prior chunk-load
//     failure, so recovery retries that too.
export function BrainGraph(props: BrainGraphProps): React.JSX.Element {
  // display:contents wrapper: no layout box of its own (so BrainGraph's
  // `absolute inset-0` still resolves against the real positioned ancestor), but
  // a real DOM node the hook can query the canvas under.
  const hostRef = useRef<HTMLDivElement>(null)
  const recoveryKey = useWebglRecovery(hostRef)
  return (
    <div ref={hostRef} style={{ display: 'contents' }}>
      <ErrorBoundary
        key={recoveryKey}
        label="BrainGraph"
        fallback={<div className="h-full w-full" aria-hidden />}
      >
        <Suspense fallback={<div className="h-full w-full" aria-hidden />}>
          <BrainGraphImpl {...props} />
        </Suspense>
      </ErrorBoundary>
    </div>
  )
}
