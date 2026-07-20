// @vitest-environment jsdom
import { act } from 'react'
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

let graphLoading = false
vi.mock('../hooks/useMemoryGraph', () => ({
  useMemoryGraph: () => ({
    graph,
    centerNodeId: 'n0',
    rebuild: vi.fn(),
    rebuilding: false,
    loading: graphLoading
  })
}))

// Capture the props the preview passes; render a probe node so hasGraph is true.
// Also expose the latest onPresentable so a test can simulate "a content frame
// painted" (the real signal comes from a WebGL frame, which can't mount in jsdom).
let lastOnPresentable: (() => void) | undefined
vi.mock('../components/graph/LazyBrainGraph', () => ({
  BrainGraph: (props: {
    graph: KnowledgeGraph
    labelMode?: string
    interactive?: boolean
    onPresentable?: () => void
  }) => {
    brainGraphProps.push(props)
    lastOnPresentable = props.onPresentable
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
  // Render on the /memories route: the preview canvas is route-gated (mounts while
  // the Memories route is active), so the default '/' would never mount BrainGraph.
  render(
    <MemoryRouter initialEntries={['/memories']}>
      <Memories />
    </MemoryRouter>
  )
}

beforeEach(() => {
  memoriesList = [mem('a'), mem('b')]
  graph = bigGraph
  graphLoading = false
  brainGraphProps.length = 0
  lastOnPresentable = undefined
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

// The reveal must wait until the graph's data has SETTLED, so the user sees the
// loading indicator until the final graph is ready — never an intermediate frame
// (floor-only, then floor+server-KG) laid out and shown as it loads in. While the
// data is still loading the preview feeds BrainGraph an EMPTY graph (no node frame
// rendered before settle) and keeps the "Building your memory map…" indicator up.
describe('Memories brain-map preview — reveal gate', () => {
  it('holds the loader and renders NO graph nodes while the graph data is still loading', async () => {
    graphLoading = true
    await renderPage()
    // The loading indicator's text is always in the DOM (only its opacity toggles),
    // so assert the actual VISIBLE state: the loader layer is opaque and the graph
    // layer (BrainGraph's wrapper) is faded out.
    const loader = screen.getByText(/Building your memory map/i).closest('div[aria-hidden]')
    expect(loader?.className).toMatch(/opacity-100/)
    const el = screen.getByTestId('preview-graph')
    const graphLayer = el.parentElement
    expect(graphLayer?.className).toMatch(/opacity-0(?!\d)/)
    // …and BrainGraph has been fed the empty graph, so no capped/settled frame has
    // rendered yet (the "no graph frame before the settle signal" guarantee).
    expect(el.getAttribute('data-node-count')).toBe('0')
    expect(brainGraphProps.every((p) => (p.graph?.nodes.length ?? 0) === 0)).toBe(true)
  })

  it('feeds the settled capped graph once the data has loaded', async () => {
    graphLoading = false
    await renderPage()
    const el = screen.getByTestId('preview-graph')
    expect(el.getAttribute('data-node-count')).toBe(String(DEFAULT_NODE_CAP))
  })

  it('keeps the loader up even after data settles, until BrainGraph paints content (onPresentable)', async () => {
    // The load-bearing regression guard: settled data + a mounted, capped-graph
    // canvas is NOT enough to reveal — the WebGL scene has drawn nothing yet, so
    // revealing now would expose the raw warmup (dot / blank / fly-in start). The
    // graph layer must stay faded out until onPresentable fires.
    graphLoading = false
    await renderPage()
    const el = screen.getByTestId('preview-graph')
    // Data is settled and the capped graph is already fed…
    expect(el.getAttribute('data-node-count')).toBe(String(DEFAULT_NODE_CAP))
    // …yet the graph layer is still hidden (no content frame reported).
    expect(el.parentElement?.className).toMatch(/opacity-0(?!\d)/)
    // Simulate BrainGraph painting its first real content frame.
    expect(lastOnPresentable).toBeTypeOf('function')
    act(() => lastOnPresentable!())
    // Now — and only now — the graph layer is revealed.
    expect(screen.getByTestId('preview-graph').parentElement?.className).toMatch(/opacity-100/)
  })
})
