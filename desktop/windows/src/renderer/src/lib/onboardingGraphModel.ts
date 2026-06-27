import type { OnboardingGraphNode, OnboardingGraphEdge } from '../../../shared/types'

export const USER_NODE_ID = 'user'

// Stable, URL-safe id fragment from a display label.
export function slugId(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export function buildUserNode(name: string): OnboardingGraphNode {
  return { id: USER_NODE_ID, label: name.trim(), nodeType: 'person' }
}

export function buildLanguage(
  code: string,
  label: string
): { nodes: OnboardingGraphNode[]; edges: OnboardingGraphEdge[] } {
  const id = `language_${code}`
  return {
    nodes: [{ id, label, nodeType: 'concept', aliases: [code] }],
    edges: [{ id: `edge_${USER_NODE_ID}_${id}`, sourceId: USER_NODE_ID, targetId: id, label: 'prefers' }]
  }
}

export function buildApps(apps: { name: string }[]): { nodes: OnboardingGraphNode[]; edges: OnboardingGraphEdge[] } {
  const nodes: OnboardingGraphNode[] = []
  const edges: OnboardingGraphEdge[] = []
  const seen = new Set<string>()
  for (const app of apps) {
    const name = app.name.trim()
    if (!name) continue
    const id = `app_${slugId(name)}`
    // A repeated app (scanned from two locations) or two names that slug the same
    // would otherwise emit duplicate node and edge ids. Dedupe like deriveAppNodes.
    if (seen.has(id)) continue
    seen.add(id)
    nodes.push({ id, label: name, nodeType: 'thing' })
    edges.push({ id: `edge_${USER_NODE_ID}_${id}`, sourceId: USER_NODE_ID, targetId: id, label: 'uses' })
  }
  return { nodes, edges }
}
