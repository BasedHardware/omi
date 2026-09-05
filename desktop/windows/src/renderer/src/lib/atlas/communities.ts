// Louvain community detection over the relatedness graph.
//
// Ported from macOS `MemoryAtlasForceLayout.swift:790-915`. This is what turns a
// hairball into regions: the map cannot draw a named territory until it knows
// which entities belong together, and "belong together" here means densely
// connected to each other relative to the rest of the graph.
//
// Determinism, as everywhere in this package: candidate groups are walked in
// sorted order and a move needs to beat the incumbent by more than a tolerance,
// so a tie leaves a node exactly where it was. Without both, the same graph
// produces different regions on different runs and the map appears to reorganise
// itself for no reason.

/** Weighted undirected adjacency: `adjacency[i]` maps a neighbour index to a weight. */
type Adjacency = Array<Map<number, number>>

/** Levels of coarsening attempted before giving up. */
export const LOUVAIN_LEVELS = 10
/** Local-move sweeps per level. */
export const LOUVAIN_ROUNDS = 20
/** A candidate must beat the incumbent by more than this to win the node. */
export const LOUVAIN_EPSILON = 1e-12

/**
 * One pass of local moving: repeatedly move each node to the neighbouring
 * community that most improves modularity, until nothing moves or the sweep
 * budget runs out. Returns a dense, first-seen relabelling.
 */
export function mergeByModularity(
  adjacency: Adjacency,
  selfLoops: number[],
  rounds = LOUVAIN_ROUNDS
): number[] {
  const n = adjacency.length
  const community = Array.from({ length: n }, (_v, i) => i)
  if (n === 0) return community

  const degree = adjacency.map((neighbours, i) => {
    let total = 0
    for (const weight of neighbours.values()) total += weight
    return total + 2 * (selfLoops[i] ?? 0)
  })
  const twiceTotal = degree.reduce((sum, d) => sum + d, 0)
  // A graph with no weight has no communities to find; the identity partition is
  // the honest answer rather than an arbitrary grouping.
  if (twiceTotal <= 0) return community

  const totalDegree = [...degree]

  for (let round = 0; round < rounds; round += 1) {
    let moved = false
    for (let i = 0; i < n; i += 1) {
      const current = community[i]
      // Weight from i into each candidate community.
      // Self-edges are excluded where the adjacency is BUILT (both in
      // detectCommunities and in the collapse below), so there is no second
      // check here: two guards for one invariant means neither can be shown to
      // matter on its own.
      const shared = new Map<number, number>()
      for (const [j, weight] of adjacency[i]) {
        shared.set(community[j], (shared.get(community[j]) ?? 0) + weight)
      }

      // Remove i from its own community before scoring, so it is not compared
      // against a total that still includes itself.
      totalDegree[current] -= degree[i]
      const currentShared = shared.get(current) ?? 0
      let bestCommunity = current
      let bestGain = currentShared - (totalDegree[current] * degree[i]) / twiceTotal

      for (const candidate of [...shared.keys()].sort((x, y) => x - y)) {
        if (candidate === current) continue
        const gain =
          (shared.get(candidate) ?? 0) - (totalDegree[candidate] * degree[i]) / twiceTotal
        // Strictly greater by more than the tolerance: an equal-scoring
        // candidate must not be able to pull the node, or the partition
        // oscillates and never settles.
        if (gain > bestGain + LOUVAIN_EPSILON) {
          bestGain = gain
          bestCommunity = candidate
        }
      }

      totalDegree[bestCommunity] += degree[i]
      if (bestCommunity !== current) {
        community[i] = bestCommunity
        moved = true
      }
    }
    if (!moved) break
  }

  return denseRelabel(community)
}

/** Renumbers labels to 0..k-1 in first-seen order, so the ids a level produces
 *  do not depend on how large the original index space was. */
export function denseRelabel(labels: number[]): number[] {
  const seen = new Map<number, number>()
  return labels.map((label) => {
    const existing = seen.get(label)
    if (existing !== undefined) return existing
    const next = seen.size
    seen.set(label, next)
    return next
  })
}

/**
 * Assigns every id a community.
 *
 * `neighbours` is the weighted adjacency from relatedness.ts. Ids with no
 * neighbours still get a community of their own, so nothing is silently lost
 * between here and the map.
 */
export function detectCommunities(
  ids: string[],
  neighbours: Map<string, Array<{ id: string; weight: number }>>,
  levels = LOUVAIN_LEVELS
): Map<string, number> {
  const indexOf = new Map<string, number>()
  ids.forEach((id, i) => indexOf.set(id, i))

  let adjacency: Adjacency = ids.map(() => new Map<number, number>())
  for (let i = 0; i < ids.length; i += 1) {
    for (const neighbour of neighbours.get(ids[i]) ?? []) {
      const j = indexOf.get(neighbour.id)
      // Self-edges carry no information about which group a node belongs to.
      if (j === undefined || j === i) continue
      adjacency[i].set(j, (adjacency[i].get(j) ?? 0) + neighbour.weight)
    }
  }
  let selfLoops = new Array<number>(ids.length).fill(0)
  // Membership of the ORIGINAL nodes, rewritten at each level of coarsening.
  let membership = ids.map((_id, i) => i)

  for (let level = 0; level < levels; level += 1) {
    const groups = mergeByModularity(adjacency, selfLoops)
    const groupCount = new Set(groups).size
    // Nothing merged, so no coarser level can either.
    if (groupCount >= adjacency.length) break

    membership = membership.map((g) => groups[g])

    const collapsed: Adjacency = Array.from({ length: groupCount }, () => new Map<number, number>())
    const collapsedSelf = new Array<number>(groupCount).fill(0)
    for (let i = 0; i < adjacency.length; i += 1) {
      collapsedSelf[groups[i]] += selfLoops[i]
      for (const [j, weight] of adjacency[i]) {
        if (groups[i] === groups[j]) {
          // Each undirected edge is seen once from each end, so half of it lands
          // in the group's self-loop from each side.
          collapsedSelf[groups[i]] += weight / 2
        } else {
          const key = groups[j]
          collapsed[groups[i]].set(key, (collapsed[groups[i]].get(key) ?? 0) + weight)
        }
      }
    }
    adjacency = collapsed
    selfLoops = collapsedSelf
  }

  const out = new Map<string, number>()
  const dense = denseRelabel(membership)
  ids.forEach((id, i) => out.set(id, dense[i]))
  return out
}

/** Members per community, each list in sorted id order. */
export function membersByCommunity(membership: Map<string, number>): Map<number, string[]> {
  const out = new Map<number, string[]>()
  for (const id of [...membership.keys()].sort()) {
    const group = membership.get(id) as number
    const existing = out.get(group)
    if (existing === undefined) out.set(group, [id])
    else existing.push(id)
  }
  return out
}
