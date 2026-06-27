import { extractJSONObject } from './extractJson'
import { nodeId, slugify } from './kgTech'
import type {
  LocalKGEdge,
  LocalKGNode,
  LocalKGNodeType,
  LocalKnowledgeGraph
} from '../../../shared/types'

const VALID_TYPES: LocalKGNodeType[] = [
  'project',
  'app',
  'technology',
  'person',
  'org',
  'interest',
  'file_group'
]

// Intermediate shapes: the LLM emits nodes typed by `type` and edges that
// reference nodes by label. mergeGraph turns these into id-keyed LocalKG*.
export type ParsedNode = {
  label: string
  nodeType: LocalKGNodeType
  summary: string
  aliases?: string[]
  sourceRefs?: string[]
}
export type ParsedEdge = { sourceLabel: string; targetLabel: string; label: string }
export type ParsedGraph = { nodes: ParsedNode[]; edges: ParsedEdge[] }

// Keep only the string entries of a possibly-mixed array; undefined if none.
function stringArray(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined
  const out = v.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
  return out.length ? out : undefined
}

export function parseGraphResponse(content: string): ParsedGraph {
  let obj: unknown
  try {
    obj = JSON.parse(extractJSONObject(content))
  } catch {
    return { nodes: [], edges: [] }
  }
  const o = obj as { nodes?: unknown; edges?: unknown }
  const nodes: ParsedNode[] = Array.isArray(o.nodes)
    ? o.nodes.flatMap((raw) => {
        const x = raw as {
          label?: unknown
          type?: unknown
          summary?: unknown
          aliases?: unknown
          sourceRefs?: unknown
        }
        const label = typeof x.label === 'string' ? x.label.trim() : ''
        const type = typeof x.type === 'string' ? x.type.trim() : ''
        const summary = typeof x.summary === 'string' ? x.summary.trim() : ''
        if (!label || !VALID_TYPES.includes(type as LocalKGNodeType)) return []
        const aliases = stringArray(x.aliases)
        const sourceRefs = stringArray(x.sourceRefs)
        return [
          {
            label,
            nodeType: type as LocalKGNodeType,
            summary,
            ...(aliases ? { aliases } : {}),
            ...(sourceRefs ? { sourceRefs } : {})
          }
        ]
      })
    : []
  const edges: ParsedEdge[] = Array.isArray(o.edges)
    ? o.edges.flatMap((raw) => {
        const x = raw as { source?: unknown; target?: unknown; label?: unknown }
        const sourceLabel = typeof x.source === 'string' ? x.source.trim() : ''
        const targetLabel = typeof x.target === 'string' ? x.target.trim() : ''
        const label = typeof x.label === 'string' ? x.label.trim() : ''
        if (!sourceLabel || !targetLabel) return []
        return [{ sourceLabel, targetLabel, label: label || 'related to' }]
      })
    : []
  return { nodes, edges }
}

// Combine deterministic nodes (technology/app) with LLM-synthesized nodes
// (deterministic wins on id collision), then resolve LLM edges from labels to
// node ids, dropping dangling and self-edges.
export function mergeGraph(
  deterministic: LocalKGNode[],
  parsed: ParsedGraph,
  now: number
): LocalKnowledgeGraph {
  const byId = new Map<string, LocalKGNode>()
  for (const n of deterministic) byId.set(n.id, n)
  for (const pn of parsed.nodes) {
    const id = nodeId(pn.label, pn.nodeType)
    if (byId.has(id)) continue
    byId.set(id, {
      id,
      label: pn.label,
      nodeType: pn.nodeType,
      summary: pn.summary,
      source: 'memories',
      createdAt: now,
      ...(pn.aliases ? { aliases: pn.aliases } : {}),
      ...(pn.sourceRefs ? { sourceRefs: pn.sourceRefs } : {})
    })
  }

  // Edges reference nodes by label, so resolve label -> id. Keyed by lowercase
  // label only; if two nodes share a label across types, last-writer-wins. The
  // LLM emits no type on edge endpoints, so a richer key would not help here.
  const labelToId = new Map<string, string>()
  for (const n of byId.values()) labelToId.set(n.label.toLowerCase(), n.id)

  const edges: LocalKGEdge[] = []
  const seen = new Set<string>()
  for (const pe of parsed.edges) {
    const sourceId = labelToId.get(pe.sourceLabel.toLowerCase())
    const targetId = labelToId.get(pe.targetLabel.toLowerCase())
    if (!sourceId || !targetId || sourceId === targetId) continue
    const id = `${sourceId}->${targetId}:${slugify(pe.label)}`
    if (seen.has(id)) continue
    seen.add(id)
    edges.push({ id, sourceId, targetId, label: pe.label, createdAt: now })
  }
  return { nodes: [...byId.values()], edges }
}
