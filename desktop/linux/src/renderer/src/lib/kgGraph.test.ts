import { describe, it, expect } from 'vitest'
import { parseGraphResponse, mergeGraph } from './kgGraph'
import type { LocalKGNode } from '../../../shared/types'

describe('parseGraphResponse', () => {
  it('parses fenced JSON and keeps valid nodes/edges', () => {
    const content =
      '```json\n{"nodes":[{"label":"omi-windows","type":"project","summary":"Electron app"}],' +
      '"edges":[{"source":"omi-windows","target":"TypeScript","label":"written in"}]}\n```'
    const g = parseGraphResponse(content)
    expect(g.nodes).toEqual([
      { label: 'omi-windows', nodeType: 'project', summary: 'Electron app' }
    ])
    expect(g.edges).toEqual([
      { sourceLabel: 'omi-windows', targetLabel: 'TypeScript', label: 'written in' }
    ])
  })

  it('drops malformed nodes (bad type, missing label) and edges', () => {
    const content =
      '{"nodes":[{"label":"X","type":"banana","summary":"s"},{"type":"project","summary":"s"},' +
      '{"label":"Good","type":"interest","summary":"s"}],"edges":[{"source":"Good"}]}'
    const g = parseGraphResponse(content)
    expect(g.nodes).toEqual([{ label: 'Good', nodeType: 'interest', summary: 's' }])
    expect(g.edges).toEqual([])
  })

  it('returns empty graph on non-JSON', () => {
    expect(parseGraphResponse('sorry, I cannot help')).toEqual({ nodes: [], edges: [] })
  })

  it('captures aliases and sourceRefs provenance when present', () => {
    const content =
      '{"nodes":[{"label":"Omi","type":"project","summary":"s",' +
      '"aliases":["omi-windows",""],"sourceRefs":["C:/x","I build Omi"]}],"edges":[]}'
    const g = parseGraphResponse(content)
    expect(g.nodes[0]).toEqual({
      label: 'Omi',
      nodeType: 'project',
      summary: 's',
      aliases: ['omi-windows'], // blank dropped
      sourceRefs: ['C:/x', 'I build Omi']
    })
  })
})

describe('mergeGraph', () => {
  const now = 5
  const tech: LocalKGNode = {
    id: 'typescript:technology',
    label: 'TypeScript',
    nodeType: 'technology',
    summary: 'TS',
    source: 'derived',
    createdAt: now
  }

  it('keeps deterministic nodes, adds LLM nodes, resolves edges by label', () => {
    const parsed = {
      nodes: [{ label: 'omi-windows', nodeType: 'project' as const, summary: 'app' }],
      edges: [{ sourceLabel: 'omi-windows', targetLabel: 'TypeScript', label: 'written in' }]
    }
    const g = mergeGraph([tech], parsed, now)
    expect(g.nodes.map((n) => n.id).sort()).toEqual(['omi-windows:project', 'typescript:technology'])
    expect(g.nodes.find((n) => n.id === 'omi-windows:project')!.source).toBe('memories')
    expect(g.edges).toHaveLength(1)
    expect(g.edges[0]).toMatchObject({
      sourceId: 'omi-windows:project',
      targetId: 'typescript:technology',
      label: 'written in'
    })
  })

  it('deterministic node wins over an LLM node with the same id', () => {
    const parsed = {
      nodes: [{ label: 'TypeScript', nodeType: 'technology' as const, summary: 'LLM version' }],
      edges: []
    }
    const g = mergeGraph([tech], parsed, now)
    expect(g.nodes).toHaveLength(1)
    expect(g.nodes[0].summary).toBe('TS') // deterministic kept
  })

  it('drops edges with unresolved endpoints and self-edges', () => {
    const parsed = {
      nodes: [{ label: 'omi-windows', nodeType: 'project' as const, summary: 'app' }],
      edges: [
        { sourceLabel: 'omi-windows', targetLabel: 'Ghost', label: 'uses' },
        { sourceLabel: 'omi-windows', targetLabel: 'omi-windows', label: 'self' }
      ]
    }
    const g = mergeGraph([], parsed, now)
    expect(g.edges).toEqual([])
  })
})
