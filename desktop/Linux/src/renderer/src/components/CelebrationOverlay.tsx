import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useGoals } from '../stores/goals'
import type { Goal } from '../api/types'

// Confetti palette ported from GoalCelebrationView.swift (gold, green, blue, pink, orange, cyan, mint, purple).
const CONFETTI_COLORS = [
  '#FFE600',
  '#FFD700',
  '#22C55E',
  '#3399FF',
  '#EC4899',
  '#F97316',
  '#22D3EE',
  '#6EE7B7',
  '#8B5CF6',
  'rgba(139,92,246,0.7)'
]

const PARTICLE_COUNT = 40
const DISMISS_MS = 2500

interface Particle {
  left: number
  delay: number
  duration: number
  size: number
  color: string
  isRect: boolean
  drift: number
}

function makeParticles(): Particle[] {
  return Array.from({ length: PARTICLE_COUNT }, () => {
    const size = 4 + Math.random() * 6
    return {
      left: Math.random() * 100,
      delay: Math.random() * 0.5,
      duration: 1.8 + Math.random() * 1.4,
      size,
      color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
      isRect: Math.random() > 0.5,
      drift: (Math.random() - 0.5) * 80
    }
  })
}

/**
 * Fullscreen goal-completion celebration. Listens to the goals store's
 * `lastCompletedGoal` signal, plays a confetti + gradient-title burst, then
 * clears the signal after ~2.5s. Mount it once near the app root (owned elsewhere).
 */
export default function CelebrationOverlay() {
  const goal = useGoals((s) => s.lastCompletedGoal)
  const clearCompletedGoal = useGoals((s) => s.clearCompletedGoal)
  // Snapshot the goal so the overlay keeps rendering while it fades out, even after the store clears.
  const [shown, setShown] = useState<Goal | null>(null)
  const particles = useMemo(makeParticles, [shown])
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!goal) return
    setShown(goal)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      timer.current = null
      setShown(null)
    }, DISMISS_MS)
    // The store signal is one-shot; clear it so re-completing the same goal re-triggers.
    clearCompletedGoal()
  }, [goal, clearCompletedGoal])

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    []
  )

  if (!shown) return null

  const target = shown.target_value ?? 1
  const unit = shown.unit ? ` ${shown.unit}` : ''

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        pointerEvents: 'none',
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden'
      }}
    >
      {/* Confetti rain */}
      {particles.map((p, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            top: 0,
            left: `${p.left}%`,
            width: p.size,
            height: p.isRect ? p.size * 2.5 : p.size,
            borderRadius: p.isRect ? 1.5 : '50%',
            background: p.color,
            marginLeft: p.drift,
            animation: `confettiFall ${p.duration}s ${p.delay}s linear forwards`
          }}
        />
      ))}

      {/* Celebration text */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 16,
          textAlign: 'center',
          animation: 'celebratePop 0.5s ease-out forwards'
        }}
      >
        <div
          style={{
            fontSize: 32,
            fontWeight: 700,
            backgroundImage: 'linear-gradient(90deg, #FDE047, #F97316, #FDE047)',
            WebkitBackgroundClip: 'text',
            backgroundClip: 'text',
            color: 'transparent',
            filter: 'drop-shadow(0 0 12px rgba(253,224,71,0.55))'
          }}
        >
          Goal Completed!
        </div>
        <div style={{ fontSize: 18, fontWeight: 500, color: '#fff', maxWidth: 420, padding: '0 40px' }}>
          {shown.title}
        </div>
        <div className="tnum" style={{ fontSize: 14, color: 'rgba(255,255,255,0.7)' }}>
          {Math.round(target)}
          {unit} reached
        </div>
      </div>
    </div>
  )
}
