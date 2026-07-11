import {
  adapterCredentialScopeFor,
  isProductionAdapterId,
  type AdapterCredentialScope,
  type ProductionAdapterId,
} from "../adapters/interface.js";

export type AgentExecutionRole = "coordinator" | "leaf";
export type ProviderBoundary = "managed_cloud" | `local_user:${string}`;

export const LEAF_AGENT_CONTROL_TOOLS = new Set([
  "send_agent_message",
  "spawn_background_agent",
  "spawn_agent",
  "run_agent_and_wait",
]);

export function providerBoundaryForAdapter(adapterId: string): ProviderBoundary {
  if (isProductionAdapterId(adapterId) && adapterCredentialScopeFor(adapterId) === "managed_cloud") {
    return "managed_cloud";
  }
  return `local_user:${adapterId}`;
}

export function credentialScopeForBoundary(boundary: ProviderBoundary): AdapterCredentialScope {
  return boundary === "managed_cloud" ? "managed_cloud" : "local_user";
}

export function resolveAdapterWithinBoundary(input: {
  providerBoundary: ProviderBoundary;
  defaultAdapterId: string;
  requestedAdapterId?: string;
}): string {
  const requestedAdapterId = input.requestedAdapterId ?? input.defaultAdapterId;
  if (!isProductionAdapterId(input.defaultAdapterId)) {
    // Test/development adapters are deliberately outside the production
    // registry. They may only keep their current adapter identity.
    if (requestedAdapterId !== input.defaultAdapterId) {
      throw new Error(`Adapter ${requestedAdapterId} is outside the owning execution boundary.`);
    }
    return requestedAdapterId;
  }
  if (!isProductionAdapterId(requestedAdapterId)) {
    throw new Error(`Unknown production adapter: ${requestedAdapterId}`);
  }
  if (requestedAdapterId === "acp" && input.providerBoundary !== "local_user:acp") {
    throw new Error("Local Claude is available only when the User Claude mode is selected.");
  }
  if (input.providerBoundary === "managed_cloud") {
    if (adapterCredentialScopeFor(requestedAdapterId) !== "managed_cloud") {
      throw new Error("Managed Omi agents can only use Omi cloud routing.");
    }
    return requestedAdapterId;
  }
  const pinnedAdapterId = input.providerBoundary.slice("local_user:".length);
  if (requestedAdapterId !== pinnedAdapterId) {
    if (requestedAdapterId === "acp") {
      throw new Error("Local Claude is available only when the User Claude mode is selected.");
    }
    throw new Error(`Local provider mode is pinned to ${pinnedAdapterId}.`);
  }
  return requestedAdapterId;
}

export function assertProductionAdapterScopeDeclared(adapterId: ProductionAdapterId): void {
  const scope = adapterCredentialScopeFor(adapterId);
  if (scope !== "managed_cloud" && scope !== "local_user") {
    throw new Error(`Production adapter ${adapterId} is missing credentialScope`);
  }
}

export function executionRoleAllowsTool(role: AgentExecutionRole, toolName: string): boolean {
  return role !== "leaf" || !LEAF_AGENT_CONTROL_TOOLS.has(toolName);
}

export function executionRoleForSurface(input: {
  surfaceKind: string;
  externalRefKind?: string | null;
}): AgentExecutionRole {
  return input.surfaceKind === "delegated_agent"
    || input.surfaceKind === "background_agent"
    || (input.surfaceKind === "floating_bar" && input.externalRefKind === "pill")
    ? "leaf"
    : "coordinator";
}
