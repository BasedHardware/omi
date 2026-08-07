import { compareStrings } from "./order";
import type { PersistedValidTime } from "../schema";
import type { CommittedClaim, SafeSubgraph } from "./index";

/** The D13 topology labels plus an ordered, non-identity temporal connector. */
export type TypedAdjacencyKind = "when-adjacent" | "entity-shared" | "evidence-lineage" | "source-shared" | "temporal-proximity";
export interface TypedAdjacencyEdge { kind: Exclude<TypedAdjacencyKind, "temporal-proximity">; from: string; to: string; }
/** This distinct type cannot be mistaken for identity support: proximity asserts only capture ordering. */
export interface TemporalProximityEdge { kind: "temporal-proximity"; from: string; to: string; temporal_window_ms: number; identity_evidence: false; }
export type ProjectedAdjacencyEdge = TypedAdjacencyEdge | TemporalProximityEdge;
export interface TypedAdjacencyProjection { edges: readonly ProjectedAdjacencyEdge[]; }

export const DEFAULT_TEMPORAL_PROXIMITY_WINDOW_MS = 48 * 60 * 60 * 1000;

const claimNode = (revision: string) => `claim:${revision}`;
const entityNode = (entity: string) => `entity:${entity}`;
const evidenceNode = (id: string) => `evidence:${id}`;
const eventNode = (id: string) => `event:${id}`;
const captureNode = (id: string) => `capture:${id}`;
const pair = (kind: TypedAdjacencyEdge["kind"], left: string, right: string): TypedAdjacencyEdge[] => [
  { kind, from: left, to: right }, { kind, from: right, to: left },
];
const canonical = (edges: readonly ProjectedAdjacencyEdge[]): TypedAdjacencyProjection => ({
  edges: [...edges].sort((left, right) => compareStrings(`${left.kind}\u0000${left.from}\u0000${left.to}`, `${right.kind}\u0000${right.from}\u0000${right.to}`)),
});

const interval = (claim: CommittedClaim): PersistedValidTime["resolved_interval"] | null =>
  claim.claim.lifecycle === "canonical" ? claim.claim.temporal_scope.valid_time.resolved_interval : null;
const overlaps = (left: CommittedClaim, right: CommittedClaim): boolean => {
  const a = interval(left); const b = interval(right);
  if (!a || !b || a.kind === "imprecise" || b.kind === "imprecise") return false;
  // Instants are points; equal points are adjacent, while a point has no
  // invented duration that could bridge a calendar interval.
  if (a.kind === "instant" || b.kind === "instant") return a.kind === "instant" && b.kind === "instant" && a.start === b.start;
  return a.start < b.end && b.start < a.end;
};
/**
 * G5's read-only topology projection. Its only input is the already-safe D46
 * subgraph, so an excluded claim cannot add a node, path, count, or edge.
 */
export const projectTypedAdjacency = (subgraph: SafeSubgraph, options: { temporal_proximity_window_ms?: number } = {}): TypedAdjacencyProjection => {
  const temporalWindow = options.temporal_proximity_window_ms ?? DEFAULT_TEMPORAL_PROXIMITY_WINDOW_MS;
  if (!Number.isInteger(temporalWindow) || temporalWindow < 0) throw new Error("temporal proximity window must be a non-negative integer milliseconds");
  const edges: ProjectedAdjacencyEdge[] = [];
  const claims = [...subgraph.claims].sort((left, right) => compareStrings(left.revision_id, right.revision_id));
  for (let left = 0; left < claims.length; left += 1) for (let right = left + 1; right < claims.length; right += 1) {
    const a = claims[left]!; const b = claims[right]!;
    if (overlaps(a, b)) edges.push(...pair("when-adjacent", claimNode(a.revision_id), claimNode(b.revision_id)));
  }
  const entityMembers = new Map<string, string[]>();
  // Append in place; the rebuild-per-row form was O(rows^2) in memmove.
  for (const edge of subgraph.adjacency) { const bucket = entityMembers.get(edge.entity_id); if (bucket) bucket.push(edge.claim_revision_id); else entityMembers.set(edge.entity_id, [edge.claim_revision_id]); }
  for (const [entity, members] of entityMembers) {
    const unique = [...new Set(members)].sort();
    // Keep the durable entity itself as a navigable anchor.  The claim-to-claim
    // connector remains useful for compact traversal, but cannot satisfy a
    // query that starts at the entity the dream just bound.
    for (const member of unique) edges.push(...pair("entity-shared", entityNode(entity), claimNode(member)));
    for (let left = 0; left < unique.length; left += 1) for (let right = left + 1; right < unique.length; right += 1) edges.push(...pair("entity-shared", claimNode(unique[left]!), claimNode(unique[right]!)));
  }
  const captureMembers = new Map<string, string[]>();
  for (const lineage of subgraph.evidence_lineage) {
    edges.push({ kind: "evidence-lineage", from: claimNode(lineage.claim_revision_id), to: evidenceNode(lineage.evidence_id) });
    edges.push({ kind: "evidence-lineage", from: evidenceNode(lineage.evidence_id), to: eventNode(lineage.event_revision_id) });
    edges.push({ kind: "evidence-lineage", from: eventNode(lineage.event_revision_id), to: captureNode(lineage.capture_session_id) });
    const bucket = captureMembers.get(lineage.capture_session_id); if (bucket) bucket.push(lineage.claim_revision_id); else captureMembers.set(lineage.capture_session_id, [lineage.claim_revision_id]);
  }
  for (const members of captureMembers.values()) {
    const unique = [...new Set(members)].sort();
    for (let left = 0; left < unique.length; left += 1) for (let right = left + 1; right < unique.length; right += 1) edges.push(...pair("source-shared", claimNode(unique[left]!), claimNode(unique[right]!)));
  }
  // One directed edge per consecutive capture preserves each proximity component without a clique.
  const watermarkByCapture = new Map<string, string>();
  for (const lineage of subgraph.evidence_lineage) {
    if (!lineage.event_time) continue;
    const current = watermarkByCapture.get(lineage.capture_session_id);
    if (!current || current < lineage.event_time) watermarkByCapture.set(lineage.capture_session_id, lineage.event_time);
  }
  const captures = [...watermarkByCapture.entries()].map(([capture_session_id, event_time]) => ({ capture_session_id, event_time, timestamp: Date.parse(event_time) }))
    .filter((capture) => Number.isFinite(capture.timestamp)).sort((left, right) => left.timestamp - right.timestamp || compareStrings(left.capture_session_id, right.capture_session_id));
  for (let index = 1; index < captures.length; index += 1) {
    const previous = captures[index - 1]!, next = captures[index]!;
    if (next.timestamp - previous.timestamp <= temporalWindow) edges.push({ kind: "temporal-proximity", from: captureNode(previous.capture_session_id), to: captureNode(next.capture_session_id), temporal_window_ms: temporalWindow, identity_evidence: false });
  }
  return canonical([...new Map(edges.map((edge) => [`${edge.kind}\u0000${edge.from}\u0000${edge.to}`, edge])).values()]);
};
