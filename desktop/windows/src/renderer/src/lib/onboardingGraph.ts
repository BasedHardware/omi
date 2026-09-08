import { useEffect, useState } from 'react'
import type { KnowledgeGraph } from '../../../shared/types'
import { buildUserNode, buildLanguage, buildApps, USER_NODE_ID } from './onboardingGraphModel'

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

// Adopt the persisted graph as-is (no clear). Used when onboarding RESUMES:
// the nodes from the steps already completed are on disk and must survive.
export async function hydrateOnboardingGraph(): Promise<void> {
  current = await window.omi.localGraphLoad()
  emit()
}

/**
 * Graph state for an Onboarding mount.
 *
 * A FRESH start (step 0) wipes the store, mirroring macOS's "clear the graph
 * when onboarding begins". A RESUME must NOT: onboarding re-mounts on every
 * renderer reload (the main process reloads a crashed renderer) and on a
 * quit-and-relaunch, and it comes back at the persisted step. Clearing there
 * deleted the `user` node the name step wrote — and since EVERY edge anchors at
 * `user`, the map lost the user's own node and rendered as unconnected dots.
 * Hydrate instead, and re-add the user node if it is somehow missing so
 * `centerNodeId="user"` always resolves.
 */
export async function initOnboardingGraph(step: number, displayName?: string): Promise<void> {
  if (step <= 0) {
    await resetOnboardingGraph()
    return
  }
  await hydrateOnboardingGraph()
  const name = displayName?.trim()
  if (name && !current.nodes.some((n) => n.id === USER_NODE_ID)) await addUserNode(name)
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
