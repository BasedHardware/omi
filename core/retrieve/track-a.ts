import { sha256CanonicalRedacted } from "../ledger";
import { policyPartitionLabel, type TreeInputSnapshot } from "./index";
import { nodeId, type StructuralNode, type StructuralTree, type ViewKind } from "./tree";

export type TrackAPerturbation = "late_arrival" | "correction" | "liveness_supersession" | "identity_merge" | "identity_split" | "policy_classifier" | "timezone" | "source_reassignment" | "strategy" | "render_model_swap";
export interface TrackAReport {
  perturbation: TrackAPerturbation;
  eligible_node_denominator: number;
  stable_node_ids: number;
  invalidated_node_ids: readonly string[];
  structure_converged: boolean;
}
const parts = (value: string, timezone: string) => {
  const p = new Intl.DateTimeFormat("en-US", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(value));
  return (type: string) => p.find((item) => item.type === type)?.value ?? "00";
};

/**
 * Independent transition implementation for Track A. It deliberately does not invoke
 * buildDeterministicAnchors; duplicate, small anchor logic is intentional backstop code.
 */
export const incrementallyTransitionAnchors = (_previous: StructuralTree, next: TreeInputSnapshot): StructuralTree => {
  type Draft = { view: ViewKind; anchor: string; parent: string | null; partition: string; members: Set<string> };
  const drafts = new Map<string, Draft>();
  const add = (view: ViewKind, anchor: string, parent: string | null, partition: string, id: string) => {
    const key = `${view}\u0000${anchor}\u0000${partition}`;
    const draft = drafts.get(key) ?? { view, anchor, parent, partition, members: new Set<string>() };
    draft.members.add(id); drafts.set(key, draft);
  };
  for (const claim of next.claims) {
    const partition = policyPartitionLabel(claim.policy_class);
    if (claim.time_anchor.kind === "imprecise_time") add("temporal", "imprecise-time", null, partition, claim.claim_revision_id);
    else {
      const get = parts(claim.valid_time!, next.account_timezone); const y = `year:${get("year")}`, m = `${y}/month:${get("month")}`, d = `${m}/day:${get("day")}`;
      add("temporal", y, null, partition, claim.claim_revision_id); add("temporal", m, y, partition, claim.claim_revision_id); add("temporal", d, m, partition, claim.claim_revision_id);
    }
    if (claim.placement_status === "canonical") for (const argument of claim.arguments) if (argument.value.kind === "entity_ref") add("entity", `entity:${argument.value.ref}`, null, partition, claim.claim_revision_id);
    const captures = [...new Set(claim.evidence_spans.map((span) => span.capture_session_id))];
    for (const capture of captures.length ? captures : ["unknown-capture"]) add("source", `capture:${capture}`, null, partition, claim.claim_revision_id);
  }
  const all = [...drafts.values()];
  const nodes: StructuralNode[] = all.map((draft) => {
    const members = [...draft.members].sort();
    const children = all.filter((other) => other.view === draft.view && other.parent === draft.anchor && other.partition === draft.partition).map((other) => nodeId(next.owner_account_id, other.view, other.anchor, other.partition)).sort();
    const parent = draft.parent ? all.find((other) => other.view === draft.view && other.anchor === draft.parent && other.partition === draft.partition) : undefined;
    return { node_id: nodeId(next.owner_account_id, draft.view, draft.anchor, draft.partition), view_kind: draft.view, anchor_key: draft.anchor, parent_node_id: parent ? nodeId(next.owner_account_id, parent.view, parent.anchor, parent.partition) : null, child_node_ids: children, order_key: draft.anchor, policy_partition_label: draft.partition, member_claim_revision_ids: members, structural_revision: sha256CanonicalRedacted({ view_kind: draft.view, anchor_key: draft.anchor, partition: draft.partition, member_claim_revision_ids: members, graph_generation: next.graph_generation }), dependency_manifest: { live_member_revisions: members, child_render_hashes: [] }, graph_generation: next.graph_generation };
  }).sort((a, b) => a.node_id.localeCompare(b.node_id));
  return { input_generation: next.graph_generation, nodes };
};

/** Track A validates deterministic-anchor + input integrity only; it is not a D13/D14/D17 gate. */
export const compareTrackA = (perturbation: TrackAPerturbation, previous: StructuralTree, fullRebuild: StructuralTree, incremental: StructuralTree): TrackAReport => {
  const oldIds = new Set(previous.nodes.map((node) => node.node_id));
  const nextIds = new Set(fullRebuild.nodes.map((node) => node.node_id));
  const stable = [...nextIds].filter((id) => oldIds.has(id));
  const invalidated = [...new Set([
    ...fullRebuild.nodes.filter((node) => !oldIds.has(node.node_id) || previous.nodes.find((old) => old.node_id === node.node_id)?.structural_revision !== node.structural_revision).map((node) => node.node_id),
    ...previous.nodes.filter((node) => !nextIds.has(node.node_id)).map((node) => node.node_id),
  ])].sort();
  return { perturbation, eligible_node_denominator: fullRebuild.nodes.length, stable_node_ids: stable.length, invalidated_node_ids: invalidated, structure_converged: JSON.stringify(fullRebuild) === JSON.stringify(incremental) };
};
