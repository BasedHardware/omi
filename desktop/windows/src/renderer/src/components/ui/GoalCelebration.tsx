import { useEffect, useState } from 'react'

type Particle = {
  id: number
  color: string
  size: number
  angle: number
  distance: number
  rotation: number
  isRect: boolean
  x: number
  y: number
}

const COLORS = [
  '#facc15', '#fbbf24', '#22c55e', '#3b82f6',
  '#ec4899', '#f97316', '#06b6d4', '#a78bfa',
  '#5b02e0', '#8b5cf6',
]

function makeParticles(count: number): Particle[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i,
    color: COLORS[Math.floor(Math.random() * COLORS.length)],
    size: 4 + Math.random() * 6,
    angle: (Math.random() * Math.PI * 2),
    distance: 80 + Math.random() * 260,
    rotation: Math.random() * 1080,
    isRect: Math.random() > 0.5,
    x: 30 + Math.random() * 40, // % from left
    y: 30 + Math.random() * 40, // % from top
  }))
}

export function GoalCelebration(): React.JSX.Element | null {
  const [visible, setVisible] = useState(false)
  const [goalTitle, setGoalTitle] = useState('')
  const [phase, setPhase] = useState<'in' | 'text' | 'out'>('in')
  const [particles] = useState(() => makeParticles(48))

  useEffect(() => {
    const handler = (e: Event): void => {
      const detail = (e as CustomEvent<{ title: string }>).detail
      setGoalTitle(detail.title)
      setVisible(true)
      setPhase('in')

      setTimeout(() => setPhase('text'), 400)
      setTimeout(() => setPhase('out'), 3200)
      setTimeout(() => setVisible(false), 3700)
    }
    window.addEventListener('goal-completed', handler)
    return () => window.removeEventListener('goal-completed', handler)
  }, [])

  if (!visible) return null

  return (
    <div
      className="pointer-events-none fixed inset-0 z-[9998] overflow-hidden"
      style={{ opacity: phase === 'out' ? 0 : 1, transition: 'opacity 0.5s ease-out' }}
    >
      {/* Dark overlay */}
      <div
        className="absolute inset-0 bg-black/50"
        style={{ opacity: phase === 'in' ? 0 : 1, transition: 'opacity 0.3s ease-out' }}
      />

      {/* Confetti particles */}
      {particles.map((p) => (
        <div
          key={p.id}
          className="absolute"
          style={{
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.isRect ? p.size : p.size,
            height: p.isRect ? p.size * 2.5 : p.size,
            backgroundColor: p.color,
            borderRadius: p.isRect ? 2 : '50%',
            transform: phase === 'in'
              ? 'translate(-50%,-50%) scale(0.1) rotate(0deg)'
              : `translate(calc(-50% + ${Math.cos(p.angle) * p.distance}px), calc(-50% + ${Math.sin(p.angle) * p.distance - 40}px)) scale(${phase === 'out' ? 0.1 : 1}) rotate(${p.rotation}deg)`,
            opacity: phase === 'out' ? 0 : 1,
            transition: phase === 'in'
              ? 'transform 0.8s cubic-bezier(0.16,1,0.3,1), opacity 0.8s ease-out'
              : 'opacity 0.8s ease-out, transform 0.8s ease-out',
          }}
        />
      ))}

      {/* Celebration text */}
      {phase === 'text' && (
        <div
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-center"
          style={{ animation: 'celebrationIn 0.5s cubic-bezier(0.16,1,0.3,1) both' }}
        >
          <p
            className="text-4xl font-bold"
            style={{
              background: 'linear-gradient(90deg, #facc15, #f97316, #facc15)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              textShadow: 'none',
              filter: 'drop-shadow(0 0 24px rgba(250,204,21,0.6))',
            }}
          >
            Goal Completed!
          </p>
          {goalTitle && (
            <p className="mt-3 text-lg font-medium text-white/90">{goalTitle}</p>
          )}
        </div>
      )}

      <style>{`
        @keyframes celebrationIn {
          from { opacity: 0; transform: translate(-50%,-50%) scale(0.7); }
          to { opacity: 1; transform: translate(-50%,-50%) scale(1); }
        }
      `}</style>
    </div>
  )
}
