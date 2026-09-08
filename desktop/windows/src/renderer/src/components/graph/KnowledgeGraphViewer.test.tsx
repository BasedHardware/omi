// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, screen, fireEvent } from '@testing-library/react'
import type { KnowledgeGraph } from '../../../../shared/types'

// The real BrainGraph needs a WebGL context (unavailable in jsdom), so stub the
// lazy wrapper. The stub records the props the viewer passes so we can assert the
// full-screen scene is mounted INTERACTIVE (orbit/pan/zoom) with the graph data.
vi.mock('./LazyBrainGraph', () => ({
  BrainGraph: (props: { interactive?: boolean; graph: KnowledgeGraph; labelMode?: string }) => (
    <div
      data-testid="brain-graph"
      data-interactive={String(!!props.interactive)}
      data-node-count={props.graph.nodes.length}
      data-label-mode={props.labelMode ?? 'all'}
    />
  )
}))

import { KnowledgeGraphViewer } from './KnowledgeGraphViewer'
import { DEFAULT_NODE_CAP } from '../../lib/graphDisplay'

afterEach(cleanup)

// A graph larger than the default cap, so the density control engages. One hub
// (n0) connected to every other node guarantees a stable importance ranking.
const big: KnowledgeGraph = {
  nodes: Array.from({ length: DEFAULT_NODE_CAP + 40 }, (_, i) => ({
    id: `n${i}`,
    label: `n${i}`,
    nodeType: 'concept',
    aliases: [],
    memoryIds: []
  })),
  edges: Array.from({ length: DEFAULT_NODE_CAP + 39 }, (_, i) => ({
    id: `e${i}`,
    sourceId: 'n0',
    targetId: `n${i + 1}`,
    label: '',
    memoryIds: []
  }))
}

const POPULATED: KnowledgeGraph = {
  nodes: [
    { id: 'you', label: 'You', nodeType: 'person', aliases: [], memoryIds: [] },
    { id: 'omi', label: 'Omi', nodeType: 'organization', aliases: [], memoryIds: [] }
  ],
  edges: [{ id: 'e1', sourceId: 'you', targetId: 'omi', label: 'uses', memoryIds: [] }]
}

const EMPTY: KnowledgeGraph = { nodes: [], edges: [] }

