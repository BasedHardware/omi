// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { Memory } from '../hooks/useMemories'
import type { KnowledgeGraph } from '../../../shared/types'
import { DEFAULT_NODE_CAP } from '../lib/graphDisplay'

// The inline brain-map PREVIEW on the Memories page must render decluttered — the
// same DEFAULT_NODE_CAP-capped node set and declutter labels the full-screen
// viewer uses — not the whole graph with every node named. This drives the real
// page and asserts the props handed to BrainGraph, since the WebGL canvas itself
// can't mount under jsdom.
let memoriesList: Memory[] = []
let graph: KnowledgeGraph = { nodes: [], edges: [] }
const brainGraphProps: { graph?: KnowledgeGraph; labelMode?: string; interactive?: boolean }[] = []

vi.mock('../hooks/useMemories', () => ({
  useMemories: () => ({
    memories: memoriesList,
    loading: false,
    error: null,
    canonicalLifecycleExposed: false,
    createMemory: vi.fn(),
    editMemory: vi.fn(),
    setMemoryVisibility: vi.fn(),
    deleteMemory: vi.fn(),
    refresh: vi.fn()
  })
}))

vi.mock('../hooks/useMemoryGraph', () => ({
  useMemoryGraph: () => ({ graph, centerNodeId: 'n0', rebuild: vi.fn(), rebuilding: false })
}))

// Capture the props the preview passes; render a probe node so hasGraph is true.
vi.mock('../components/graph/LazyBrainGraph', () => ({
  BrainGraph: (props: { graph: KnowledgeGraph; labelMode?: string; interactive?: boolean }) => {
    brainGraphProps.push(props)
    return (
      <div
        data-testid="preview-graph"
        data-node-count={props.graph.nodes.length}
        data-label-mode={props.labelMode ?? 'all'}
        data-interactive={String(!!props.interactive)}
      />
    )
  }
}))

vi.mock('../lib/toast', () => ({ toast: vi.fn() }))
vi.mock('../lib/apiClient', () => ({
  omiApi: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }
}))

const mem = (id: string): Memory => ({
  id,
  uid: 'u',
  content: `memory ${id}`,
  visibility: 'private',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z'
})

// A hub-and-spoke graph larger than the cap, so the cap actually bites. n0 is the
// center and connects to every other node — a stable importance ranking.
const NODE_TOTAL = DEFAULT_NODE_CAP + 40
const bigGraph: KnowledgeGraph = {
  nodes: Array.from({ length: NODE_TOTAL }, (_, i) => ({
    id: `n${i}`,
    label: `n${i}`,
    nodeType: 'concept',
    aliases: [],
    memoryIds: []
  })),
  edges: Array.from({ length: NODE_TOTAL - 1 }, (_, i) => ({
    id: `e${i}`,
    sourceId: 'n0',
    targetId: `n${i + 1}`,
    label: '',
    memoryIds: []
  }))
}

async function renderPage(): Promise<void> {
  const { Memories } = await import('./Memories')
  render(
    <MemoryRouter>
      <Memories />
    </MemoryRouter>
  )
}

beforeEach(() => {
  memoriesList = [mem('a'), mem('b')]
  graph = bigGraph
  brainGraphProps.length = 0
})

afterEach(() => {
  cleanup()
  vi.resetModules()
})

describe('Memories brain-map preview', () => {
  it('caps the preview to the connected core (not the whole graph)', async () => {
    await renderPage()
    const el = screen.getByTestId('preview-graph')
    expect(el.getAttribute('data-node-count')).toBe(String(DEFAULT_NODE_CAP))
    // Guard against a regression back to the uncapped "text soup".
    expect(el.getAttribute('data-node-count')).not.toBe(String(NODE_TOTAL))
  })

  it('declutters the preview labels (top hubs only), matching the full-screen view', async () => {
    await renderPage()
    expect(screen.getByTestId('preview-graph').getAttribute('data-label-mode')).toBe('declutter')
  })

  it('keeps the preview non-interactive (the full-screen route owns orbit/zoom)', async () => {
    await renderPage()
    expect(screen.getByTestId('preview-graph').getAttribute('data-interactive')).toBe('false')
  })
})
