import { canonicalEntityIdsAt, project, type GraphSnapshot, type SafeSubgraph } from "./index";
import { projectTypedAdjacency, type TypedAdjacencyKind } from "./adjacency";
import { walk, type WalkPath } from "./walk";

export interface GraphComponent { nodes: readonly string[]; }
export interface TrajectoryDiff {
  entities_merged: readonly { canonical_entity_id: string; entity_ids: readonly string[] }[];
  entities_split: readonly { previous_canonical_entity_id: string; entity_ids: readonly string[] }[];
  predicates_aliased: readonly string[];
  components_before: readonly GraphComponent[];
  components_after: readonly GraphComponent[];
  paths_newly_walkable: readonly WalkPath[];
  claims_reprojected: readonly { claim_revision_id: string; raw_key: string; previous_resolved_key: string | null; resolved_key: string; frontier: string }[];
}

const ownerProjection = (snapshot: GraphSnapshot): SafeSubgraph => project(snapshot, { reader_account_id: snapshot.owner_account_id, grant: { grant_id: "owner-trajectory", policy_classes: [] } });
const components = (subgraph: SafeSubgraph, relationKinds: readonly TypedAdjacencyKind[], temporalWindow?: number): readonly GraphComponent[] => {
  const edges = projectTypedAdjacency(subgraph, { temporal_proximity_window_ms: temporalWindow }).edges.filter((edge) => relationKinds.includes(edge.kind));
  const neighbors = new Map<string, Set<string>>();
  for (const claim of subgraph.claims) neighbors.set(`claim:${claim.revision_id}`, new Set());
  for (const edge of edges) { neighbors.set(edge.from, new Set([...(neighbors.get(edge.from) ?? []), edge.to])); neighbors.set(edge.to, new Set([...(neighbors.get(edge.to) ?? []), edge.from])); }
  const unseen = new Set(neighbors.keys()), output: GraphComponent[] = [];
  while (unseen.size) {
    const first = [...unseen].sort()[0]!; const found = new Set([first]); const queue = [first]; unseen.delete(first);
    while (queue.length) for (const next of neighbors.get(queue.shift()!) ?? []) if (!found.has(next)) { found.add(next); unseen.delete(next); queue.push(next); }
    output.push({ nodes: [...found].sort() });
  }
  return output.sort((left, right) => left.nodes.join("\u0000").localeCompare(right.nodes.join("\u0000")));
};
const entityGroups = (snapshot: GraphSnapshot): Map<string, string[]> => {
  const canonical = canonicalEntityIdsAt(snapshot); const groups = new Map<string, string[]>();
  for (const entity of snapshot.entities) { const root = canonical.get(entity.entity.entity_id) ?? entity.entity.entity_id; groups.set(root, [...(groups.get(root) ?? []), entity.entity.entity_id]); }
  for (const members of groups.values()) members.sort();
  return groups;
};
const pathSignature = (path: WalkPath): string => JSON.stringify({ nodes: path.nodes, hops: path.hops.map((hop) => ({ relation_kind: hop.relation_kind, from: hop.from, to: hop.to, temporal_window_ms: hop.temporal_window_ms })) });

/** A pure cycle-to-cycle report: it exposes structural deltas without treating either snapshot as truth. */
export const diffGraphSnapshots = (before: GraphSnapshot, after: GraphSnapshot, options: { max_hops?: number; path_cap_per_anchor?: number; relation_kinds?: readonly TypedAdjacencyKind[]; temporal_proximity_window_ms?: number } = {}): TrajectoryDiff => {
  const relationKinds = options.relation_kinds ?? ["when-adjacent", "entity-shared", "evidence-lineage", "source-shared", "temporal-proximity"];
  const beforeSafe = ownerProjection(before), afterSafe = ownerProjection(after);
  const beforeGroups = entityGroups(before), afterGroups = entityGroups(after);
  const entities_merged = [...afterGroups].flatMap(([canonical_entity_id, entity_ids]) => {
    const prior = new Set(entity_ids.map((id) => canonicalEntityIdsAt(before).get(id) ?? id));
    return entity_ids.length > 1 && prior.size > 1 ? [{ canonical_entity_id, entity_ids }] : [];
  }).sort((left, right) => left.canonical_entity_id.localeCompare(right.canonical_entity_id));
  const entities_split = [...beforeGroups].flatMap(([previous_canonical_entity_id, entity_ids]) => {
    const next = new Set(entity_ids.map((id) => canonicalEntityIdsAt(after).get(id) ?? id));
    return entity_ids.length > 1 && next.size > 1 ? [{ previous_canonical_entity_id, entity_ids }] : [];
  }).sort((left, right) => left.previous_canonical_entity_id.localeCompare(right.previous_canonical_entity_id));
  const priorAssertions = new Set((before.predicate_assertions ?? []).map((item) => item.assertion.assertion_id));
  const predicates_aliased = (after.predicate_assertions ?? []).filter((item) => item.assertion.relation === "alias_of" && item.assertion.lifecycle === "active" && item.assertion.admission === "accepted" && !priorAssertions.has(item.assertion.assertion_id)).map((item) => item.assertion.assertion_id).sort();
  const maxHops = options.max_hops ?? 3, pathCap = options.path_cap_per_anchor ?? 100;
  const collect = (subgraph: SafeSubgraph): readonly WalkPath[] => {
    const anchors = [...new Set(projectTypedAdjacency(subgraph, { temporal_proximity_window_ms: options.temporal_proximity_window_ms }).edges.flatMap((edge) => [edge.from, edge.to]))].sort();
    return anchors.flatMap((anchor) => walk(subgraph, { anchor, max_hops: maxHops, result_cap: pathCap, relation_kinds: relationKinds, temporal_proximity_window_ms: options.temporal_proximity_window_ms }).paths);
  };
  const beforePaths = new Set(collect(beforeSafe).map(pathSignature));
  const paths_newly_walkable = collect(afterSafe).filter((path) => !beforePaths.has(pathSignature(path))).sort((left, right) => pathSignature(left).localeCompare(pathSignature(right)));
  const oldByRaw = new Map(before.claims.map((item) => [item.claim.proposition_key_raw, item.claim]));
  const claims_reprojected = after.claims.flatMap((item) => {
    const raw_key = item.claim.proposition_key_raw; const resolved_key = item.claim.proposition_key_resolved; const frontier = item.claim.predicate_alias_frontier;
    if (!raw_key || !resolved_key || !frontier) return [];
    const previous = oldByRaw.get(raw_key);
    return !previous || previous.proposition_key_resolved !== resolved_key || previous.predicate_alias_frontier !== frontier ? [{ claim_revision_id: item.revision_id, raw_key, previous_resolved_key: previous?.proposition_key_resolved ?? null, resolved_key, frontier }] : [];
  }).sort((left, right) => left.claim_revision_id.localeCompare(right.claim_revision_id));
  return { entities_merged, entities_split, predicates_aliased, components_before: components(beforeSafe, relationKinds, options.temporal_proximity_window_ms), components_after: components(afterSafe, relationKinds, options.temporal_proximity_window_ms), paths_newly_walkable, claims_reprojected };
};
