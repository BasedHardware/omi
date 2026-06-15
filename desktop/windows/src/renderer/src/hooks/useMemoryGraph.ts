import { useEffect, useMemo, useRef, useState } from 'react'
import type { KnowledgeGraph } from '../../../shared/types'
import type { Memory } from './useMemories'
import { useKnowledgeGraph } from './useKnowledgeGraph'
import { mergeGraphs, scopeGraphToMemories } from '../lib/mergeGraphs'
import { USER_NODE_ID } from '../lib/onboardingGraphModel'

const EMPTY: KnowledgeGraph = { nodes: [], edges: [] }

// The Memories brain map is the onboarding graph "and beyond": the persisted
// onboarding graph (you → language → apps, seeded during onboarding so it's
// never empty) with the server-built knowledge graph layered on top, SCOPED to
// the memories you actually have. The center stays the onboarding "you" node
// when present, otherwise the first person node.
//
// The server graph is an account-wide snapshot (every entity it ever extracted),
// so layered whole it shows far more than your memories — phantom nodes from
// deleted memories, plus entities from memories beyond the list. We therefore
// scope it to `memories` via each node's memoryIds, so the map corresponds to
// reality. We also (a) drop the layer entirely when you have zero memories —
// leaving just the app/onboarding floor — and (b) refetch the snapshot whenever
// the memory set changes, so it tracks creates/deletes.
export function useMemoryGraph(memories: Memory[]): {
  graph: KnowledgeGraph
  centerNodeId?: string
} {
  const { graph: kg, refetch } = useKnowledgeGraph()
  const [floor, setFloor] = useState<KnowledgeGraph>(EMPTY)
  const memoryCount = memories.length

  // Load the persisted onboarding graph once. useOnboardingGraph only holds the
  // in-memory graph built during the wizard; on the Memories page (a later
  // session) we must read it back from the onboarding_kg_* tables.
  useEffect(() => {
    let cancelled = false
    window.omi
      .localGraphLoad()
      .then((g) => {
        if (!cancelled) setFloor(g)
      })
      .catch(() => {
        /* no floor available — fall back to the server graph alone */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Refresh the server KG whenever the memory count changes (create/delete) so
  // the map reflects the current memories, not the once-per-session cache.
  const prevCount = useRef(memoryCount)
  useEffect(() => {
    if (prevCount.current !== memoryCount) {
      prevCount.current = memoryCount
      void refetch()
    }
  }, [memoryCount, refetch])

  // Set of the user's current memory ids, used to scope the account-wide server
  // KG down to entities that reference a memory the user actually has.
  const memoryIds = useMemo(() => new Set(memories.map((m) => m.id)), [memories])

  const graph = useMemo(() => {
    if (memoryCount === 0 || !kg) return mergeGraphs(floor, EMPTY)
    // Scope the account-wide KG to entities tied to a current memory. An empty
    // result is CORRECT (not a bug to paper over): it means the server snapshot
    // is stale relative to your memories — the map shows just the floor until a
    // rebuild re-derives the KG. Never fall back to the unscoped KG, or deleted
    // memories' phantom nodes reappear.
    return mergeGraphs(floor, scopeGraphToMemories(kg, memoryIds))
  }, [floor, kg, memoryCount, memoryIds])
  const centerNodeId = graph.nodes.some((n) => n.id === USER_NODE_ID)
    ? USER_NODE_ID
    : graph.nodes.find((n) => n.nodeType === 'person')?.id

  return { graph, centerNodeId }
}
