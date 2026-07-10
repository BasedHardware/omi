// The Omi orb — React mount for the WebGL2 orb (one component, multiple
// mounts: the bar, the main-window sidebar header, onboarding later). Owns an
// OrbAnimator (self-throttled rAF: 30fps idle / 60fps active / 0fps hidden)
// and wires REAL app signals: state, speech activity (PTT capturing / VAD
// gate), and a live amplitude source sampled while speech is active.
import { useEffect, useRef } from 'react'
import { OrbAnimator } from '../../orb/orbAnimator'
import { ORB_PRESETS, DEFAULT_ORB_PARAMS, type OrbState } from '../../orb/choreography'
import type { WaveformSource } from '../../../../shared/types'

export type OrbProps = {
  /** CSS size in px (the canvas backing store is size × devicePixelRatio). */
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

/** RMS of a WaveformSource's byte-frequency snapshot, normalized to ~0..1. */
function sampleAmplitude(source: WaveformSource, scratch: Uint8Array): number {
  source.getByteFrequencyData(scratch)
  let sum = 0
  for (let i = 0; i < scratch.length; i++) sum += scratch[i] * scratch[i]
  const rms = Math.sqrt(sum / scratch.length) / 255
  // Frequency-bin RMS of speech tends to sit low; lift into a usable range
  // (the choreography soft-knee bounds it regardless).
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
  const sourceRef = useRef(amplitudeSource)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the sampling interval
  sourceRef.current = amplitudeSource

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.round(size * dpr)
    canvas.height = Math.round(size * dpr)
    let animator: OrbAnimator | null = null
    try {
      animator = new OrbAnimator(canvas, ORB_PRESETS[preset] ?? DEFAULT_ORB_PARAMS)
    } catch (e) {
      // WebGL2 unavailable (ancient GPU/driver): leave the canvas empty rather
      // than crash the window — the orb is brand motion, not functionality.
      console.warn('[orb] renderer unavailable:', e)
      return
    }
    animatorRef.current = animator
    return () => {
      animatorRef.current = null
      animator?.dispose()
    }
  }, [size, preset])

  useEffect(() => {
    animatorRef.current?.setState(state)
    // setState resets the speech gate; re-assert the live signal after.
    if (state === 'listening') animatorRef.current?.setSpeechActive(speechActive)
  }, [state, speechActive])

  useEffect(() => {
    animatorRef.current?.setVisible(visible && !document.hidden)
    const onVis = (): void => animatorRef.current?.setVisible(visible && !document.hidden)
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [visible])

  useEffect(() => {
    if (genesisNonce > 0) animatorRef.current?.summon()
  }, [genesisNonce])

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

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: size, height: size, display: 'block' }}
      aria-hidden
    />
  )
}
