import { useEffect, useRef, useState } from 'react'

// Full-screen goal-completion celebration, ported from the macOS
// `GoalCelebrationView` (frozen v0.12.72). Four phases over ~3.5s: dim → confetti
// burst → gradient text → fade out. Choreography is faithful to Mac; motion is
// implemented with CSS transitions/tweens rather than a live physics sim (per
// the project's animation guidance — keep the choreography, optimize the impl).
//
// INV-UI-1: Mac's palette includes 2 purple particles; those are dropped here and
// replaced with neutral white. No purple anywhere.

// Phase offsets in ms from mount. Exported for the timing test.
export const CELEBRATION_TIMINGS = {
  confettiAt: 300,
  textAt: 800,
  fadeOutAt: 3000,
  doneAt: 3500
} as const

export type CelebrationPhase = 'dim' | 'confetti' | 'text' | 'fadeOut'

export interface CelebrationGoal {
  title: string
  target_value?: number | null
  unit?: string | null
}

// Confetti palette: Mac's 9-color set with the 2 purple shades swapped for white.
const CONFETTI_COLORS = [
  '#FACC15', // yellow
  '#FFD700', // gold
  '#22C55E', // green
  '#3B82F6', // blue
  '#EC4899', // pink
  '#F97316', // orange
  '#22D3EE', // cyan
  '#34D399', // mint
  '#FFFFFF' // white (replaces Mac's purple particles)
] as const

interface Particle {
  color: string
  size: number
  angle: number
  distance: number
  rotation: number
  isRect: boolean
}

function makeParticles(): Particle[] {
  return Array.from({ length: 40 }, () => ({
    color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
    size: 4 + Math.random() * 6, // 4–10px
    angle: Math.random() * 2 * Math.PI,
    distance: 80 + Math.random() * 220, // 80–300px
    rotation: Math.random() * 1080,
    isRect: Math.random() < 0.5
  }))
}

// 40-particle burst from screen center. Each particle animates outward along a
// random radial angle, spinning, then fades. The random set is built once (lazy
// state init); the burst/fade flip via timers. `motion-reduce:hidden` drops the
// whole burst under prefers-reduced-motion (CSS-only) so the dim + text still
// convey completion without motion.
function GoalConfetti(): React.JSX.Element {
  const [particles] = useState(makeParticles)
  const [animate, setAnimate] = useState(false)
  const [fadeOut, setFadeOut] = useState(false)

  useEffect(() => {
    const raf = requestAnimationFrame(() => setAnimate(true))
    const fade = setTimeout(() => setFadeOut(true), 1500)
    return () => {
      cancelAnimationFrame(raf)
      clearTimeout(fade)
    }
  }, [])

  return (
    <div className="pointer-events-none absolute inset-0 motion-reduce:hidden">
      {particles.map((p, i) => {
        const dx = Math.cos(p.angle) * p.distance
        const dy = Math.sin(p.angle) * p.distance - 40
        const scale = fadeOut ? 0.1 : animate ? 1 : 0.1
        const transform = animate
          ? `translate(-50%, -50%) translate(${dx}px, ${dy}px) rotate(${p.rotation}deg) scale(${scale})`
          : 'translate(-50%, -50%) scale(0.1)'
        return (
          <span
            key={i}
            className="absolute left-1/2 top-1/2"
            style={{
              width: p.size,
              height: p.isRect ? p.size * 2.5 : p.size,
              backgroundColor: p.color,
              borderRadius: p.isRect ? 1.5 : '9999px',
              transform,
              opacity: fadeOut ? 0 : 1,
              transition: 'transform 800ms ease-out, opacity 800ms ease-out'
            }}
          />
        )
      })}
    </div>
  )
}

export function GoalCelebration({
  goal,
  onDone
}: {
  goal: CelebrationGoal
  onDone: () => void
}): React.JSX.Element {
  const [phase, setPhase] = useState<CelebrationPhase>('dim')
  // Keep the latest onDone without re-running the one-shot schedule if the
  // parent re-renders mid-celebration.
  const onDoneRef = useRef(onDone)
  useEffect(() => {
    onDoneRef.current = onDone
  }, [onDone])

  useEffect(() => {
    const timers = [
      setTimeout(() => setPhase('confetti'), CELEBRATION_TIMINGS.confettiAt),
      setTimeout(() => setPhase('text'), CELEBRATION_TIMINGS.textAt),
      setTimeout(() => setPhase('fadeOut'), CELEBRATION_TIMINGS.fadeOutAt),
      setTimeout(() => onDoneRef.current(), CELEBRATION_TIMINGS.doneAt)
    ]
    return () => timers.forEach(clearTimeout)
  }, [])

  const dimOpacity = phase === 'dim' ? 0.4 : phase === 'fadeOut' ? 0 : 0.5
  const textVisible = phase === 'text'
  const target = Math.round(goal.target_value ?? 0)
  const caption = goal.unit ? `${target} ${goal.unit} reached` : `${target} reached`

  return (
    <div className="pointer-events-none fixed inset-0 z-[200] flex items-center justify-center">
      {/* Dim scrim */}
      <div
        className="absolute inset-0 bg-black"
        style={{
          opacity: dimOpacity,
          transition: `opacity ${phase === 'fadeOut' ? 500 : 300}ms ease-out`
        }}
      />

      {phase !== 'dim' && <GoalConfetti />}

      {(phase === 'text' || phase === 'fadeOut') && (
        <div
          className="relative flex flex-col items-center gap-4 px-10 text-center"
          style={{
            opacity: textVisible ? 1 : 0,
            transform: textVisible ? 'scale(1)' : 'scale(0.7)',
            transition: 'opacity 500ms ease-out, transform 500ms cubic-bezier(0.34, 1.56, 0.64, 1)'
          }}
        >
          <span
            className="bg-gradient-to-r from-yellow-300 via-orange-400 to-yellow-300 bg-clip-text text-[32px] font-bold text-transparent"
            style={{ filter: 'drop-shadow(0 0 12px rgba(250, 204, 21, 0.6))' }}
          >
            Goal Completed!
          </span>
          <span className="text-[18px] font-medium text-white">{goal.title}</span>
          <span className="text-[14px] text-white/70">{caption}</span>
        </div>
      )}
    </div>
  )
}
