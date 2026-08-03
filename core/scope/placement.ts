import type { Entity, Evidence, ProvisionalClaim, Scope } from "../schema";

export interface ScopeRoleRequest {
  strategy: "scope-role-binding";
  version: "v1";
  claim_revision_id: string;
  predicate: string;
  entity_role_slots: readonly string[];
  argument_surfaces: readonly { slot_id: string; role: string; surface: string }[];
  evidence: readonly { evidence_id: string; excerpt: string }[];
  /** Model-visible IDs are required so a scope edge can only bind an owner-local candidate. */
  candidate_entities: readonly { entity_id: string; labels: readonly string[] }[];
  candidate_scope_labels: readonly string[];
  ambiguity_markers: readonly string[];
}
export interface ScopeRoleProposal { bindings: Readonly<Record<string, string | null>>; scope: Scope | null; }
export interface ScopeRolePlan { bindings: Readonly<Record<string, string | null>>; scope: Scope | null; abstained_slots: readonly string[]; scope_abstained: boolean; confidently_placed: boolean; }

export const buildScopeRoleRequest = (claim: ProvisionalClaim, entities: readonly Entity[], evidence: readonly Evidence[]): ScopeRoleRequest => {
  const evidenceById = new Map(evidence.map((item) => [item.evidence_id, item]));
  const excerpts = claim.evidence_refs.map((evidence_id) => {
    const item = evidenceById.get(evidence_id);
    if (!item?.excerpt) throw new Error(`scope request lacks retained evidence excerpt: ${evidence_id}`);
    return { evidence_id, excerpt: item.excerpt };
  });
  if (!excerpts.length) throw new Error("scope request lacks retained evidence excerpt");
  const ownerEntities = entities.filter((entity) => entity.owner_account_id === claim.owner_account_id);
  const candidate_scope_labels = ownerEntities.flatMap((entity) => entity.labels.length ? entity.labels : [entity.handle]);
  // No identity candidate is not evidence that the capture lacks a scope.
  // Keep the request scope-only and let the pure planner fail role bindings closed.
  return {
    strategy: "scope-role-binding", version: "v1", claim_revision_id: claim.claim_revision_id, predicate: claim.predicate,
    entity_role_slots: claim.arguments.map((argument) => argument.slot_id),
    argument_surfaces: claim.arguments.map((argument) => ({ slot_id: argument.slot_id, role: argument.role, surface: argument.surface ?? (argument.value.kind === "entity_ref" || argument.value.kind === "source_local_ref" ? argument.value.ref : String(argument.value.value)) })),
    evidence: excerpts,
    candidate_entities: ownerEntities.map((entity) => ({ entity_id: entity.entity_id, labels: entity.labels.length ? entity.labels : [entity.handle] })),
    candidate_scope_labels,
    ambiguity_markers: claim.ambiguity_markers,
  };
};

/** Pure D-c planner. It accepts opaque scope refs and never creates a content taxonomy. */
export const planScopeAndRoles = (claim: ProvisionalClaim, entities: readonly Entity[], proposal: ScopeRoleProposal): ScopeRolePlan => {
  const slots = claim.arguments.map((argument) => argument.slot_id);
  const entityIds = new Set(entities.filter((entity) => entity.owner_account_id === claim.owner_account_id).map((entity) => entity.entity_id));
  const bindings: Record<string, string | null> = {};
  for (const slot of slots) {
    const target = proposal.bindings[slot] ?? null;
    bindings[slot] = target !== null && entityIds.has(target) ? target : null;
  }
  const abstained_slots = Object.entries(bindings).filter(([, target]) => target === null).map(([slot]) => slot);
  const hedgedOneOff = claim.ambiguity_markers.includes("hedged") && claim.ambiguity_markers.includes("one_off");
  const scope = hedgedOneOff && proposal.scope?.locality === "durable"
    ? { locality: "source_local" as const, scope_ref: null }
    : proposal.scope;
  return { bindings, scope, abstained_slots, scope_abstained: scope === null || scope.scope_ref === null, confidently_placed: abstained_slots.length === 0 && scope !== null && scope.scope_ref !== null };
};
