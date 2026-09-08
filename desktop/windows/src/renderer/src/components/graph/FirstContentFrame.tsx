import { useEffect, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'

// Fires `onFire` exactly once, on the first render-loop tick where the scene has
// real content to draw (`ready` — nodes populated). Sits inside the Canvas so it
// shares the r3f frame loop. This is what turns "renderer created" (onCreated, too
// early — the node list is still the empty initial state, so GraphNodes draws its
// single origin placeholder = a dot on a blank card) into "content is on screen",
// which is the correct moment for a caller to crossfade away its loading state.
//
// Extracted to its own module so it can be unit-tested in isolation (mock
// @react-three/fiber) — the load-bearing signal of the Memories preview reveal.
export function FirstContentFrame({
  ready,
  onFire
}: {
  ready: boolean
  onFire?: () => void
}): null {
  const invalidate = useThree((s) => s.invalidate)
  const fired = useRef(false)
  // Kick a render the moment content is ready. In frameLoop="demand" nothing
  // repaints on its own after the node list lands, so without this the useFrame
  // below can sit un-called for seconds — the reveal then falls to the bounded
  // fallback, which can uncover a not-yet-painted frame (the blackout). This
  // guarantees the very next frame runs, and GraphNodes' own per-frame invalidate
  // (while the fly-in is moving) keeps it going from there.
  useEffect(() => {
    if (ready && !fired.current) invalidate()
  }, [ready, invalidate])
  useFrame(() => {
    if (!fired.current && ready) {
      fired.current = true
      onFire?.()
    }
  })
  return null
}
