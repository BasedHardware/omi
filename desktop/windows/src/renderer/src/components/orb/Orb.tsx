// The Omi orb — React mount for the WebGL2 orb (one component, multiple
// mounts: the bar, the main-window sidebar header, onboarding later). Owns an
// OrbAnimator (self-throttled rAF: 30fps idle / 60fps active / 0fps hidden)
// and wires REAL app signals: state, speech activity (PTT capturing / VAD
// gate), and a live amplitude source sampled while speech is active.
import { useEffect, useRef, useState } from 'react'
import { OrbAnimator } from '../../orb/orbAnimator'
import { ORB_PRESETS, DEFAULT_ORB_PARAMS, type OrbState } from '../../orb/choreography'
import type { WaveformSource } from '../../../../shared/types'
import omiLogo from '../../assets/omi-logo.png'

// WebGL/SwiftShader can be transiently unavailable while the GPU process spins up
// at boot (or across a renderer reload). Retry construction this many times, at
// this interval, before settling on the static-mark fallback — long enough to
// outlast a startup GPU handshake, and self-healing (the canvas stays mounted so
// the orb reveals the moment WebGL becomes ready).
const MAX_ORB_ATTEMPTS = 60
const ORB_RETRY_MS = 700

// Supersample the orb's WebGL drawing buffer to at least this many samples per
// CSS px (the device pixel ratio wins when it is higher). The shader antialiases
// the blob with a fixed ~2px band derived from the field gradient; on a 22–34px
// orb that band is a large fraction of the whole shape and reads as a soft,
// "misty" rim at 1×. Rendering the buffer larger and letting the browser
// downscale it into the CSS box shrinks the band to a sub-pixel fraction, so the
// merged blob's edge stays crisp.
//
// 3.0 is the measured knee: sweeping the factor at the real mount sizes (22/26/
// 34px, dpr 1) the rim's soft-edge fraction drops steeply from 1×→~2.5× then
// plateaus — 3.0 already sits on that plateau, so a higher factor only adds
// render cost (12× the fragments at 3.0) for no visible gain. Verified against
// real bar sizes at dpr 1/1.5; per-frame SwiftShader cost stays a couple ms.
const ORB_SUPERSAMPLE = 3.0
// Ceiling on the drawing-buffer edge (px): past this the AA band is already
// sub-pixel, so it only bounds cost on any large future mount.
const ORB_MAX_BACKING = 256

export type OrbProps = {
  /** CSS size in px. The canvas backing store is supersampled to
   *  size × max(devicePixelRatio, ORB_SUPERSAMPLE), capped at ORB_MAX_BACKING. */
  size: number
  state: OrbState
  /** Real speech signal (PTT capturing / VAD gate open). Only meaningful with
   *  state 'listening' — 'speaking' implies it. */
  speechActive?: boolean
  /** Live level source, sampled ~30Hz while speech is active. A getter is
   *  resolved per sample — the PTT analyser attaches shortly AFTER recording
   *  flips true, so a snapshotted value would be stale-null. */
  amplitudeSource?: WaveformSource | (() => WaveformSource | null) | null
  /** Bump to replay the genesis spring (materialize from scale 0). */
  genesisNonce?: number
  /** 0fps hard-off (e.g. the bar window is hidden). */
  visible?: boolean
  preset?: keyof typeof ORB_PRESETS
  className?: string
}

/** Raw voice level for the orb, ~0..1+. Prefers the source's fast `getOrbLevel`
 *  (a low-smoothing tap that tracks syllables; the bar bins are too smoothed to
 *  wave the blob); falls back to RMS of the frequency bins for a plain analyser.
 *  Either way the choreography envelope + soft-knee bound it downstream. */
function sampleAmplitude(source: WaveformSource, scratch: Uint8Array): number {
  const fast = source.getOrbLevel?.()
  if (fast !== undefined) return fast
  source.getByteFrequencyData(scratch)
  let sum = 0
  for (let i = 0; i < scratch.length; i++) sum += scratch[i] * scratch[i]
  const rms = Math.sqrt(sum / scratch.length) / 255
  return rms * 2.2
}

