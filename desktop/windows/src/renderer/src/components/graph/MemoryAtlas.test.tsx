// @vitest-environment jsdom
//
// The atlas draws to a 2D canvas, which jsdom does not implement, so the context
// is a recording stub. That is enough to assert what matters here: that the map
// is built from the graph and that the right things reach the canvas in the
// right order - regions under entities, captions over both.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, screen, fireEvent } from '@testing-library/react'
import type { KGEdge, KGNode, KnowledgeGraph } from '../../../../shared/types'

const calls: Array<{ op: string; args: unknown[] }> = []

const stubContext = (): unknown => {
  const record =
    (op: string) =>
    (...args: unknown[]): void => {
      calls.push({ op, args })
    }
  return {
    setTransform: record('setTransform'),
    clearRect: record('clearRect'),
    beginPath: record('beginPath'),
    moveTo: record('moveTo'),
    lineTo: record('lineTo'),
    closePath: record('closePath'),
    arc: record('arc'),
    fill: record('fill'),
    stroke: record('stroke'),
    fillText: record('fillText'),
    set fillStyle(v: unknown) {
      calls.push({ op: 'fillStyle', args: [v] })
    },
    set strokeStyle(v: unknown) {
      calls.push({ op: 'strokeStyle', args: [v] })
    },
    set lineWidth(v: unknown) {
      calls.push({ op: 'lineWidth', args: [v] })
    },
    set font(v: unknown) {
      calls.push({ op: 'font', args: [v] })
    },
    set textAlign(v: unknown) {
      calls.push({ op: 'textAlign', args: [v] })
    },
    set textBaseline(v: unknown) {
      calls.push({ op: 'textBaseline', args: [v] })
    }
  }
}

const { MemoryAtlas } = await import('./MemoryAtlas')

const node = (id: string, label: string, memoryIds: string[] = []): KGNode => ({
  id,
  label,
  nodeType: 'topic',
  aliases: [],
  memoryIds
})
const edge = (a: string, b: string, memoryIds: string[] = []): KGEdge => ({
  id: `${a}-${b}`,
  sourceId: a,
  targetId: b,
  label: '',
  memoryIds
})

const threeWorlds = (): KnowledgeGraph => {
  const nodes: KGNode[] = []
  const edges: KGEdge[] = []
  for (const [prefix, hub] of [
    ['w', 'Acme'],
    ['h', 'Lease'],
    ['t', 'Travel']
  ] as const) {
    for (let i = 0; i < 10; i += 1) {
      nodes.push(node(`${prefix}${i}`, i === 0 ? hub : `${prefix} thing ${i}`, [`${prefix}m`]))
    }
    for (let i = 0; i < 10; i += 1) {
      for (let j = i + 1; j < 10; j += 1) {
        edges.push(edge(`${prefix}${i}`, `${prefix}${j}`, [`${prefix}m`]))
      }
    }
  }
  edges.push(edge('w0', 'h0'))
  edges.push(edge('h0', 't0'))
  return { nodes, edges }
}

beforeEach(() => {
  calls.length = 0
  HTMLCanvasElement.prototype.getContext = vi.fn(stubContext) as never
  // jsdom reports every element as zero-sized; the atlas skips drawing at zero,
  // so the canvas is given a size the way a real layout would.
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientWidth', {
    configurable: true,
    value: 800
  })
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientHeight', {
    configurable: true,
    value: 600
  })
})

afterEach(() => cleanup())

const textDrawn = (): string[] =>
  calls.filter((c) => c.op === 'fillText').map((c) => String(c.args[0]))

describe('MemoryAtlas', () => {
  it('names the regions it found in its accessible label', () => {
    render(<MemoryAtlas graph={threeWorlds()} />)
    expect(screen.getByRole('img', { name: 'Memory atlas with 3 regions' })).toBeTruthy()
  })

  it('draws a caption for every region, in upper case', () => {
    render(<MemoryAtlas graph={threeWorlds()} />)
    const text = textDrawn()
    // Uppercased at draw time only; the stored caption keeps its own casing so
    // nothing downstream inherits the shouting.
    expect(text).toContain('ACME')
    expect(text).toContain('LEASE')
    expect(text).toContain('TRAVEL')
  })

  it('fills regions with the even-odd rule so an enclave stays a hole', () => {
    render(<MemoryAtlas graph={threeWorlds()} />)
    expect(calls.some((c) => c.op === 'fill' && c.args[0] === 'evenodd')).toBe(true)
  })

  it('draws regions first and captions last', () => {
    render(<MemoryAtlas graph={threeWorlds()} />)
    const firstFill = calls.findIndex((c) => c.op === 'fill' && c.args[0] === 'evenodd')
    const firstDot = calls.findIndex((c) => c.op === 'arc')
    const lastCaption = calls.map((c) => c.op).lastIndexOf('fillText')
    // A caption under its own region is unreadable, and an entity under a
    // region fill disappears.
    expect(firstFill).toBeLessThan(firstDot)
    expect(lastCaption).toBeGreaterThan(firstDot)
  })

  it('renders an empty graph without drawing anything', () => {
    render(<MemoryAtlas graph={{ nodes: [], edges: [] }} />)
    expect(screen.getByRole('img', { name: 'Memory atlas with 0 regions' })).toBeTruthy()
    expect(textDrawn()).toEqual([])
  })

  it('hides nothing: every entity reaches the canvas', () => {
    render(<MemoryAtlas graph={threeWorlds()} />)
    // The point of the map is that it does not solve legibility by dropping
    // nodes the way the graph view does.
    expect(calls.filter((c) => c.op === 'arc').length).toBe(30)
  })

  it('redraws when the camera moves', () => {
    render(<MemoryAtlas graph={threeWorlds()} />)
    const before = calls.length
    fireEvent.wheel(screen.getByRole('img'), { deltaY: -100 })
    expect(calls.length).toBeGreaterThan(before)
  })
})
