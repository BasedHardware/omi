import { compareStrings } from "../order";
import { sha256CanonicalRedacted } from "../ledger";
import { policyPartitionLabel, type LiveClaimView, type TreeInputSnapshot } from "./index";

export type ViewKind = "temporal" | "entity" | "source";
export interface DependencyManifest {
  live_member_revisions: readonly string[];
  child_render_hashes: readonly string[];
}
export interface StructuralNode {
  node_id: string;
  view_kind: ViewKind;
  anchor_key: string;
  parent_node_id: string | null;
  child_node_ids: readonly string[];
  order_key: string;
  policy_partition_label: string;
  member_claim_revision_ids: readonly string[];
  structural_revision: string;
  dependency_manifest: DependencyManifest;
  graph_generation: string;
}
export interface StructuralTree {
  input_generation: string;
  nodes: readonly StructuralNode[];
}

/**
 * Stable structural content only.  The graph frontier is intentionally metadata: a
 * new frontier must not invalidate an otherwise unchanged anchor.
 */
export const structuralRevision = (node: Pick<StructuralNode, "view_kind" | "anchor_key" | "policy_partition_label" | "member_claim_revision_ids" | "child_node_ids">): string =>
  sha256CanonicalRedacted({
    view_kind: node.view_kind,
    anchor_key: node.anchor_key,
    policy_partition_label: node.policy_partition_label,
    member_claim_revision_ids: [...node.member_claim_revision_ids].sort(),
    child_structural_refs: [...node.child_node_ids].sort(),
  });

/** Exact §8.3 derivation: no render, summary, membership, or prose enters this key. */
export const nodeId = (owner_account_id: string, view_kind: ViewKind, anchor_key: string, policy_partition: string): string =>
  `retrieval-node-v1:${sha256CanonicalRedacted({ owner_account_id, view_kind, anchor_key, policy_partition })}`;

const temporalParts = (value: string, timezone: string): { year: string; month: string; day: string } => {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date(value));
  const lookup = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return { year: lookup("year"), month: lookup("month"), day: lookup("day") };
};
const sorted = <T>(items: readonly T[], key: (item: T) => string): T[] => [...items].sort((left, right) => compareStrings(key(left), key(right)));

interface Draft { view_kind: ViewKind; anchor_key: string; parent_anchor: string | null; partition: string; members: Set<string>; }
const add = (drafts: Map<string, Draft>, view_kind: ViewKind, anchor_key: string, parent_anchor: string | null, claim: LiveClaimView): void => {
  const partition = policyPartitionLabel(claim.policy_class);
  const key = `${view_kind}\u0000${anchor_key}\u0000${partition}`;
  const draft = drafts.get(key) ?? { view_kind, anchor_key, parent_anchor, partition, members: new Set<string>() };
  draft.members.add(claim.claim_revision_id);
  drafts.set(key, draft);
};

/** Deterministic bookkeeping anchors only; no adaptive topology is implied by this builder. */
export const buildDeterministicAnchors = (input: TreeInputSnapshot): StructuralTree => {
  const drafts = new Map<string, Draft>();
  for (const claim of input.claims) {
    if (claim.time_anchor.kind === "imprecise_time") add(drafts, "temporal", "imprecise-time", null, claim);
    else {
      const { year, month, day } = temporalParts(claim.time_anchor.value, input.account_timezone);
      const yearKey = `year:${year}`, monthKey = `${yearKey}/month:${month}`, dayKey = `${monthKey}/day:${day}`;
      add(drafts, "temporal", yearKey, null, claim);
      add(drafts, "temporal", monthKey, yearKey, claim);
      add(drafts, "temporal", dayKey, monthKey, claim);
    }
    // D41: unplaced provisional claims have no safe entity relation and never enter this view.
    if (claim.placement_status === "canonical") for (const argument of claim.arguments) {
      if (argument.value.kind === "entity_ref") add(drafts, "entity", `entity:${argument.value.ref}`, null, claim);
    }
    const captures = [...new Set(claim.evidence_spans.map((span) => span.capture_session_id))];
    for (const capture of (captures.length ? captures : ["unknown-capture"])) add(drafts, "source", `capture:${capture}`, null, claim);
  }
  const draftValues = [...drafts.values()];
  const byIdentity = new Map(draftValues.map((draft) => [`${draft.view_kind}\u0000${draft.anchor_key}\u0000${draft.partition}`, draft]));
  const nodes = draftValues.map((draft) => {
    const id = nodeId(input.owner_account_id, draft.view_kind, draft.anchor_key, draft.partition);
    const parent = draft.parent_anchor ? byIdentity.get(`${draft.view_kind}\u0000${draft.parent_anchor}\u0000${draft.partition}`) : undefined;
    const member_claim_revision_ids = [...draft.members].sort();
    const child_node_ids = draftValues.filter((candidate) => candidate.view_kind === draft.view_kind && candidate.parent_anchor === draft.anchor_key && candidate.partition === draft.partition)
      .map((candidate) => nodeId(input.owner_account_id, candidate.view_kind, candidate.anchor_key, candidate.partition)).sort();
    const dependency_manifest = { live_member_revisions: member_claim_revision_ids, child_render_hashes: [] };
    const partial = { node_id: id, view_kind: draft.view_kind, anchor_key: draft.anchor_key,
      parent_node_id: parent ? nodeId(input.owner_account_id, parent.view_kind, parent.anchor_key, parent.partition) : null,
      child_node_ids, order_key: draft.anchor_key, policy_partition_label: draft.partition, member_claim_revision_ids,
      dependency_manifest, graph_generation: input.graph_generation };
    return { ...partial, structural_revision: structuralRevision(partial) } satisfies StructuralNode;
  });
  return { input_generation: input.graph_generation, nodes: sorted(nodes, (node) => node.node_id) };
};
