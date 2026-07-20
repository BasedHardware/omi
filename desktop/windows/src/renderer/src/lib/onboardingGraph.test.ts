import { describe, it, expect, beforeEach, vi } from 'vitest'
import type {
  KnowledgeGraph,
  OnboardingGraphEdge,
  OnboardingGraphNode
} from '../../../shared/types'
import { native } from './native'

vi.mock('./native', () => ({
  native: {
    localGraphClear: vi.fn(),
    localGraphUpsert: vi.fn()
  }
}))

import {
  resetOnboardingGraph,
  addUserNode,
  addLanguageNode,
  addAppNodes,
  getOnboardingGraph,
  subscribeOnboardingGraph
} from './onboardingGraph'

// In-memory fake of the main-process store, exposed via window.omi.
function installFakeBridge(): void {
  const nodes = new Map<string, KnowledgeGraph['nodes'][number]>()
  const edges = new Map<string, KnowledgeGraph['edges'][number]>()
  const snapshot = (): KnowledgeGraph => ({
    nodes: [...nodes.values()],
    edges: [...edges.values()]
  })
  vi.mocked(native.localGraphClear).mockImplementation(async () => {
    nodes.clear()
    edges.clear()
  })
  vi.mocked(native.localGraphUpsert).mockImplementation(
    async (ns: OnboardingGraphNode[], es: OnboardingGraphEdge[]) => {
      for (const n of ns) nodes.set(n.id, { ...n, aliases: n.aliases ?? [], memoryIds: [] })
      for (const e of es) edges.set(e.id, { ...e, memoryIds: [] })
      return snapshot()
    }
  )
}

describe('onboardingGraph', () => {
  beforeEach(async () => {
    installFakeBridge()
    await resetOnboardingGraph()
  })

  it('adds the user node and notifies subscribers', async () => {
    const seen: number[] = []
    const unsub = subscribeOnboardingGraph((g) => seen.push(g.nodes.length))
    await addUserNode('Ander')
    expect(getOnboardingGraph().nodes.map((n) => n.id)).toEqual(['user'])
    expect(seen.at(-1)).toBe(1)
    unsub()
  })

  it('adds a language node + edge after the user', async () => {
    await addUserNode('Ander')
    await addLanguageNode('en', 'English')
    const g = getOnboardingGraph()
    expect(g.nodes.map((n) => n.id).sort()).toEqual(['language_en', 'user'])
    expect(g.edges.map((e) => e.label)).toEqual(['prefers'])
  })

  it('adds app nodes and is idempotent on re-add', async () => {
    await addUserNode('Ander')
    await addAppNodes([{ name: 'Slack' }, { name: 'Figma' }])
    await addAppNodes([{ name: 'Slack' }]) // duplicate
    const g = getOnboardingGraph()
    const appIds = g.nodes.filter((n) => n.nodeType === 'thing').map((n) => n.id)
    expect(appIds.sort()).toEqual(['app_figma', 'app_slack'])
  })

  it('reset clears the graph', async () => {
    await addUserNode('Ander')
    await resetOnboardingGraph()
    expect(getOnboardingGraph().nodes).toEqual([])
  })
})