export function Orb({
  size,
  state,
  speechActive = false,
  amplitudeSource = null,
  genesisNonce = 0,
  visible = true,
  preset = 'default',
  className
}: OrbProps): React.JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animatorRef = useRef<OrbAnimator | null>(null)
  // The orb reveals only once its WebGL animator is built; until then the static
  // omi mark shows under a hidden canvas. Bumping retryNonce re-runs the build
  // effect, so the orb self-heals the instant WebGL becomes ready — no broken
  // canvas, and no permanent fallback for a mere startup race.
  const [ready, setReady] = useState(false)
  const [retryNonce, setRetryNonce] = useState(0)
  const attemptsRef = useRef(0)
  const sourceRef = useRef(amplitudeSource)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the sampling interval
  sourceRef.current = amplitudeSource

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const backing = Math.min(ORB_MAX_BACKING, Math.round(size * Math.max(dpr, ORB_SUPERSAMPLE)))
    canvas.width = backing
    canvas.height = backing
    let animator: OrbAnimator | null = null
    try {
      animator = new OrbAnimator(canvas, ORB_PRESETS[preset] ?? DEFAULT_ORB_PARAMS)
      attemptsRef.current = 0
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-shot fallback→orb swap reflecting the result of building the external WebGL renderer, not derived state
      setReady(true)
    } catch (e) {
      // Drop back to the fallback while we retry — if a prior build had succeeded
      // (props changed → rebuild → the disposed context can't be reused on the
      // same element), leaving `ready` true would show a hidden canvas over a dead
      // context with the static mark suppressed.
      setReady(false)
      // WebGL2 not ready (GPU/SwiftShader still coming up, or a renderer reload).
      // The canvas stays mounted-but-hidden and we keep retrying, so the orb
      // reveals itself the instant WebGL works rather than latching a broken
      // frame. Only settle on the static mark after a generous window.
      attemptsRef.current += 1
      if (attemptsRef.current === 1) console.warn('[orb] WebGL not ready, retrying…', e)
      if (attemptsRef.current < MAX_ORB_ATTEMPTS) {
        const retry = setTimeout(() => setRetryNonce((n) => n + 1), ORB_RETRY_MS)
        return () => clearTimeout(retry)
      }
      console.warn('[orb] WebGL unavailable after retries — showing static mark')
      return
    }
    animatorRef.current = animator
    return () => {
      animatorRef.current = null
      animator?.dispose()
    }
  }, [size, preset, retryNonce])

  // `ready` is in each dep list so that when a RETRY finally builds a fresh
  // animator (ready flips false→true), the app's current state / visibility /
  // pending genesis are re-applied to it — otherwise the rebuilt animator would
  // keep its constructor defaults (idle, visible, already looping) forever.
  useEffect(() => {
    animatorRef.current?.setState(state)
    // setState resets the speech gate; re-assert the live signal after.
    if (state === 'listening') animatorRef.current?.setSpeechActive(speechActive)
  }, [state, speechActive, ready])

  useEffect(() => {
    animatorRef.current?.setVisible(visible && !document.hidden)
    const onVis = (): void => animatorRef.current?.setVisible(visible && !document.hidden)
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [visible, ready])

  useEffect(() => {
    if (genesisNonce > 0) animatorRef.current?.summon()
  }, [genesisNonce, ready])

  // Live amplitude: sample the source ~30Hz while speech is active.
  const speechLive = speechActive || state === 'speaking'
  useEffect(() => {
    if (!speechLive) {
      animatorRef.current?.setAmplitude(0)
      return
    }
    const scratch = new Uint8Array(64)
    const timer = setInterval(() => {
      const raw = sourceRef.current
      const src = typeof raw === 'function' ? raw() : raw
      if (src) animatorRef.current?.setAmplitude(sampleAmplitude(src, scratch))
    }, 33)
    return () => clearInterval(timer)
  }, [speechLive])

  // The canvas is always mounted (so retries can reach it) but hidden until the
  // orb is ready; the static mark shows underneath meanwhile. No broken-canvas
  // glyph is ever visible, and the orb fades in the moment WebGL comes up.
  return (
    <div
      className={className}
      style={{ position: 'relative', width: size, height: size }}
      aria-hidden
    >
      <canvas
        // Fresh canvas per retry. getContext('webgl2') is idempotent per element:
        // once this canvas hands back a context that later becomes lost (the boot
        // GPU handshake, or a GPU-process reset), every subsequent getContext on
        // the SAME element returns that same dead context, so retrying in place
        // can never recover. Keying on retryNonce remounts a brand-new canvas, so
        // each retry gets a genuinely fresh context off the (now-ready) GPU.
        key={retryNonce}
        ref={canvasRef}
        style={{
          width: size,
          height: size,
          display: 'block',
          opacity: ready ? 1 : 0,
          transition: 'opacity 200ms ease'
        }}
        aria-hidden
      />
      {!ready && (
        <img
          src={omiLogo}
          alt=""
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            width: size,
            height: size,
            objectFit: 'contain'
          }}
        />
      )}
    </div>
  )
}
