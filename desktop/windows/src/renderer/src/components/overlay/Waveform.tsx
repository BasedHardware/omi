import { useEffect, useRef } from 'react'

const BAR_COUNT = 24
const MIN_SCALE = 0.06 // resting height so idle bars still read as a waveform
// Adaptive noise gate, like a videoconference mic meter. Instead of a fixed
// threshold (which can't know how loud a given laptop's fans are), we LEARN the
// ambient floor: it rises slowly toward steady noise and falls quickly when the
// room quiets. Only energy MARGIN above that learned floor counts as speech —
// steady fans/hum get absorbed into the floor and leave the bars flat.
const MARGIN = 0.09 // level above the learned floor required to activate — low
// enough that normal/quiet speech moves the bars, still above steady fan/room hum
// Amplifies the above-floor portion so speech fills the bars. Tuned so NORMAL
// speaking lands in the dynamic (non-clipped) range — at the old 4.2 (and even
// 2.2) normal speech saturated every bar to max (looked static), leaving only a
// whisper with any visible movement. Lower = the lively range sits at
// louder/normal volume.
const GAIN = 1.4
const FLOOR_RISE = 0.03 // learn steady noise reasonably fast (without chasing speech)
const FLOOR_FALL = 0.1 // faster: re-learn quickly when the room quiets
const SMOOTH = 0.18 // per-bar easing toward target (lower = smoother/less reactive)

/**
 * Live mic-amplitude waveform. Reads the frequency data straight off the analyser
 * (owned by usePushToTalk) on every animation frame and writes bar heights via
 * `style.transform` — no React state per frame, so it stays at 60fps without
 * re-rendering the overlay. Shows resting bars when the analyser is absent (mic
 * blocked / connecting).
 */
export function Waveform({
  analyserRef
}: {
  analyserRef: React.MutableRefObject<AnalyserNode | null>
}): React.JSX.Element {
  const barsRef = useRef<Array<HTMLDivElement | null>>([])
  // Learned ambient noise floor (0..1) and whether it's been seeded yet.
  const floorRef = useRef(0)
  const seededRef = useRef(false)
  // Current displayed scale per bar, eased toward the target each frame for smoothness.
  const scalesRef = useRef<number[]>([])

  useEffect(() => {
    let raf = 0
    const data = new Uint8Array(BAR_COUNT)
    const center = (BAR_COUNT - 1) / 2
    const tick = (): void => {
      const analyser = analyserRef.current
      const bars = barsRef.current
      if (analyser) {
        analyser.getByteFrequencyData(data)
        // Overall level = average across the low bins (robust to a single noisy bin).
        let sum = 0
        for (let i = 0; i < bars.length; i++) sum += data[Math.round(Math.abs(i - center))] / 255
        const level = sum / bars.length

        // Decide speech vs. ambient using the CURRENT floor (before this frame's
        // update), so the floor we test against isn't already nudged by this frame.
        const active = level - floorRef.current >= MARGIN

        // Track the ambient floor: seed on the first frame, then learn ONLY while
        // NOT speaking. Freezing the floor during speech is what stops sustained
        // normal-volume talk from being absorbed into the floor (which collapsed
        // the bars mid-sentence and made quiet feel more responsive than normal).
        // When quiet it rises slowly toward steady noise and falls fast when the
        // room quiets.
        if (!seededRef.current) {
          floorRef.current = level
          seededRef.current = true
        } else if (!active) {
          const a = level > floorRef.current ? FLOOR_RISE : FLOOR_FALL
          floorRef.current = floorRef.current * (1 - a) + level * a
        }
        const floor = floorRef.current

        for (let i = 0; i < bars.length; i++) {
          let target = MIN_SCALE
          if (active) {
            // Mirror around the center so the waveform is symmetric: each bar reads
            // the frequency bin at its distance from the middle, putting the louder
            // low bins in the center and tapering symmetrically toward both edges.
            const bin = Math.round(Math.abs(i - center))
            const v = Math.min(1, Math.max(0, data[bin] / 255 - floor) * GAIN)
            target = MIN_SCALE + v * (1 - MIN_SCALE)
          }
          // Ease toward the target so speech ramps in/out instead of snapping.
          const prev = scalesRef.current[i] ?? MIN_SCALE
          const next = prev + (target - prev) * SMOOTH
          scalesRef.current[i] = next
          const bar = bars[i]
          if (bar) bar.style.transform = `scaleY(${next})`
        }
      } else {
        // Reset so the floor re-learns from scratch on the next capture.
        seededRef.current = false
        floorRef.current = 0
        for (let i = 0; i < bars.length; i++) {
          scalesRef.current[i] = MIN_SCALE
          const bar = bars[i]
          if (bar) bar.style.transform = `scaleY(${MIN_SCALE})`
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [analyserRef])

  return (
    <div className="flex h-7 flex-1 items-center justify-center gap-[3px]">
      {Array.from({ length: BAR_COUNT }).map((_, i) => (
        <div
          key={i}
          ref={(el) => {
            barsRef.current[i] = el
          }}
          className="h-6 w-[3px] origin-center rounded-full bg-neutral-200"
          style={{ transform: `scaleY(${MIN_SCALE})` }}
        />
      ))}
    </div>
  )
}
