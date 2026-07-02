import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import { EmptyState, Spinner } from '../../components/ui'
import { useAuth } from '../../stores/auth'
import type { KnowledgeGraphEdge, KnowledgeGraphNode } from '../../api/types'

// Knowledge graph, 2D force-directed layout. The Mac app renders this in 3D
// (SceneKit); node-type colors, connection-sized nodes, glow halos and blended
// edge colors all match MemoryGraphPage.swift + ForceDirectedSimulation.swift.
// macOS dark-mode system colors, matching MemoryGraphPage.swift node types.
const TYPE_COLOR: Record<string, string> = {
  person: '#64D2FF', // .cyan
  place: '#00FF9E', // mint Color(0,1,0.62)
  organization: '#FF9F0A', // .orange
  thing: '#BF5AF2', // .purple
  concept: '#0A84FF' // .systemBlue
}
const USER_ID = '__user__'

interface Pos {
  x: number
  y: number
  vx: number
  vy: number
}

/** Parse "#rrggbb" into [r,g,b]. */
function hexRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

/** Average two node-type colors at the given alpha (mirrors blendColors in the Mac app). */
function blendEdgeColor(a: string, b: string, alpha: number): string {
  const [ar, ag, ab] = hexRgb(a)
  const [br, bg, bb] = hexRgb(b)
  return `rgba(${Math.round((ar + br) / 2)}, ${Math.round((ag + bg) / 2)}, ${Math.round((ab + bb) / 2)}, ${alpha})`
}

const colorForNode = (n: KnowledgeGraphNode) => TYPE_COLOR[n.node_type ?? 'concept'] || '#3B82F6'

/**
 * Shared force-directed brain-map renderer. Used full-bleed by GraphPage and in a
 * compact card by the Memories page. Owns its own simulation + animation loop so
 * either mount lays out independently.
 */
