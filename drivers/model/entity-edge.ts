import type { ModelPort } from "./port";
import { buildEntityResolutionRequest, planEntityResolution, type EntityProposal, type EntityTable } from "../../core/resolve/entities";
import type { LocalHandle } from "../../core/resolve/mentions";

/** Imperative model boundary for D-b; the resolver itself remains pure. */
export const invokeEntityStrategy = async (port: ModelPort, table: EntityTable, owner: string, handle: LocalHandle, evidence: readonly string[], candidates: readonly string[]) => {
  const request = buildEntityResolutionRequest(owner, handle, evidence, candidates);
  const proposal = await port.invoke({ strategy: request.strategy, version: request.version, input: request }) as EntityProposal;
  return planEntityResolution(table, request, proposal);
};
