import { describe, it, expect, beforeEach } from 'vitest'
import { GraphSimulation, __clearLayoutCacheForTests } from './useGraphSimulation'
import type { KnowledgeGraph } from '../../../shared/types'

const g1: KnowledgeGraph = {
  nodes: [{ id: 'user', label: 'Ander', nodeType: 'person', aliases: [], memoryIds: [] }],
  edges: []
}
const g2: KnowledgeGraph = {
  nodes: [
    { id: 'user', label: 'Ander', nodeType: 'person', aliases: [], memoryIds: [] },
    { id: 'language_en', label: 'English', nodeType: 'concept', aliases: [], memoryIds: [] }
  ],
  edges: [{ id: 'e1', sourceId: 'user', targetId: 'language_en', label: 'prefers', memoryIds: [] }]
}

describe('GraphSimulation', () => {
  // The layout cache is module-scoped (by design — it must survive a real
  // component remount), so it otherwise leaks a settled g1/g2 layout from one
  // test into the next. Reset it so each test settles from a clean slate.
  beforeEach(() => {
    __clearLayoutCacheForTests()
  })

  it('pins the center node at the origin', () => {
    const sim = new GraphSimulation('user')
    sim.setGraph(g1)
    sim.settle(50)
    const user = sim.getPositions().find((p) => p.id === 'user')!
    expect(user.x).toBeCloseTo(0, 5)
    expect(user.y).toBeCloseTo(0, 5)
    expect(user.z).toBeCloseTo(0, 5)
  })

  it('adds only new nodes and preserves existing positions', () => {
    const sim = new GraphSimulation('user')
    sim.setGraph(g1)
    sim.settle(50)
    sim.setGraph(g2)
    const before = sim.getPositions().find((p) => p.id === 'language_en')!
    expect(before).toBeDefined()
    // user remains pinned
    const user = sim.getPositions().find((p) => p.id === 'user')!
    expect(user.x).toBeCloseTo(0, 5)
    // language node exists and has finite coordinates
    expect(Number.isFinite(before.x)).toBe(true)
  })

  it('marks freshly-added node ids so the renderer can animate them in', () => {
    const sim = new GraphSimulation('user')
    sim.setGraph(g1)
    expect(sim.consumeNewlyAdded()).toEqual(['user'])
    sim.setGraph(g2)
    expect(sim.consumeNewlyAdded()).toEqual(['language_en'])
    expect(sim.consumeNewlyAdded()).toEqual([]) // consumed
  })

  it('settles synchronously inside setGraph, leaving nothing for the render loop', () => {
    // setGraph() now runs its settle as one synchronous batch (so the entry
    // animation is a cheap, deterministic tween toward an already-fixed target,
    // not a live physics convergence spread across frames) — settleFrame()
    // should report there's nothing left to do immediately after.
    const sim = new GraphSimulation('user')
    sim.setGraph(g2)

    expect(sim.settleFrame()).toBe(false)
  })

  it('reuses a cached layout for an identical node set instead of re-settling', () => {
    const sim1 = new GraphSimulation('user')
    sim1.setGraph(g2)
    const sizeScale1 = sim1.getPositions().find((p) => p.id === 'language_en')!.sizeScale

    // A second, independent instance (e.g. a remount) with the exact same node
    // set should adopt the first instance's settled sizeScale verbatim — if it
    // were re-settling from scratch, sizeScale is re-rolled via Math.random()
    // and would essentially never match.
    const sim2 = new GraphSimulation('user')
    sim2.setGraph(g2)
    const sizeScale2 = sim2.getPositions().find((p) => p.id === 'language_en')!.sizeScale

    expect(sizeScale2).toBe(sizeScale1)
  })

  it('reports a freshly-added node at its seed spot, distinct from its settled target', () => {
    const sim = new GraphSimulation('user')
    sim.setGraph(g2)

    const rendered = sim.getPositions().find((p) => p.id === 'language_en')!
    const settled = sim.liveNode('language_en')!
    // The renderer's initial position (seed) and its per-frame lerp target
    // (already-settled) must differ — otherwise there is nothing to animate.
    expect(rendered.x === settled.x && rendered.y === settled.y).toBe(false)
  })

  // A user-centered graph with several leaves — enough for the layout to spread.
  const gBig: KnowledgeGraph = {
    nodes: [
      { id: 'user', label: 'Ander', nodeType: 'person', aliases: [], memoryIds: [] },
      ...Array.from({ length: 8 }, (_, i) => ({
        id: `n${i}`,
        label: `Node ${i}`,
        nodeType: 'thing',
        aliases: [],
        memoryIds: []
      }))
    ],
    edges: Array.from({ length: 8 }, (_, i) => ({
      id: `e${i}`,
      sourceId: 'user',
      targetId: `n${i}`,
      label: 'rel',
      memoryIds: []
    }))
  }

  it('spreads nodes through depth (non-zero z variance) on the 3D interactive path', () => {
    const sim = new GraphSimulation('user', 3)
    sim.setGraph(gBig)
    sim.settle(60)
    const zs = gBig.nodes.filter((n) => n.id !== 'user').map((n) => sim.liveNode(n.id)!.z ?? 0)
    const mean = zs.reduce((a, b) => a + b, 0) / zs.length
    const variance = zs.reduce((a, b) => a + (b - mean) ** 2, 0) / zs.length
    // Real 3D: the cloud has depth, and at least one node is well off the z=0 plane.
    expect(variance).toBeGreaterThan(1)
    expect(Math.max(...zs.map((z) => Math.abs(z)))).toBeGreaterThan(5)
  })

  it('keeps the layout planar (z ≈ 0) on the default 2D path', () => {
    const sim = new GraphSimulation('user') // default dimensions = 2
    sim.setGraph(gBig)
    sim.settle(60)
    for (const n of gBig.nodes) {
      expect(Math.abs(sim.liveNode(n.id)!.z ?? 0)).toBeLessThan(1e-9)
    }
  })

  it('never adopts a cached 2D layout for a 3D sim of the same node set', () => {
    // Regression: the layout cache used to be keyed by node ids alone, so the 2D
    // Memories card (which settles first) poisoned the cache for the full-screen
    // 3D page — every node adopted z=0 and the "3D" scene was a flat plane with
    // zero parallax (orbiting read as panning).
    const flat = new GraphSimulation('user', 2)
    flat.setGraph(gBig)
    flat.settle(60)

    const deep = new GraphSimulation('user', 3)
    deep.setGraph(gBig)
    deep.settle(60)
    const zs = gBig.nodes
      .filter((n) => n.id !== 'user')
      .map((n) => Math.abs(deep.liveNode(n.id)!.z ?? 0))
    // A cache hit on the 2D layout would leave every z exactly 0.
    expect(Math.max(...zs)).toBeGreaterThan(5)
  })

  it('prunes nodes absent from a shrinking graph (Show all → Show key round-trip)', () => {
    // Regression: setGraph only ever ADDED nodes (fine for grow-only onboarding),
    // so when the knowledge-graph viewer's cap shrank the set — toggling
    // "Show all 188" back to "Show key 120" — getPositions() kept reporting the
    // 188-node high-water mark and the scene never shed the dropped spheres.
    const sim = new GraphSimulation('user')
    sim.setGraph(gBig)
    sim.settle(60)
    const full = sim.getPositions().length
    expect(full).toBe(gBig.nodes.length)

    // Feed a strict subset (drop everything but the center + one node).
    const kept = gBig.nodes.slice(0, 2).map((n) => n.id)
    const shrunk: KnowledgeGraph = {
      nodes: gBig.nodes.filter((n) => kept.includes(n.id)),
      edges: gBig.edges.filter((e) => kept.includes(e.sourceId) && kept.includes(e.targetId))
    }
    sim.setGraph(shrunk)
    const after = sim.getPositions()
    expect(after.length).toBe(2)
    expect(after.map((p) => p.id).sort()).toEqual([...kept].sort())
    // The dropped nodes must be gone from the live map too, not just the report.
    expect(sim.liveNode(gBig.nodes[3].id)).toBeUndefined()
  })
})
