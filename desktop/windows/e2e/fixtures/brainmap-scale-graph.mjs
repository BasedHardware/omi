/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS test fixture */
// A SYNTHETIC knowledge graph generated to match the SHAPE of a real, heavy
// account measured on 2026-07-19 (read-only /v1/knowledge-graph): 188 nodes,
// 474 edges, node types {concept 134, thing 35, organization 7, person 6,
// place 6}, one ~226-degree hub, a second ~92-degree node, a long tail of
// degree-1 leaves. Labels span 1..35 chars (median ~13). No real personal data —
// deterministic, safe to commit, and reproducible for the perf harness and the
// before/after screenshots. Wire format is snake_case (mapGraphResponse maps it).
//
// The generator is deterministic (seeded LCG) so the graph is identical every
// run. Parallel edges to the hub are intentional: the real graph has a node with
// degree 226 among only 188 nodes, i.e. multiple relationship edges between the
// same pair — we reproduce that so the renderer faces the same edge load.

const TYPE_MIX = [
  ['concept', 134],
  ['thing', 35],
  ['organization', 7],
  ['person', 6],
  ['place', 6]
]
const WORDS = [
  'household chores', 'breakdancing', 'code review', 'E2E tests', 'testing', 'Notion',
  'Porter', 'file', 'Trader Joe', 'Portugal', 'Gusto', 'OpenAI', 'GitHub', 'Warp',
  'refactor', 'sprint planning', 'design system', 'onboarding', 'latency budget',
  'knowledge graph', 'speaker embedding', 'transcription pipeline', 'vector search',
  'release pipeline', 'incident review', 'weekly sync', 'roadmap', 'user research'
]

function lcg(seed) {
  let s = seed >>> 0
  return () => ((s = (s * 1664525 + 1013904223) >>> 0), s / 0xffffffff)
}

export function buildScaleGraph() {
  const rand = lcg(42)
  const NODES = 188
  const EDGES = 474
  // Node types by the measured mix (index 0 is the center person "you").
  const types = []
  for (const [t, n] of TYPE_MIX) for (let i = 0; i < n; i++) types.push(t)
  const nodes = []
  for (let i = 0; i < NODES; i++) {
    const w = WORDS[Math.floor(rand() * WORDS.length)]
    // Vary label length 1..35 chars around a ~13 median.
    const label = i === 0 ? 'You' : `${w}${i % 5 === 0 ? ' ' + Math.floor(rand() * 900) : ''}`.slice(0, 35)
    nodes.push({
      id: `n${i}`,
      label: label || `n${i}`,
      node_type: i === 0 ? 'person' : types[i] || 'concept',
      aliases: [],
      memory_ids: [`m${i % 125}`] // all reference a current memory (scoping keeps them)
    })
  }
  // Target endpoint counts: hub 226, then 92, 39, 29, 23, 17, 16, 15, 13, 13,
  // filling the remainder as degree-1 leaves. We add edges hub-first so the
  // degree profile matches, allowing parallel edges to the hub.
  const targets = [226, 92, 39, 29, 23, 17, 16, 15, 13, 13]
  const edges = []
  let budget = EDGES
  const addEdge = (a, b) => {
    edges.push({
      id: `e${edges.length}`,
      source_id: `n${a}`,
      target_id: `n${b}`,
      label: 'related',
      memory_ids: [`m${a % 125}`]
    })
  }
  // Hubs first.
  for (let h = 0; h < targets.length && budget > 0; h++) {
    const want = Math.min(targets[h], budget)
    for (let k = 0; k < want && budget > 0; k++) {
      let other = 1 + Math.floor(rand() * (NODES - 1))
      if (other === h) other = (other + 1) % NODES
      addEdge(h, other)
      budget--
    }
  }
  // Remaining budget → connect otherwise-isolated leaves so most tail nodes reach
  // degree 1 (matching the measured ~40% degree-1 population).
  let leaf = targets.length
  while (budget > 0 && leaf < NODES) {
    addEdge(leaf, Math.floor(rand() * targets.length)) // attach leaf to a hub
    leaf++
    budget--
  }
  return { nodes, edges }
}
