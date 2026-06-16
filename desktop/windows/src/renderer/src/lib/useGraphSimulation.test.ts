import { describe, it, expect } from 'vitest'
import { GraphSimulation } from './useGraphSimulation'
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
})
