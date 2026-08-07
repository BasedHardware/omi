import { compareStrings } from "../order";
import { canonicalEntityIdsAt, project, type GraphSnapshot, type SafeSubgraph } from "./index";
import { projectTypedAdjacency, type TypedAdjacencyKind } from "./adjacency";
import { buildWalkIndex, walk, type WalkPath } from "./walk";

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
  // Insert into the existing Set: rebuilding it per edge made this O(edges^2).
  const link = (from: string, to: string) => { const bucket = neighbors.get(from); if (bucket) bucket.add(to); else neighbors.set(from, new Set([to])); };
  for (const edge of edges) { link(edge.from, edge.to); link(edge.to, edge.from); }
  const unseen = new Set(neighbors.keys()), output: GraphComponent[] = [];
  while (unseen.size) {
    // Lexicographic min, matching the previous [...unseen].sort()[0] without
    // re-sorting the whole frontier every round.
    let first: string | null = null; for (const node of unseen) if (first === null || node < first) first = node;
    const found = new Set([first!]); const queue = [first!]; unseen.delete(first!);
    while (queue.length) for (const next of neighbors.get(queue.shift()!) ?? []) if (!found.has(next)) { found.add(next); unseen.delete(next); queue.push(next); }
    output.push({ nodes: [...found].sort() });
  }
  return output.sort((left, right) => compareStrings(left.nodes.join("\u0000"), right.nodes.join("\u0000")));
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
  const canonicalBefore = canonicalEntityIdsAt(before), canonicalAfter = canonicalEntityIdsAt(after);
  const entities_merged = [...afterGroups].flatMap(([canonical_entity_id, entity_ids]) => {
    const prior = new Set(entity_ids.map((id) => canonicalBefore.get(id) ?? id));
    return entity_ids.length > 1 && prior.size > 1 ? [{ canonical_entity_id, entity_ids }] : [];
  }).sort((left, right) => compareStrings(left.canonical_entity_id, right.canonical_entity_id));
  const entities_split = [...beforeGroups].flatMap(([previous_canonical_entity_id, entity_ids]) => {
    const next = new Set(entity_ids.map((id) => canonicalAfter.get(id) ?? id));
    return entity_ids.length > 1 && next.size > 1 ? [{ previous_canonical_entity_id, entity_ids }] : [];
  }).sort((left, right) => compareStrings(left.previous_canonical_entity_id, right.previous_canonical_entity_id));
  const priorAssertions = new Set((before.predicate_assertions ?? []).map((item) => item.assertion.assertion_id));
  const predicates_aliased = (after.predicate_assertions ?? []).filter((item) => item.assertion.relation === "alias_of" && item.assertion.lifecycle === "active" && item.assertion.admission === "accepted" && !priorAssertions.has(item.assertion.assertion_id)).map((item) => item.assertion.assertion_id).sort();
  const maxHops = options.max_hops ?? 3, pathCap = options.path_cap_per_anchor ?? 100;
  /**
   * Visit every walkable path, in anchor order then walk order -- the exact
   * sequence the previous `anchors.flatMap(...)` produced, just never
   * materialized all at once.
   *
   * One projection serves every anchor. walk() used to rebuild the whole
   * O(claims^2) adjacency projection per anchor, so a graph with thousands of
   * anchors made this diff -- which runs at the end of EVERY dream cycle --
   * cost anchors x claims^2 and never finish.
   *
   * Streaming matters as much as that hoist did. On the live v7 graph there are
   * thousands of anchors and a 100-path cap on each, so collecting into an array
   * held hundreds of thousands of paths -- every one with its own node and hop
   * arrays -- plus a signature string per path, for BOTH snapshots, all live at
   * the same instant. The `before` side needs only the signatures and the
   * `after` side needs only the paths that turn out to be new, so neither of
   * those arrays has to exist.
   */
  const eachPath = (subgraph: SafeSubgraph, visit: (path: WalkPath) => void): void => {
    const index = buildWalkIndex(subgraph, { relation_kinds: relationKinds, temporal_proximity_window_ms: options.temporal_proximity_window_ms });
    const anchors = [...new Set(index.edges.flatMap((edge) => [edge.from, edge.to]))].sort();
    for (const anchor of anchors) {
      for (const path of walk(subgraph, { anchor, max_hops: maxHops, result_cap: pathCap, relation_kinds: relationKinds, temporal_proximity_window_ms: options.temporal_proximity_window_ms, index }).paths) visit(path);
    }
  };
  const beforePaths = new Set<string>();
  eachPath(beforeSafe, (path) => { beforePaths.add(pathSignature(path)); });
  // Filtering during the walk rather than after collecting is order-preserving:
  // survivors keep their relative order, and Array.sort is stable.
  const newlyWalkable: { path: WalkPath; signature: string }[] = [];
  eachPath(afterSafe, (path) => {
    const signature = pathSignature(path);
    if (!beforePaths.has(signature)) newlyWalkable.push({ path, signature });
  });
  const paths_newly_walkable = newlyWalkable.sort((left, right) => compareStrings(left.signature, right.signature)).map((entry) => entry.path);
  const oldByRaw = new Map(before.claims.map((item) => [item.claim.proposition_key_raw, item.claim]));
  const claims_reprojected = after.claims.flatMap((item) => {
    const raw_key = item.claim.proposition_key_raw; const resolved_key = item.claim.proposition_key_resolved; const frontier = item.claim.predicate_alias_frontier;
    if (!raw_key || !resolved_key || !frontier) return [];
    const previous = oldByRaw.get(raw_key);
    return !previous || previous.proposition_key_resolved !== resolved_key || previous.predicate_alias_frontier !== frontier ? [{ claim_revision_id: item.revision_id, raw_key, previous_resolved_key: previous?.proposition_key_resolved ?? null, resolved_key, frontier }] : [];
  }).sort((left, right) => compareStrings(left.claim_revision_id, right.claim_revision_id));
  return { entities_merged, entities_split, predicates_aliased, components_before: components(beforeSafe, relationKinds, options.temporal_proximity_window_ms), components_after: components(afterSafe, relationKinds, options.temporal_proximity_window_ms), paths_newly_walkable, claims_reprojected };
};