describe('KnowledgeGraphViewer', () => {
  it('renders the graph full-screen and INTERACTIVE from the hook data (core path)', () => {
    render(<KnowledgeGraphViewer graph={POPULATED} centerNodeId="you" onClose={() => {}} />)
    const canvas = screen.getByTestId('brain-graph')
    // Interactive => OrbitControls (pan/zoom/rotate). This is the whole point of
    // the full-screen route vs the non-interactive inline Memories card.
    expect(canvas.getAttribute('data-interactive')).toBe('true')
    expect(canvas.getAttribute('data-node-count')).toBe('2')
    // Reachable back affordance so the route is never a dead end.
    expect(screen.getByRole('button', { name: 'Back' })).toBeTruthy()
  })

  it('shows a sensible empty state (not a blank canvas) when there are no nodes', () => {
    render(<KnowledgeGraphViewer graph={EMPTY} onClose={() => {}} />)
    // No WebGL canvas is mounted for an empty graph...
    expect(screen.queryByTestId('brain-graph')).toBeNull()
    // ...instead a human-readable empty state is shown.
    expect(screen.getByText('Your brain map is empty')).toBeTruthy()
  })

  it('calls onClose from the back button', () => {
    const onClose = vi.fn()
    render(<KnowledgeGraphViewer graph={POPULATED} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('offers a rebuild affordance that invokes the passed rebuild()', () => {
    const rebuild = vi.fn()
    render(<KnowledgeGraphViewer graph={POPULATED} onClose={() => {}} rebuild={rebuild} />)
    fireEvent.click(screen.getByRole('button', { name: /rebuild/i }))
    expect(rebuild).toHaveBeenCalledTimes(1)
  })

  it('caps a large graph by default and reveals the full set via "Show all"', () => {
    render(<KnowledgeGraphViewer graph={big} centerNodeId="n0" onClose={() => {}} />)
    // Default view is capped to the connected core, not the whole graph.
    expect(screen.getByTestId('brain-graph').getAttribute('data-node-count')).toBe(
      String(DEFAULT_NODE_CAP)
    )
    // The escape hatch is present and names the full count so nothing is hidden
    // without a way to reach it.
    const showAll = screen.getByRole('button', { name: `Show all ${big.nodes.length}` })
    fireEvent.click(showAll)
    // Now the full graph is rendered, and the control flips to collapse again.
    expect(screen.getByTestId('brain-graph').getAttribute('data-node-count')).toBe(
      String(big.nodes.length)
    )
    expect(screen.getByRole('button', { name: `Show key ${DEFAULT_NODE_CAP}` })).toBeTruthy()
  })

  it('does not show the density control when the graph is under the cap', () => {
    render(<KnowledgeGraphViewer graph={POPULATED} onClose={() => {}} />)
    expect(screen.queryByRole('button', { name: /show all/i })).toBeNull()
  })

  it('defaults to declutter labels and toggles to all labels via "Show all labels"', () => {
    render(<KnowledgeGraphViewer graph={big} centerNodeId="n0" onClose={() => {}} />)
    // Resting look: decluttered (only the top hubs stay named), same as the card.
    expect(screen.getByTestId('brain-graph').getAttribute('data-label-mode')).toBe('declutter')
    const toggle = screen.getByRole('button', { name: 'Show all labels' })
    fireEvent.click(toggle)
    // Now every visible node is named, and the control flips to collapse again.
    expect(screen.getByTestId('brain-graph').getAttribute('data-label-mode')).toBe('all')
    expect(screen.getByRole('button', { name: 'Show key labels' })).toBeTruthy()
  })

  it('composes the labels toggle with the node toggle independently (4 states)', () => {
    render(<KnowledgeGraphViewer graph={big} centerNodeId="n0" onClose={() => {}} />)
    const canvas = (): HTMLElement => screen.getByTestId('brain-graph')
    const nodeToggle = (): HTMLElement =>
      screen.getByRole('button', { name: /^Show (all \d+|key \d+)$/ })
    const labelToggle = (): HTMLElement =>
      screen.getByRole('button', { name: /^Show (all|key) labels$/ })

    // State 1: key nodes + declutter labels (defaults).
    expect(canvas().getAttribute('data-node-count')).toBe(String(DEFAULT_NODE_CAP))
    expect(canvas().getAttribute('data-label-mode')).toBe('declutter')

    // State 2: key nodes + all labels — flipping labels leaves the node set alone.
    fireEvent.click(labelToggle())
    expect(canvas().getAttribute('data-node-count')).toBe(String(DEFAULT_NODE_CAP))
    expect(canvas().getAttribute('data-label-mode')).toBe('all')

    // State 3: all nodes + all labels — flipping nodes leaves the label mode alone.
    fireEvent.click(nodeToggle())
    expect(canvas().getAttribute('data-node-count')).toBe(String(big.nodes.length))
    expect(canvas().getAttribute('data-label-mode')).toBe('all')

    // State 4: all nodes + declutter labels.
    fireEvent.click(labelToggle())
    expect(canvas().getAttribute('data-node-count')).toBe(String(big.nodes.length))
    expect(canvas().getAttribute('data-label-mode')).toBe('declutter')
  })

  it('does not show the labels control when few enough nodes are visible', () => {
    render(<KnowledgeGraphViewer graph={POPULATED} onClose={() => {}} />)
    expect(screen.queryByRole('button', { name: /labels/i })).toBeNull()
  })

  it('never introduces off-brand purple chrome', () => {
    const { container } = render(<KnowledgeGraphViewer graph={POPULATED} onClose={() => {}} />)
    expect(container.innerHTML).not.toMatch(/purple|violet/i)
  })
})
