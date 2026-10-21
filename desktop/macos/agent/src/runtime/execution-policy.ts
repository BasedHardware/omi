import {
  adapterCredentialScopeFor,
  isProductionAdapterId,
  type AdapterCredentialScope,
  type ProductionAdapterId,
} from "../adapters/interface.js";

export type AgentExecutionRole = "coordinator" | "leaf";
export type ProviderBoundary = "managed_cloud" | `local_user:${string}`;

export type SessionModelRoutingContext = {
  providerBoundary: ProviderBoundary;
  defaultAdapterId: string;
  modelProfile: string | null;
};

/** True when session.modelProfile is a cloud QoS hint that the active adapter uses for routing. */
export function adapterUsesCloudModelQoSHint(session: SessionModelRoutingContext): boolean {
  const profile = session.modelProfile?.trim();
  if (!profile) {
    return false;
  }
  if (session.providerBoundary === "managed_cloud" && session.defaultAdapterId === "pi-mono") {
    return true;
  }
  if (session.defaultAdapterId === "acp") {
    return true;
  }
  return false;
}

/** Value persisted to runs.requested_model_id at admission time. */
export function runRequestedModelIdForSession(session: SessionModelRoutingContext): string | null {
  return adapterUsesCloudModelQoSHint(session) ? session.modelProfile : null;
}

/** When true, a model_used observation should replace requested_model_id on terminal success. */
export function shouldRecordServedModelAsRunRequestedId(session: SessionModelRoutingContext): boolean {
  return !adapterUsesCloudModelQoSHint(session);
}

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
