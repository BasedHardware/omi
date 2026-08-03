import type { ModelPort } from "./port";
import { buildEntityResolutionRequest, planEntityResolution, type EntityProposal, type EntityTable, type LocalDurableBinding } from "../../core/resolve/entities";
import type { LocalHandle } from "../../core/resolve/mentions";
import type { CoreferenceSupport, IdentityAuthorization, SourceIdentityRef } from "../../core/schema";
import type { IdentityAuthorityContext } from "../../core/resolve/identity-authority";
import type { CandidateSnapshot } from "../../core/resolve/candidates";

/** Imperative model boundary for D-b; the resolver itself remains pure. */
export const invokeEntityStrategy = async (port: ModelPort, table: EntityTable, owner: string, handle: LocalHandle, evidence: readonly string[], candidates: readonly string[], localBindings: ReadonlyMap<string, LocalDurableBinding> = new Map(), sourceIdentity?: SourceIdentityRef, candidateSnapshot?: CandidateSnapshot, authorizations?: readonly IdentityAuthorization[], authorityContext?: IdentityAuthorityContext, discourseUnitRef?: string | null, coreferenceSupports?: readonly CoreferenceSupport[]) => {
  const candidateSet = new Set(candidates);
  const candidateEntities = table.entities
    .filter((entity) => candidateSet.has(entity.entity_id))
    .map(({ entity_id, handle: candidateHandle, labels }) => ({ entity_id, handle: candidateHandle, labels }));
  const request = buildEntityResolutionRequest(owner, handle, evidence, candidates, candidateEntities, sourceIdentity, candidateSnapshot, authorizations, authorityContext, discourseUnitRef, coreferenceSupports);
  const proposal = await port.invoke({ strategy: request.strategy, version: request.version, input: request }) as EntityProposal;
  return planEntityResolution(table, request, proposal, localBindings);
};
