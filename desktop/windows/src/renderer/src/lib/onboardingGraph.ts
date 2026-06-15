import { useEffect, useState } from 'react'
import type { KnowledgeGraph } from '../../../shared/types'
import { buildUserNode, buildLanguage, buildApps } from './onboardingGraphModel'

const EMPTY: KnowledgeGraph = { nodes: [], edges: [] }

let current: KnowledgeGraph = EMPTY
const listeners = new Set<(g: KnowledgeGraph) => void>()

function emit(): void {
  for (const l of listeners) l(current)
}

export function getOnboardingGraph(): KnowledgeGraph {
  return current
}

export function subscribeOnboardingGraph(cb: (g: KnowledgeGraph) => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export async function resetOnboardingGraph(): Promise<void> {
  await window.omi.localGraphClear()
  current = EMPTY
  emit()
}

export async function addUserNode(name: string): Promise<void> {
  current = await window.omi.localGraphUpsert([buildUserNode(name)], [])
  emit()
}

export async function addLanguageNode(code: string, label: string): Promise<void> {
  const { nodes, edges } = buildLanguage(code, label)
  current = await window.omi.localGraphUpsert(nodes, edges)
  emit()
}

export async function addAppNodes(apps: { name: string }[]): Promise<void> {
  const { nodes, edges } = buildApps(apps)
  if (nodes.length === 0) return
  current = await window.omi.localGraphUpsert(nodes, edges)
  emit()
}

// Live graph for React consumers. Re-renders on every store change.
export function useOnboardingGraph(): KnowledgeGraph {
  const [graph, setGraph] = useState<KnowledgeGraph>(current)
  useEffect(() => subscribeOnboardingGraph(setGraph), [])
  return graph
}
