import {
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum
} from 'd3-force'
import type { KnowledgeGraph, KGNode, KGEdge } from '../../../shared/types'

export type LaidOutNode = KGNode & { x: number; y: number; degree: number }
export type LaidOutGraph = { nodes: LaidOutNode[]; edges: KGEdge[] }

type SimNode = KGNode & SimulationNodeDatum & { degree: number }
type SimLink = { source: string; target: string }

export type LayoutOptions = { iterations?: number; width?: number; height?: number }

// Pure: clones nodes (d3 mutates node objects), runs a fixed number of ticks,
// returns positioned nodes + degree. Deterministic for a given input + options.
export function computeLayout(graph: KnowledgeGraph, opts: LayoutOptions = {}): LaidOutGraph {
  const width = opts.width ?? 800
  const height = opts.height ?? 600
  const iterations = opts.iterations ?? 300

  const degree: Record<string, number> = {}
  for (const n of graph.nodes) degree[n.id] = 0
  for (const e of graph.edges) {
    if (e.sourceId in degree) degree[e.sourceId]++
    if (e.targetId in degree && e.targetId !== e.sourceId) degree[e.targetId]++
  }

  const simNodes: SimNode[] = graph.nodes.map((n) => ({ ...n, degree: degree[n.id] ?? 0 }))
  const simLinks: SimLink[] = graph.edges.map((e) => ({ source: e.sourceId, target: e.targetId }))

  const sim = forceSimulation<SimNode>(simNodes)
    .force('charge', forceManyBody().strength(-180))
    .force('link', forceLink<SimNode, SimLink>(simLinks).id((d) => d.id).distance(70))
    .force('center', forceCenter(width / 2, height / 2))
    .force('collide', forceCollide<SimNode>().radius((d) => 6 + Math.sqrt(d.degree) * 4))
    .stop()

  sim.tick(iterations)

  const nodes: LaidOutNode[] = simNodes.map((n) => ({
    id: n.id,
    label: n.label,
    nodeType: n.nodeType,
    aliases: n.aliases,
    memoryIds: n.memoryIds,
    degree: n.degree,
    x: n.x ?? width / 2,
    y: n.y ?? height / 2
  }))
  return { nodes, edges: graph.edges }
}
