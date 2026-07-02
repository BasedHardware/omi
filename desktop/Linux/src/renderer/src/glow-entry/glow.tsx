import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'

// Screen-edge glow border, ported from GlowBorderView.swift. Focused = green
// (hue ~0.38), distracted = red (hue 0.0). Border 20px, glow padding 30px,
// corner radius 12px, dual blur (8px outer + 2px inner), 0.3s fade-in, ~1.5s
// wobble, 0.5s fade-out (total ~2.5s).

document.body.style.background = 'transparent'

const FOCUSED = { core: '#22e06a', edge: '#0bd6a6' } // green->cyan
const DISTRACTED = { core: '#ff4d4d', edge: '#ff8a3d' } // red->orange

function Glow() {
  const [visible, setVisible] = useState(false)
  const [status, setStatus] = useState<'focused' | 'distracted'>('focused')

  useEffect(() => {
    return window.omi.focus.onGlow((g) => {
      setStatus(g.status)
      setVisible(true)
      window.setTimeout(() => setVisible(false), 2200)
    })
  }, [])

  const c = status === 'focused' ? FOCUSED : DISTRACTED
  const pad = 30
  const border = 20

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        opacity: visible ? 1 : 0,
        transition: `opacity ${visible ? 0.3 : 0.5}s ease`,
        pointerEvents: 'none'
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: pad,
          borderRadius: 12,
          border: `${border}px solid transparent`,
          background: `linear-gradient(120deg, ${c.core}, ${c.edge}, ${c.core}) border-box`,
          WebkitMask: 'linear-gradient(#000 0 0) padding-box, linear-gradient(#000 0 0)',
          WebkitMaskComposite: 'xor',
          maskComposite: 'exclude',
          filter: 'blur(8px)',
          animation: visible ? 'glowWobble 1.5s ease-in-out infinite alternate' : 'none'
        }}
      />
      <div
        style={{
          position: 'absolute',
          inset: pad,
          borderRadius: 12,
          border: `2px solid ${c.core}`,
          opacity: 0.8,
          filter: 'blur(2px)'
        }}
      />
      <style>{`
        @keyframes glowWobble {
          0% { filter: blur(8px); opacity: 0.85; }
          100% { filter: blur(11px); opacity: 1; }
        }
      `}</style>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Glow />
  </React.StrictMode>
)
