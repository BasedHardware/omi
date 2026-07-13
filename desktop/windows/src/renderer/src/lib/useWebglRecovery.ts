import { useEffect, useState } from 'react'

// Chromium paints a <canvas> whose WebGL context is LOST-and-not-restored as its
// broken-image placeholder — the white rounded box with the small sad-face glyph
// (the exact "why is there a broken image on the Memories page" symptom). Two
// distinct triggers produce that lost context in this app, and neither is caught
// by the main process' render-process-gone auto-reload (the renderer stays alive
// in both):
//
//   1. GPU-process crash. SwiftShader (dev's forced-software GL) runs INSIDE the
//      GPU process, so even with hardware acceleration off the GPU process can
//      still crash (see crash.log: `child-process-gone type=GPU`). Chromium keeps
//      the renderer, restarts the GPU process, and fires `webglcontextlost` on
//      every live canvas. render-process-gone never fires → nothing reloads.
//   2. SwiftShader context loss under rapid canvas mount/unmount churn (see the
//      pauseWhenHidden note in BrainGraph.tsx). Fires `webglcontextlost` too.
//
// react-three-fiber (v9) does NOT rebuild its renderer when a context is later
// restored, and getContext() on the same <canvas> element keeps returning the
// dead context forever (the same reason Orb.tsx remounts a fresh canvas to
// recover). So the durable fix is to REMOUNT the canvas subtree on context loss,
// which creates a brand-new canvas + fresh context off the recovered GPU.
//
// Remounts are debounced and capped: recovery must not itself become the rapid
// churn that loses the context again (a remount storm while the GPU is still
// down). After the cap we stop and leave the host's own fallback rather than
// thrash — self-limiting, and it resets once losses stop for the window.
//
// Returns a key to spread onto the canvas-owning subtree (`<X key={key} />`); a
// bump forces the remount. Pass the ref of an element that CONTAINS the canvas
// (the canvas may mount/remount asynchronously; we track it via MutationObserver).
const RECOVER_DEBOUNCE_MS = 600
const RECOVER_MAX = 4
const RECOVER_WINDOW_MS = 60_000

export function useWebglRecovery(
  hostRef: React.RefObject<HTMLElement | null>,
  onContextLost?: () => void
): number {
  const [recoveryKey, setRecoveryKey] = useState(0)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const firedAt: number[] = []
    let timer: ReturnType<typeof setTimeout> | undefined

    const scheduleRemount = (): void => {
      // Coalesce a burst (a GPU crash fires lost on every canvas at once) into a
      // single remount.
      if (timer) return
      const now = Date.now()
      const recent = firedAt.filter((t) => now - t < RECOVER_WINDOW_MS)
      firedAt.length = 0
      firedAt.push(...recent)
      if (recent.length >= RECOVER_MAX) {
        console.warn(
          '[webgl-recovery] context lost repeatedly — leaving fallback instead of remounting again'
        )
        return
      }
      timer = setTimeout(() => {
        timer = undefined
        firedAt.push(Date.now())
        setRecoveryKey((k) => k + 1)
      }, RECOVER_DEBOUNCE_MS)
    }

    const onLost = (e: Event): void => {
      // preventDefault keeps the canvas element alive (Chromium won't fully tear
      // it down), so the remount can bind a fresh context to a fresh canvas.
      e.preventDefault()
      // Hide the now-broken canvas IMMEDIATELY so Chromium's broken-image
      // placeholder never shows — not during the anti-storm debounce below, and
      // not at all if we hit the remount cap (the host's own dark background
      // stands in instead, matching the Orb's "hidden canvas, never a broken
      // glyph" fallback). The remount replaces this element with a fresh one.
      if (e.target instanceof HTMLElement) e.target.style.visibility = 'hidden'
      onContextLost?.()
      scheduleRemount()
    }

    // The canvas mounts asynchronously (React.lazy + Suspense) and is replaced on
    // every recovery remount, so bind to whatever canvas currently lives under
    // the host and rebind when the subtree changes.
    let bound: HTMLCanvasElement | null = null
    const bind = (): void => {
      const canvas = host.querySelector('canvas')
      if (canvas === bound) return
      bound?.removeEventListener('webglcontextlost', onLost)
      bound = canvas
      bound?.addEventListener('webglcontextlost', onLost)
    }
    bind()
    const mo = new MutationObserver(bind)
    mo.observe(host, { childList: true, subtree: true })

    // Belt-and-suspenders: a GPU-process crash also broadcasts from main, so we
    // recover even if the per-canvas event is missed (or the canvas was between
    // mounts when the GPU died). Optional-chained: absent on older preload/HMR
    // and in jsdom tests.
    const offGpu = window.omi?.onGpuContextLost?.(scheduleRemount)

    return () => {
      mo.disconnect()
      bound?.removeEventListener('webglcontextlost', onLost)
      if (timer) clearTimeout(timer)
      offGpu?.()
    }
  }, [hostRef, onContextLost])

  return recoveryKey
}
