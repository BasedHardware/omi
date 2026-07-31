// The Omi orb — React mount for the WebGL2 orb (one component, multiple
// mounts: the bar, the main-window sidebar header, onboarding later). Owns an
// OrbAnimator (self-throttled rAF: 30fps idle / 60fps active / 0fps hidden)
// and wires REAL app signals: state, speech activity (PTT capturing / VAD
// gate), and a live amplitude source sampled while speech is active.
import { useCallback, useEffect, useRef, useState } from 'react'
import { OrbAnimator, type AmplitudeLane } from '../../orb/orbAnimator'
import { ORB_PRESETS, DEFAULT_ORB_PARAMS, type OrbState } from '../../orb/choreography'
import type { WaveformSource } from '../../../../shared/types'
import { useWebglRecovery } from '../../lib/useWebglRecovery'
import { useBarParked } from '../../orb/useBarParked'
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
  /** CSS size in px (square by default). The canvas backing store is
   *  supersampled to size × max(devicePixelRatio, ORB_SUPERSAMPLE), capped at
   *  ORB_MAX_BACKING. */
  size: number
  /** Optional non-square CSS box (px). When given, the orb renders at width×height
   *  — a wide mount shows a longer waveform row. Both default to `size`. The
   *  supersample cap applies to the LARGER dimension, preserving aspect. */
  width?: number
  height?: number
  state: OrbState
  /** Real speech signal (PTT capturing / VAD gate open). Only meaningful with
   *  state 'listening' — 'speaking' implies it. */
  speechActive?: boolean
  /** Live level source, sampled ~30Hz while speech is active. A getter is
   *  resolved per sample — the PTT analyser attaches shortly AFTER recording
   *  flips true, so a snapshotted value would be stale-null. */
  amplitudeSource?: WaveformSource | (() => WaveformSource | null) | null
  /** Which adaptive mapper calibrates the sampled level: 'mic' (default — the
   *  user's capture) or 'playback' (Omi's own audible reply, via the player
   *  tap). Separate mapper instances keep the two families' AGC trackers from
   *  cross-contaminating (a loud reply must not dampen the next mic hold). */
  amplitudeLane?: AmplitudeLane
  /** Bump to replay the genesis spring (materialize from scale 0). */
  genesisNonce?: number
  /** Bump to play the "failed voice turn" gesture (a brief horizontal tremor). */
  failNonce?: number
  /** 0fps hard-off (e.g. the bar window is hidden). */
  visible?: boolean
  preset?: keyof typeof ORB_PRESETS
  className?: string
}

/** Raw voice level for the orb — the canonical linear amplitude 0..1 of full
 *  scale. Prefers the source's fast `getOrbLevel` (already linear: the hub's
 *  pcmPeakLevel or the capture window's time-domain peak). A plain analyser
 *  source falls back to an APPROXIMATE linear level: invert the AnalyserNode
 *  default byte↔dB mapping ([-100,-30] dBFS → [0,255]) on the hottest bin.
 *  Either way the animator's adaptive mapper calibrates + bounds it downstream. */
function sampleAmplitude(source: WaveformSource, scratch: Uint8Array): number {
  const fast = source.getOrbLevel?.()
  if (fast !== undefined) return fast
  source.getByteFrequencyData(scratch)
  let maxByte = 0
  for (let i = 0; i < scratch.length; i++) if (scratch[i] > maxByte) maxByte = scratch[i]
  if (maxByte === 0) return 0
  return Math.pow(10, (-100 + (maxByte / 255) * 70) / 20)
}

