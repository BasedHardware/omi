// Renderer for the halo window (route #/glow). It draws ONE rounded ring whose
// geometry (pad, radius) AND appearance (hues, intensity) main hands it — this
// component never guesses geometry, never sizes or moves its own window, and knows
// nothing about why the halo is being drawn. See glow.css for the three rules that
// make it a glow and not a border.
import { useEffect, useState } from 'react'
import type { GlowShowPayload } from '../../../../shared/types'
import './glow.css'

export function GlowWindow(): React.JSX.Element | null {
  const [run, setRun] = useState<GlowShowPayload | null>(null)

  useEffect(() => {
    document.body.classList.add('glow-body')
    return () => document.body.classList.remove('glow-body')
  }, [])

  useEffect(() => {
    return window.omiGlow.onShow((p) => {
      setRun(p)
      // Paint-ack handshake (same contract as the bar): main keeps the window
      // parked off-screen until we confirm the ring's frame is composited —
      // otherwise the compositor would show the PREVIOUS run's frame at the new
      // position for a beat. Double-rAF is Chromium's "the new state has been
      // committed to a frame" proxy: rAF #1 runs after React's commit but before
      // the paint, rAF #2 after it.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => window.omiGlow.showAck(p.token))
      })
    })
  }, [])

  useEffect(() => window.omiGlow.onHide(() => setRun(null)), [])

  // Tell main we can paint (flushes a show that arrived before we mounted).
  useEffect(() => window.omiGlow.ready(), [])

  if (!run) return null

  const [h1, h2, h3] = run.paint.hues

  return (
    // key={runId}: a fresh run REMOUNTS, restarting the envelope + drift from
    // zero. Without it a superseding glow would inherit a half-played (possibly
    // already fading) animation.
    <div
      key={run.runId}
      className="halo-run"
      style={
        {
          '--pad': `${run.pad}px`,
          '--overlap': `${run.overlap}px`,
          '--radius': `${run.radius}px`,
          '--peak': run.paint.intensity
        } as React.CSSProperties
      }
    >
      {/* The three rings share one shadow stack (glow.css) and differ ONLY in hue,
          so every preset is automatically the same faintness — a new colour can
          never accidentally arrive brighter than the approved one. */}
      <div className="halo-ring h1" style={{ '--c': h1 } as React.CSSProperties} />
      <div className="halo-ring h2" style={{ '--c': h2 } as React.CSSProperties} />
      <div className="halo-ring h3" style={{ '--c': h3 } as React.CSSProperties} />
    </div>
  )
}
