import type { Entity, ProvisionalClaim, Scope } from "../schema";

export interface ScopeRoleRequest { strategy: "scope-role-binding"; version: "v1"; claim_revision_id: string; entity_role_slots: readonly string[]; ambiguity_markers: readonly string[]; }
export interface ScopeRoleProposal { bindings: Readonly<Record<string, string | null>>; scope: Scope | null; }
export interface ScopeRolePlan { bindings: Readonly<Record<string, string | null>>; scope: Scope | null; abstained_slots: readonly string[]; scope_abstained: boolean; confidently_placed: boolean; }

export const buildScopeRoleRequest = (claim: ProvisionalClaim): ScopeRoleRequest => ({
  strategy: "scope-role-binding", version: "v1", claim_revision_id: claim.claim_revision_id,
  entity_role_slots: claim.arguments.filter((argument) => argument.value.kind === "entity_ref").map((argument) => argument.slot_id),
  ambiguity_markers: claim.ambiguity_markers,
});

/** Pure D-c planner. It accepts opaque scope refs and never creates a content taxonomy. */
export const planScopeAndRoles = (claim: ProvisionalClaim, entities: readonly Entity[], proposal: ScopeRoleProposal): ScopeRolePlan => {
  const request = buildScopeRoleRequest(claim);
  const entityIds = new Set(entities.filter((entity) => entity.owner_account_id === claim.owner_account_id).map((entity) => entity.entity_id));
  const bindings: Record<string, string | null> = {};
  for (const slot of request.entity_role_slots) {
    const target = proposal.bindings[slot] ?? null;
    bindings[slot] = target !== null && entityIds.has(target) ? target : null;
  }
  const abstained_slots = Object.entries(bindings).filter(([, target]) => target === null).map(([slot]) => slot);
  const hedgedOneOff = request.ambiguity_markers.includes("hedged") && request.ambiguity_markers.includes("one_off");
  const scope = hedgedOneOff && proposal.scope?.locality === "durable"
    ? { locality: "source_local" as const, scope_ref: null }
    : proposal.scope;
  return { bindings, scope, abstained_slots, scope_abstained: scope === null || scope.scope_ref === null, confidently_placed: abstained_slots.length === 0 && scope !== null && scope.scope_ref !== null };
};