export function Orb({
  size,
  width,
  height,
  state,
  speechActive = false,
  amplitudeSource = null,
  amplitudeLane = 'mic',
  genesisNonce = 0,
  failNonce = 0,
  visible = true,
  preset = 'default',
  className
}: OrbProps): React.JSX.Element {
  const cssW = width ?? size
  const cssH = height ?? size
  const hostRef = useRef<HTMLDivElement>(null)
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
  const laneRef = useRef(amplitudeLane)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the sampling interval
  laneRef.current = amplitudeLane

  // Runtime context-loss recovery, via the same shared hook BrainGraph uses.
  // A context lost AFTER a successful build (GPU-process crash / SwiftShader
  // reset — SwiftShader lives in the GPU process even with hardware accel off)
  // fires `webglcontextlost` and leaves this element with a dead context that
  // getContext() can never revive, i.e. a frozen/broken tiny orb. The hook
  // debounces and caps remounts (a GPU crash-loop must not remount the orb
  // unbounded); onContextLost drops to the static mark immediately, on every
  // loss, ahead of the debounced/capped remount itself. The hook's
  // MutationObserver tracks whatever canvas currently lives under hostRef, so
  // it tolerates the canvas being replaced by retryNonce too.
  // Stable identity so it doesn't re-run the hook's effect on every render.
  const handleContextLost = useCallback(() => setReady(false), [])
  const recoveryKey = useWebglRecovery(hostRef, handleContextLost)
  // In the floating bar, main parks the window off-screen to "hide" it without
  // going document.hidden (occlusion tracking is macOS-only), so this is the only
  // honest signal that the orb is invisible — fold it into the 0fps gate below.
  // Always `false` for every non-bar mount. See useBarParked.
  const barParked = useBarParked()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    // Supersample both dimensions by the same factor (preserves aspect), then cap
    // by the LARGER edge so a wide mount never blows past ORB_MAX_BACKING while
    // keeping its aspect intact.
    const scale = Math.max(dpr, ORB_SUPERSAMPLE)
    let backingW = cssW * scale
    let backingH = cssH * scale
    const longEdge = Math.max(backingW, backingH)
    if (longEdge > ORB_MAX_BACKING) {
      const k = ORB_MAX_BACKING / longEdge
      backingW *= k
      backingH *= k
    }
    canvas.width = Math.max(1, Math.round(backingW))
    canvas.height = Math.max(1, Math.round(backingH))
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
  }, [cssW, cssH, preset, retryNonce, recoveryKey])

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
    const apply = (): void =>
      animatorRef.current?.setVisible(visible && !document.hidden && !barParked)
    apply()
    document.addEventListener('visibilitychange', apply)
    return () => document.removeEventListener('visibilitychange', apply)
  }, [visible, barParked, ready])

  useEffect(() => {
    if (genesisNonce > 0) animatorRef.current?.summon()
  }, [genesisNonce, ready])

  useEffect(() => {
    if (failNonce > 0) animatorRef.current?.failGesture()
  }, [failNonce, ready])

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
      if (src) animatorRef.current?.setAmplitude(sampleAmplitude(src, scratch), laneRef.current)
    }, 33)
    return () => clearInterval(timer)
  }, [speechLive])

  // The canvas is always mounted (so retries can reach it) but hidden until the
  // orb is ready; the static mark shows underneath meanwhile. No broken-canvas
  // glyph is ever visible, and the orb fades in the moment WebGL comes up.
  return (
    <div
      ref={hostRef}
      className={className}
      style={{ position: 'relative', width: cssW, height: cssH }}
      aria-hidden
    >
      <canvas
        // Fresh canvas per retry AND per hook-driven recovery. getContext('webgl2')
        // is idempotent per element: once this canvas hands back a context that
        // later becomes lost (the boot GPU handshake, or a GPU-process reset),
        // every subsequent getContext on the SAME element returns that same dead
        // context, so retrying in place can never recover. Keying on both nonces
        // remounts a brand-new canvas on either signal, so each retry/recovery
        // gets a genuinely fresh context off the (now-ready) GPU.
        key={`${retryNonce}:${recoveryKey}`}
        ref={canvasRef}
        style={{
          width: cssW,
          height: cssH,
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
            width: cssW,
            height: cssH,
            objectFit: 'contain'
          }}
        />
      )}
    </div>
  )
}
