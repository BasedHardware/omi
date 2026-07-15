// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, cleanup, screen, fireEvent } from '@testing-library/react'
import type { KnowledgeGraph } from '../../../../shared/types'

// The real BrainGraph needs a WebGL context (unavailable in jsdom), so stub the
// lazy wrapper. The stub records the props the viewer passes so we can assert the
// full-screen scene is mounted INTERACTIVE (orbit/pan/zoom) with the graph data.
vi.mock('./LazyBrainGraph', () => ({
  BrainGraph: (props: { interactive?: boolean; graph: KnowledgeGraph }) => (
    <div
      data-testid="brain-graph"
      data-interactive={String(!!props.interactive)}
      data-node-count={props.graph.nodes.length}
    />
  )
}))

import { KnowledgeGraphViewer } from './KnowledgeGraphViewer'

afterEach(cleanup)

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

  it('never introduces off-brand purple chrome', () => {
    const { container } = render(<KnowledgeGraphViewer graph={POPULATED} onClose={() => {}} />)
    expect(container.innerHTML).not.toMatch(/purple|violet/i)
  })
})
