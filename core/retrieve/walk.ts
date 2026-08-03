import type { SafeEvidenceLineage, SafeSubgraph } from "./index";
import { projectTypedAdjacency, type ProjectedAdjacencyEdge, type TypedAdjacencyKind } from "./adjacency";

export interface WalkHop { relation_kind: TypedAdjacencyKind; from: string; to: string; evidence_span: { evidence_id: string; event_revision_id: string; capture_session_id: string; range: { start: number; end: number }; excerpt: string | null } | null; temporal_window_ms?: number; }
export interface WalkPath { nodes: readonly string[]; hops: readonly WalkHop[]; }
export interface WalkResult { paths: readonly WalkPath[]; node_count: number; edge_count: number; }

const claimId = (node: string): string | null => node.startsWith("claim:") ? node.slice("claim:".length) : null;
const captureId = (node: string): string | null => node.startsWith("capture:") ? node.slice("capture:".length) : null;
const evidenceFor = (edge: ProjectedAdjacencyEdge, lineage: readonly SafeEvidenceLineage[]): WalkHop["evidence_span"] => {
  const claim = claimId(edge.from) ?? claimId(edge.to);
  const capture = captureId(edge.from) ?? captureId(edge.to);
  const item = lineage.find((candidate) => (claim ? candidate.claim_revision_id === claim : true) && (capture ? candidate.capture_session_id === capture : true) && candidate.range !== undefined) ?? lineage.find((candidate) => candidate.range !== undefined);
  return item?.range ? { evidence_id: item.evidence_id, event_revision_id: item.event_revision_id, capture_session_id: item.capture_session_id, range: item.range, excerpt: item.excerpt ?? null } : null;
};

/** D46 consumes only a safe projection; no hidden input can influence paths or topology counts. */
export const walk = (subgraph: SafeSubgraph, request: { anchor: string; max_hops: number; relation_kinds?: readonly TypedAdjacencyKind[]; result_cap?: number; temporal_proximity_window_ms?: number }): WalkResult => {
  if (!Number.isInteger(request.max_hops) || request.max_hops < 0) throw new Error("walk max_hops must be a non-negative integer");
  const resultCap = request.result_cap ?? 100;
  if (!Number.isInteger(resultCap) || resultCap < 0) throw new Error("walk result_cap must be a non-negative integer");
  const allowed = new Set(request.relation_kinds ?? ["when-adjacent", "entity-shared", "evidence-lineage", "source-shared", "temporal-proximity"]);
  const edges = projectTypedAdjacency(subgraph, { temporal_proximity_window_ms: request.temporal_proximity_window_ms }).edges.filter((edge) => allowed.has(edge.kind));
  const outgoing = new Map<string, ProjectedAdjacencyEdge[]>();
  for (const edge of edges) outgoing.set(edge.from, [...(outgoing.get(edge.from) ?? []), edge]);
  for (const values of outgoing.values()) values.sort((left, right) => `${left.kind}\u0000${left.to}\u0000${left.from}`.localeCompare(`${right.kind}\u0000${right.to}\u0000${right.from}`));
  const paths: WalkPath[] = [];
  const queue: WalkPath[] = [{ nodes: [request.anchor], hops: [] }];
  while (queue.length && paths.length < resultCap) {
    const path = queue.shift()!;
    if (path.hops.length > 0) paths.push(path);
    if (path.hops.length === request.max_hops || paths.length === resultCap) continue;
    for (const edge of outgoing.get(path.nodes[path.nodes.length - 1]!) ?? []) {
      if (path.nodes.includes(edge.to)) continue;
      const hop: WalkHop = { relation_kind: edge.kind, from: edge.from, to: edge.to, evidence_span: evidenceFor(edge, subgraph.evidence_lineage), ...(edge.kind === "temporal-proximity" ? { temporal_window_ms: edge.temporal_window_ms } : {}) };
      queue.push({ nodes: [...path.nodes, edge.to], hops: [...path.hops, hop] });
    }
  }
  const nodes = new Set<string>([request.anchor]); for (const edge of edges) { nodes.add(edge.from); nodes.add(edge.to); }
  return { paths, node_count: nodes.size, edge_count: edges.length };
};
