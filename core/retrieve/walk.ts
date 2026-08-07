import { compareStrings } from "./order";
import type { SafeEvidenceLineage, SafeSubgraph } from "./index";
import { projectTypedAdjacency, type ProjectedAdjacencyEdge, type TypedAdjacencyKind } from "./adjacency";

export interface WalkHop { relation_kind: TypedAdjacencyKind; from: string; to: string; evidence_span: { evidence_id: string; event_revision_id: string; capture_session_id: string; range: { start: number; end: number }; excerpt: string | null } | null; temporal_window_ms?: number; }
export interface WalkPath { nodes: readonly string[]; hops: readonly WalkHop[]; }
export interface WalkResult { paths: readonly WalkPath[]; node_count: number; edge_count: number; }

const claimId = (node: string): string | null => node.startsWith("claim:") ? node.slice("claim:".length) : null;
const captureId = (node: string): string | null => node.startsWith("capture:") ? node.slice("capture:".length) : null;
const spanOf = (item: SafeEvidenceLineage | undefined): WalkHop["evidence_span"] =>
  item?.range ? { evidence_id: item.evidence_id, event_revision_id: item.event_revision_id, capture_session_id: item.capture_session_id, range: item.range, excerpt: item.excerpt ?? null } : null;

/**
 * The adjacency projection, its per-node fan-out index, and the evidence-span
 * memo: everything a walk needs that depends only on the subgraph and the
 * relation/window selectors, never on the anchor.
 *
 * Building this costs O(claims^2) -- the pairwise when-adjacent scan inside
 * projectTypedAdjacency -- plus a full edge sort. Callers walking many anchors
 * over one subgraph MUST build it once and share it: rebuilding it per anchor is
 * what turned a whole-graph trajectory diff into an unbounded spin.
 */
export interface WalkIndex {
  edges: readonly ProjectedAdjacencyEdge[];
  outgoing: ReadonlyMap<string, readonly ProjectedAdjacencyEdge[]>;
  evidenceSpan: (edge: ProjectedAdjacencyEdge) => WalkHop["evidence_span"];
}

export const buildWalkIndex = (subgraph: SafeSubgraph, request: { relation_kinds?: readonly TypedAdjacencyKind[]; temporal_proximity_window_ms?: number } = {}): WalkIndex => {
  const allowed = new Set(request.relation_kinds ?? ["when-adjacent", "entity-shared", "evidence-lineage", "source-shared", "temporal-proximity"]);
  const edges = projectTypedAdjacency(subgraph, { temporal_proximity_window_ms: request.temporal_proximity_window_ms }).edges.filter((edge) => allowed.has(edge.kind));
  const outgoing = new Map<string, ProjectedAdjacencyEdge[]>();
  // Append in place: rebuilding the bucket array per edge made this O(edges^2) in memmove.
  for (const edge of edges) { const bucket = outgoing.get(edge.from); if (bucket) bucket.push(edge); else outgoing.set(edge.from, [edge]); }
  for (const values of outgoing.values()) values.sort((left, right) => compareStrings(`${left.kind}\u0000${left.to}\u0000${left.from}`, `${right.kind}\u0000${right.to}\u0000${right.from}`));
  const lineage = subgraph.evidence_lineage;
  // A span depends only on the (claim, capture) pair the edge names, so the linear
  // lineage scan is memoized instead of repeated for every hop of every path.
  const fallback = lineage.find((candidate) => candidate.range !== undefined);
  const memo = new Map<string, WalkHop["evidence_span"]>();
  const evidenceSpan = (edge: ProjectedAdjacencyEdge): WalkHop["evidence_span"] => {
    const claim = claimId(edge.from) ?? claimId(edge.to);
    const capture = captureId(edge.from) ?? captureId(edge.to);
    const key = `${claim ?? ""}\u0000${capture ?? ""}`;
    if (memo.has(key)) return memo.get(key)!;
    const span = spanOf(lineage.find((candidate) => (claim ? candidate.claim_revision_id === claim : true) && (capture ? candidate.capture_session_id === capture : true) && candidate.range !== undefined) ?? fallback);
    memo.set(key, span);
    return span;
  };
  return { edges, outgoing, evidenceSpan };
};

/** D46 consumes only a safe projection; no hidden input can influence paths or topology counts. */
export const walk = (subgraph: SafeSubgraph, request: { anchor: string; max_hops: number; relation_kinds?: readonly TypedAdjacencyKind[]; result_cap?: number; temporal_proximity_window_ms?: number; index?: WalkIndex }): WalkResult => {
  if (!Number.isInteger(request.max_hops) || request.max_hops < 0) throw new Error("walk max_hops must be a non-negative integer");
  const resultCap = request.result_cap ?? 100;
  if (!Number.isInteger(resultCap) || resultCap < 0) throw new Error("walk result_cap must be a non-negative integer");
  const { edges, outgoing, evidenceSpan } = request.index ?? buildWalkIndex(subgraph, request);
  const paths: WalkPath[] = [];
  const queue: WalkPath[] = [{ nodes: [request.anchor], hops: [] }];
  // Advance a cursor rather than Array.shift(): the frontier grows into the
  // thousands and shifting re-copies the whole queue on every dequeue.
  let head = 0;
  while (head < queue.length && paths.length < resultCap) {
    const path = queue[head]!; head += 1;
    if (path.hops.length > 0) paths.push(path);
    if (path.hops.length === request.max_hops || paths.length === resultCap) continue;
    for (const edge of outgoing.get(path.nodes[path.nodes.length - 1]!) ?? []) {
      // Everything already queued but not yet dequeued is `queue.length - head`.
      // Every queued entry has at least one hop (only the seed has none, and it
      // is dequeued first), so each remaining dequeue appends exactly one result
      // and the loop stops after `resultCap - paths.length` more of them. Once
      // that many are already pending, anything pushed now lands beyond the last
      // index this loop can ever reach, so not pushing it is output-preserving --
      // and it keeps a high-fan-out node from queueing cap x fan-out paths, each
      // one a fresh copy of the node and hop arrays, only to discard them.
      if (queue.length - head >= resultCap - paths.length) break;
      if (path.nodes.includes(edge.to)) continue;
      const hop: WalkHop = { relation_kind: edge.kind, from: edge.from, to: edge.to, evidence_span: evidenceSpan(edge), ...(edge.kind === "temporal-proximity" ? { temporal_window_ms: edge.temporal_window_ms } : {}) };
      queue.push({ nodes: [...path.nodes, edge.to], hops: [...path.hops, hop] });
    }
  }
  const nodes = new Set<string>([request.anchor]); for (const edge of edges) { nodes.add(edge.from); nodes.add(edge.to); }
  return { paths, node_count: nodes.size, edge_count: edges.length };
};
