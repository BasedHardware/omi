import type { ModelPort } from "./port";
import { buildScopeRoleRequest, planScopeAndRoles, type ScopeRoleProposal } from "../../core/scope/placement";
import type { Entity, Evidence, ProvisionalClaim } from "../../core/schema";

/** Imperative D-c edge; core request construction and planning have no model effect. */
export const invokeScopeStrategy = async (port: ModelPort, claim: ProvisionalClaim, entities: readonly Entity[], evidence: readonly Evidence[]) => {
  const request = buildScopeRoleRequest(claim, entities, evidence);
  const proposal = await port.invoke({ strategy: request.strategy, version: request.version, input: request }) as ScopeRoleProposal;
  return planScopeAndRoles(claim, entities, proposal);
};
