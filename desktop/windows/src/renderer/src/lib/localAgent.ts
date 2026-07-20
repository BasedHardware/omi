import { formatContextBlock } from './localAgentProtocol'
import { orderFloorSections, relationshipItems, type KindedSection } from './floorContext'
import { native } from './native'

async function snapshotSections(): Promise<KindedSection[]> {
  const graph = await native.kgQueryNodes('', 80)
  const nodes = graph.nodes
  const pick = (t: string): string[] => nodes.filter((n) => n.nodeType === t).map((n) => n.summary)
  const out: KindedSection[] = []
  // Background-synthesized overview card (natural-language summary) leads the floor.
  const cards = nodes.filter((n) => n.nodeType === 'card').map((n) => n.summary)
  if (cards.length) out.push({ kind: 'overview', heading: 'Overview', items: cards })
  const tech = pick('technology')
  if (tech.length)
    out.push({ kind: 'tech', heading: 'Programming languages & technologies', items: tech })
  const ent = nodes
    .filter((n) => ['project', 'person', 'org', 'interest'].includes(n.nodeType))
    .map((n) => `${n.label} (${n.nodeType}): ${n.summary}`)
  if (ent.length)
    out.push({ kind: 'entities', heading: 'Projects, people & interests', items: ent })
  // Tier 1: surface the labeled relationships synthesis built (macOS's signature).
  const rels = relationshipItems(nodes, graph.edges)
  if (rels.length) out.push({ kind: 'relationships', heading: 'How they relate', items: rels })
  const folders = pick('file_group')
  if (folders.length)
    out.push({ kind: 'folders', heading: 'Recently active working folders', items: folders })
  const apps = pick('app')
  if (apps.length) out.push({ kind: 'apps', heading: 'Installed apps', items: apps })
  return out
}

export async function gatherLocalContext(userText: string): Promise<string> {
  try {
    const status = await native.kgStatus()
    if (status.nodeCount === 0) {
      const digest = await native.kgFileIndexDigest()
      if (digest.totalFiles === 0) return ''
    }

    const floorP = snapshotSections().catch((error) => {
      console.warn('[context] local graph snapshot failed', error)
      return [] as KindedSection[]
    })
    const floor = await floorP

    const overview = floor
      .filter((s) => s.kind === 'overview')
      .map(({ heading, items }) => ({ heading, items }))
    const rest = floor.filter((s) => s.kind !== 'overview')
    return formatContextBlock([
      ...overview,
      ...orderFloorSections(rest, userText)
    ])
  } catch (error) {
    console.warn('[context] local graph lookup failed', error)
    return ''
  }
}
