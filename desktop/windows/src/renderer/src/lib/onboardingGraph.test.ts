import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { KnowledgeGraph } from '../../../shared/types'
import {
  resetOnboardingGraph,
  initOnboardingGraph,
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
  const snapshot = (): KnowledgeGraph => ({ nodes: [...nodes.values()], edges: [...edges.values()] })
  ;(globalThis as unknown as { window: { omi: unknown } }).window = {
    omi: {
      localGraphClear: vi.fn(async () => {
        nodes.clear()
        edges.clear()
      }),
      localGraphUpsert: vi.fn(async (ns: KnowledgeGraph['nodes'], es: KnowledgeGraph['edges']) => {
        for (const n of ns) nodes.set(n.id, { ...n, aliases: n.aliases ?? [], memoryIds: [] })
        for (const e of es) edges.set(e.id, { ...e, memoryIds: [] })
        return snapshot()
      }),
      localGraphLoad: vi.fn(async () => snapshot())
    }
  }
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

  // Regression: onboarding re-mounts on every renderer reload (the main process
  // reloads a crashed renderer) and on a relaunch, resuming at the saved step.
  // Clearing the graph on those mounts deleted the `user` node written by the
  // name step — and every edge anchors at `user`, so the map lost the user's own
  // node and BrainGraph (which only draws an edge when BOTH endpoints exist)
  // rendered nothing but unconnected dots.
  describe('initOnboardingGraph', () => {
    it('clears the store on a FRESH start (step 0)', async () => {
      await addUserNode('Stale')
      await addAppNodes([{ name: 'Slack' }])
      await initOnboardingGraph(0, 'Ander')
      expect(getOnboardingGraph()).toEqual({ nodes: [], edges: [] })
    })

    it('does NOT clear on a RESUME — the user node and its edges survive', async () => {
      await addUserNode('Ander')
      await addLanguageNode('en', 'English')
      await addAppNodes([{ name: 'Slack' }])

      await initOnboardingGraph(6, 'Ander')

      const g = getOnboardingGraph()
      expect(g.nodes.map((n) => n.id).sort()).toEqual(['app_slack', 'language_en', 'user'])
      // Every edge still has both endpoints present — this is exactly what
      // BrainGraph filters on before it draws a line.
      const ids = new Set(g.nodes.map((n) => n.id))
      expect(g.edges.length).toBe(2)
      expect(g.edges.every((e) => ids.has(e.sourceId) && ids.has(e.targetId))).toBe(true)
    })

    it('re-adds a missing user node on resume so centerNodeId="user" resolves', async () => {
      // App nodes present, user node lost (e.g. an older build cleared it).
      await addAppNodes([{ name: 'Slack' }])
      await initOnboardingGraph(6, 'Ander')

      const g = getOnboardingGraph()
      expect(g.nodes.find((n) => n.id === 'user')?.label).toBe('Ander')
      const ids = new Set(g.nodes.map((n) => n.id))
      expect(g.edges.every((e) => ids.has(e.sourceId) && ids.has(e.targetId))).toBe(true)
    })
  })
})
