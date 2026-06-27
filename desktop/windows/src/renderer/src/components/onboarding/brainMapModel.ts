import type { Memory } from '../../hooks/useMemories'
import { APP_MEMORY_PREFIX, APP_MEMORY_TAG } from '../../lib/appMemories'

export type BrainNode = {
  x: number // normalized 0..1
  y: number
  vx: number
  vy: number
  r: number // base radius in px
  hue: number
  pulse: number // animation phase offset
  label?: string // memory headline/text; absent for decorative nodes
}

export type BrainEdge = { a: number; b: number; o: number }

const MAX_NODES = 100
const DECORATIVE_COUNT = 15

// Map a memory category to a node hue, matching the desktop app's scheme:
// app-related memories are purple, everything else (answers like language and
// goals, plus general memories) is blue.
export function categoryHue(category?: string | null): number {
  const c = (category ?? '').toLowerCase()
  if (c.includes('app')) return 275 // purple
  return 210 // blue
}

// Hue for a memory node. App-index memories are forced purple regardless of
// the server-assigned category (the server may ignore/reassign our category),
// detected by the deterministic "Uses " content prefix or the provenance tag.
// Everything else defers to categoryHue.
export function memoryHue(m: Memory): number {
  const content = m.content ?? ''
  const isAppMemory =
    content.startsWith(APP_MEMORY_PREFIX) || (m.tags?.includes(APP_MEMORY_TAG) ?? false)
  if (isAppMemory) return 275 // purple
  return categoryHue(m.category)
}

function makeNode(hue: number, r: number, label?: string): BrainNode {
  return {
    x: 0.1 + Math.random() * 0.8,
    y: 0.12 + Math.random() * 0.76,
    vx: (Math.random() - 0.5) * 0.00018,
    vy: (Math.random() - 0.5) * 0.00018,
    r,
    hue,
    pulse: Math.random() * Math.PI * 2,
    label
  }
}

// A short, single-line label for a memory node, from its headline or content.
function memoryLabel(m: Memory): string | undefined {
  const raw = (m.headline ?? m.content ?? '').replace(/\s+/g, ' ').trim()
  if (!raw) return undefined
  return raw.length <= 22 ? raw : raw.slice(0, 21).trimEnd() + '…'
}

// Build nodes from memories (capped at 100), or a decorative fallback when empty.
export function buildNodes(memories?: Memory[]): BrainNode[] {
  const nodes: BrainNode[] = []
  if (memories && memories.length > 0) {
    for (const m of memories.slice(0, MAX_NODES)) {
      nodes.push(makeNode(memoryHue(m), 1.8 + Math.random() * 2.6, memoryLabel(m)))
    }
  } else {
    for (let i = 0; i < DECORATIVE_COUNT; i++) {
      nodes.push(makeNode(195 + Math.random() * 40, 1.6 + Math.random() * 3.2))
    }
  }
  // Anchor a larger hub node near center.
  if (nodes.length > 0) {
    nodes[0].r = 5
    nodes[0].x = 0.5
    nodes[0].y = 0.46
  }
  return nodes
}

// Stable signature used to resume the animation across step remounts.
export function signatureOf(memories?: Memory[]): string {
  if (!memories || memories.length === 0) return 'decorative'
  return memories
    .slice(0, MAX_NODES)
    .map((m) => m.id)
    .join(',')
}

// Module-level cache keeps node positions continuous across step transitions.
let cachedSignature: string | null = null
let cachedNodes: BrainNode[] | null = null

export function getOrBuildNodes(memories?: Memory[]): BrainNode[] {
  const sig = signatureOf(memories)
  if (sig === cachedSignature && cachedNodes) return cachedNodes
  cachedNodes = buildNodes(memories)
  cachedSignature = sig
  return cachedNodes
}

// Connect each node to its nearest ~3 neighbors. Same-hue (same-category)
// distances are scaled down so those edges are preferred. Returns de-duplicated
// edges with a distance-based opacity.
export function computeEdges(nodes: BrainNode[], W: number, H: number): BrainEdge[] {
  const K = 3
  const maxDist = Math.min(W, H) * 0.55
  const seen = new Set<string>()
  const edges: BrainEdge[] = []
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i]
    const dists: { j: number; d: number }[] = []
    for (let j = 0; j < nodes.length; j++) {
      if (i === j) continue
      const b = nodes[j]
      const dx = (a.x - b.x) * W
      const dy = (a.y - b.y) * H
      let d = Math.hypot(dx, dy)
      if (a.hue === b.hue) d *= 0.6
      dists.push({ j, d })
    }
    dists.sort((p, q) => p.d - q.d)
    for (let k = 0; k < Math.min(K, dists.length); k++) {
      const { j, d } = dists[k]
      if (d > maxDist) continue
      const key = i < j ? `${i}-${j}` : `${j}-${i}`
      if (seen.has(key)) continue
      seen.add(key)
      edges.push({ a: i, b: j, o: Math.max(0, 1 - d / maxDist) * 0.5 })
    }
  }
  return edges
}
