import { useEffect, useRef } from 'react'
import type { Memory } from '../../hooks/useMemories'
import { getOrBuildNodes, computeEdges } from './brainMapModel'

type BrainMapProps = { memories?: Memory[] }

// Animated memory graph for the onboarding wizard's right pane. Seeds from real
// memories (decorative fallback when empty) and keeps node positions continuous
// across step transitions via the model's module-level cache.
export function BrainMap({ memories }: BrainMapProps): React.JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const nodes = getOrBuildNodes(memories)
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let W = 0
    let H = 0

    const resize = (): void => {
      const rect = canvas.getBoundingClientRect()
      W = rect.width
      H = rect.height
      canvas.width = Math.max(1, Math.round(W * dpr))
      canvas.height = Math.max(1, Math.round(H * dpr))
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    const draw = (t: number): void => {
      ctx.clearRect(0, 0, W, H)

      // Soft central glow.
      const g = ctx.createRadialGradient(W * 0.5, H * 0.46, 0, W * 0.5, H * 0.46, W * 0.55)
      g.addColorStop(0, 'rgba(40,130,255,0.10)')
      g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g
      ctx.fillRect(0, 0, W, H)

      // Drift.
      for (const n of nodes) {
        n.x += n.vx
        n.y += n.vy
        if (n.x < 0.06 || n.x > 0.94) n.vx *= -1
        if (n.y < 0.08 || n.y > 0.92) n.vy *= -1
      }

      // Edges.
      ctx.lineWidth = 0.8
      for (const e of computeEdges(nodes, W, H)) {
        const a = nodes[e.a]
        const b = nodes[e.b]
        ctx.strokeStyle = `rgba(120,200,255,${e.o.toFixed(3)})`
        ctx.beginPath()
        ctx.moveTo(a.x * W, a.y * H)
        ctx.lineTo(b.x * W, b.y * H)
        ctx.stroke()
      }

      // Nodes with glow + pulse.
      ctx.font = '10px system-ui, -apple-system, "Segoe UI", sans-serif'
      ctx.textBaseline = 'middle'
      for (const n of nodes) {
        const px = n.x * W
        const py = n.y * H
        const pulse = 0.6 + 0.4 * Math.sin(t * 0.0016 + n.pulse)
        const rr = n.r * (0.85 + 0.3 * pulse)
        const glow = ctx.createRadialGradient(px, py, 0, px, py, rr * 5)
        glow.addColorStop(0, `hsla(${n.hue},95%,70%,${(0.55 * pulse).toFixed(3)})`)
        glow.addColorStop(1, `hsla(${n.hue},95%,70%,0)`)
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(px, py, rr * 5, 0, Math.PI * 2)
        ctx.fill()
        ctx.fillStyle = `hsla(${n.hue},90%,62%,0.98)`
        ctx.beginPath()
        ctx.arc(px, py, rr, 0, Math.PI * 2)
        ctx.fill()

        // Memory label beside the node; flips to the left near the right edge so
        // it doesn't run off-canvas. Decorative nodes have no label.
        if (n.label) {
          ctx.fillStyle = 'rgba(255,255,255,0.6)'
          if (px > W * 0.7) {
            ctx.textAlign = 'right'
            ctx.fillText(n.label, px - rr - 5, py)
          } else {
            ctx.textAlign = 'left'
            ctx.fillText(n.label, px + rr + 5, py)
          }
        }
      }
    }

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    if (reduced) {
      draw(0)
    } else {
      const loop = (t: number): void => {
        draw(t)
        raf = requestAnimationFrame(loop)
      }
      raf = requestAnimationFrame(loop)
    }

    return () => {
      if (raf) cancelAnimationFrame(raf)
      ro.disconnect()
    }
  }, [memories])

  return <canvas ref={canvasRef} className="absolute inset-0 block h-full w-full" />
}