export function BrainMapGraph({
  nodes,
  edges,
  userName,
  width = 900,
  height = 560
}: {
  nodes: KnowledgeGraphNode[]
  edges: KnowledgeGraphEdge[]
  userName: string
  width?: number
  height?: number
}) {
  const W = width
  const H = height
  const [tick, setTick] = useState(0)
  const posRef = useRef<Map<string, Pos>>(new Map())

  // Connection count per node, from real edges + the synthetic user-anchor edges
  // (mirrors recountConnections() in ForceDirectedSimulation.swift). Drives node size.
  const connections = useMemo(() => {
    const counts = new Map<string, number>()
    for (const n of nodes) counts.set(n.id, 0)
    for (const e of edges) {
      counts.set(e.source_id, (counts.get(e.source_id) ?? 0) + 1)
      counts.set(e.target_id, (counts.get(e.target_id) ?? 0) + 1)
    }
    // every node also links to the user anchor
    for (const n of nodes) counts.set(n.id, (counts.get(n.id) ?? 0) + 1)
    return counts
  }, [nodes, edges])

  // radius ~14 + min(connections, 10) * 2.5 (ForceDirectedSimulation.nodeRadius)
  const radiusFor = (id: string) => 14 + Math.min(connections.get(id) ?? 0, 10) * 2.5

  const renderEdges = useMemo(() => {
    const userEdges = nodes.map((n) => ({ id: 'u' + n.id, source_id: USER_ID, target_id: n.id }))
    return [...edges, ...userEdges]
  }, [nodes, edges])

  useEffect(() => {
    const pos = new Map<string, Pos>()
    const all = [{ id: USER_ID, label: userName } as KnowledgeGraphNode, ...nodes]
    all.forEach((n, i) => {
      const angle = (i / Math.max(1, all.length)) * Math.PI * 2
      pos.set(n.id, { x: W / 2 + Math.cos(angle) * 200, y: H / 2 + Math.sin(angle) * 160, vx: 0, vy: 0 })
    })
    pos.set(USER_ID, { x: W / 2, y: H / 2, vx: 0, vy: 0 })
    posRef.current = pos

    let frame = 0
    let raf = 0
    const userEdges: KnowledgeGraphEdge[] = nodes.map((n) => ({ id: 'u' + n.id, source_id: USER_ID, target_id: n.id }))
    const allEdges = [...edges, ...userEdges]
    const step = () => {
      const p = posRef.current
      // Repulsion
      const ids = [...p.keys()]
      for (let i = 0; i < ids.length; i++) {
        for (let j = i + 1; j < ids.length; j++) {
          const a = p.get(ids[i])!
          const b = p.get(ids[j])!
          let dx = a.x - b.x
          let dy = a.y - b.y
          let d2 = dx * dx + dy * dy
          if (d2 < 0.01) {
            dx = Math.cos(i + j) * 0.5
            dy = Math.sin(i + j) * 0.5
            d2 = 0.25
          }
          const f = 9000 / d2
          const d = Math.sqrt(d2)
          a.vx += (dx / d) * f
          a.vy += (dy / d) * f
          b.vx -= (dx / d) * f
          b.vy -= (dy / d) * f
        }
      }
      // Spring along edges
      for (const e of allEdges) {
        const a = p.get(e.source_id)
        const b = p.get(e.target_id)
        if (!a || !b) continue
        const dx = b.x - a.x
        const dy = b.y - a.y
        const d = Math.sqrt(dx * dx + dy * dy) || 1
        const f = (d - 120) * 0.02
        a.vx += (dx / d) * f
        a.vy += (dy / d) * f
        b.vx -= (dx / d) * f
        b.vy -= (dy / d) * f
      }
      for (const [id, n] of p) {
        if (id === USER_ID) {
          n.x = W / 2
          n.y = H / 2
          continue
        }
        n.vx *= 0.85
        n.vy *= 0.85
        n.x = Math.max(40, Math.min(W - 40, n.x + n.vx))
        n.y = Math.max(40, Math.min(H - 40, n.y + n.vy))
      }
      setTick((t) => t + 1)
      frame++
      if (frame < 220) raf = requestAnimationFrame(step)
    }
    if (all.length > 1) raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, W, H])

  const userPos = posRef.current.get(USER_ID)
  const userR = 30 + Math.min(nodes.length, 10) * 0.5

  return (
    <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" data-tick={tick}>
      {renderEdges.map((e) => {
        const a = posRef.current.get(e.source_id)
        const b = posRef.current.get(e.target_id)
        if (!a || !b) return null
        // Edge color = average of its two node-type colors at ~0.25 alpha.
        const sn = nodes.find((n) => n.id === e.source_id)
        const tn = nodes.find((n) => n.id === e.target_id)
        const stroke =
          sn || tn
            ? blendEdgeColor(sn ? colorForNode(sn) : '#FFFFFF', tn ? colorForNode(tn) : '#FFFFFF', 0.25)
            : 'rgba(255,255,255,0.1)'
        return <line key={e.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={stroke} strokeWidth={1} />
      })}
      {nodes.map((n) => {
        const p = posRef.current.get(n.id)
        if (!p) return null
        const color = colorForNode(n)
        const r = radiusFor(n.id)
        return (
          <g key={n.id}>
            {/* soft glow halo: larger translucent circle, screen blend */}
            <circle cx={p.x} cy={p.y} r={r * 2.5} fill={color} opacity={0.16} style={{ mixBlendMode: 'screen' }} />
            <circle cx={p.x} cy={p.y} r={r} fill={color} opacity={0.9} />
            <text x={p.x} y={p.y + r + 12} textAnchor="middle" fill="rgba(255,255,255,0.8)" fontSize={11}>
              {n.label}
            </text>
          </g>
        )
      })}
      {userPos && (
        <g>
          <circle cx={userPos.x} cy={userPos.y} r={userR * 2.2} fill="#fff" opacity={0.14} style={{ mixBlendMode: 'screen' }} />
          <circle cx={userPos.x} cy={userPos.y} r={userR} fill="#fff" />
          <text x={userPos.x} y={userPos.y + userR + 14} textAnchor="middle" fill="#fff" fontSize={13} fontWeight={600}>
            {userName}
          </text>
        </g>
      )}
    </svg>
  )
}

/**
 * Loads the knowledge graph and rebuild-polls until it populates (mirrors
 * MemoryGraphViewModel.prepareGraph). Shared by the page and the Memories card.
 */
export function useKnowledgeGraph() {
  const [nodes, setNodes] = useState<KnowledgeGraphNode[]>([])
  const [edges, setEdges] = useState<KnowledgeGraphEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [rebuilding, setRebuilding] = useState(false)
  const cancelled = useRef(false)

  const load = async (): Promise<number> => {
    setLoading(true)
    try {
      const g = await api.getKnowledgeGraph()
      const ns = g.nodes ?? []
      setNodes(ns)
      setEdges(g.edges ?? [])
      return ns.length
    } catch {
      setNodes([])
      setEdges([])
      return 0
    } finally {
      setLoading(false)
    }
  }

  // Prepare: load once, and if empty, rebuild and poll until populated.
  useEffect(() => {
    cancelled.current = false
    const prepare = async () => {
      const count = await load()
      if (count > 0 || cancelled.current) return
      setRebuilding(true)
      try {
        await api.rebuildKnowledgeGraph()
      } catch {
        // ignore; still poll in case a build is already running server-side
      }
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 3000))
        if (cancelled.current) break
        const n = await load()
        if (n > 0) break
      }
      if (!cancelled.current) setRebuilding(false)
    }
    void prepare()
    return () => {
      cancelled.current = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Manual rebuild button: kick a rebuild, then poll a few times.
  const rebuild = async () => {
    setRebuilding(true)
    try {
      await api.rebuildKnowledgeGraph()
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 3000))
        if (cancelled.current) break
        const n = await load()
        if (n > 0) break
      }
    } catch {
      // ignore
    } finally {
      if (!cancelled.current) setRebuilding(false)
    }
  }

  return { nodes, edges, loading, rebuilding, load, rebuild }
}

export function GraphPage() {
  const auth = useAuth((s) => s.state)
  const { nodes, edges, loading, rebuilding, rebuild } = useKnowledgeGraph()
  const userName = auth?.name || 'You'

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '44px 26px 14px' }}>
        <div>
          <div style={{ fontSize: 19, fontWeight: 700 }}>Memory Graph</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginTop: 2 }}>
            People, places, and ideas Omi has connected from your memories
          </div>
        </div>
        <button className="btn-secondary" style={{ fontSize: 12.5 }} onClick={() => void rebuild()} disabled={rebuilding}>
          {rebuilding ? 'Rebuilding…' : 'Rebuild graph'}
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, padding: '0 20px 20px' }}>
        {loading && nodes.length === 0 ? (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spinner size={22} />
          </div>
        ) : nodes.length === 0 ? (
          <EmptyState
            title="Brain map will appear once enough linked memories are available"
            subtitle={
              rebuilding
                ? 'Building your brain map from linked memories…'
                : 'Omi maps the people, places and concepts in your life. Try Rebuild graph.'
            }
          />
        ) : (
          <div className="card" style={{ height: '100%', overflow: 'hidden', background: '#1A1A1A' }}>
            <BrainMapGraph nodes={nodes} edges={edges} userName={userName} />
          </div>
        )}
      </div>
    </div>
  )
}
