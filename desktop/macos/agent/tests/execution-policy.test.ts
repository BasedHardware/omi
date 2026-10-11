import { describe, expect, it } from "vitest";
import {
  adapterUsesCloudModelQoSHint,
  executionRoleAllowsTool,
  providerBoundaryForAdapter,
  resolveAdapterWithinBoundary,
  runRequestedModelIdForSession,
  shouldRecordServedModelAsRunRequestedId,
} from "../src/runtime/execution-policy.js";

describe("agent execution policy", () => {
  it("derives the declared production credential boundary", () => {
    expect(providerBoundaryForAdapter("pi-mono")).toBe("managed_cloud");
    expect(providerBoundaryForAdapter("acp")).toBe("local_user:acp");
    expect(providerBoundaryForAdapter("hermes")).toBe("local_user:hermes");
    expect(providerBoundaryForAdapter("openclaw")).toBe("local_user:openclaw");
  });

  it("pins local-user surfaces to the exact selected adapter", () => {
    expect(resolveAdapterWithinBoundary({
      providerBoundary: "local_user:acp",
      defaultAdapterId: "acp",
      requestedAdapterId: "acp",
    })).toBe("acp");
    expect(() => resolveAdapterWithinBoundary({
      providerBoundary: "local_user:acp",
      defaultAdapterId: "acp",
      requestedAdapterId: "hermes",
    })).toThrow("Local provider mode is pinned to acp");
  });

  it("fails closed for local and unknown overrides from managed execution", () => {
    for (const adapterId of ["acp", "hermes", "openclaw", "unknown-adapter"]) {
      expect(() => resolveAdapterWithinBoundary({
        providerBoundary: "managed_cloud",
        defaultAdapterId: "pi-mono",
        requestedAdapterId: adapterId,
      })).toThrow();
    }
  });

  it("persists cloud QoS hints only for adapters that honor them", () => {
    const managedPiMono = {
      providerBoundary: "managed_cloud" as const,
      defaultAdapterId: "pi-mono",
      modelProfile: "claude-sonnet-4-6",
    };
    expect(adapterUsesCloudModelQoSHint(managedPiMono)).toBe(true);
    expect(runRequestedModelIdForSession(managedPiMono)).toBe("claude-sonnet-4-6");
    expect(shouldRecordServedModelAsRunRequestedId(managedPiMono)).toBe(false);

    const localPiMono = {
      providerBoundary: "managed_cloud" as const,
      defaultAdapterId: "pi-mono",
      modelProfile: null,
    };
    expect(adapterUsesCloudModelQoSHint(localPiMono)).toBe(false);
    expect(runRequestedModelIdForSession(localPiMono)).toBeNull();
    expect(shouldRecordServedModelAsRunRequestedId(localPiMono)).toBe(true);

    for (const adapterId of ["hermes", "openclaw"] as const) {
      const localProvider = {
        providerBoundary: `local_user:${adapterId}` as const,
        defaultAdapterId: adapterId,
        modelProfile: "claude-sonnet-4-6",
      };
      expect(adapterUsesCloudModelQoSHint(localProvider)).toBe(false);
      expect(runRequestedModelIdForSession(localProvider)).toBeNull();
      expect(shouldRecordServedModelAsRunRequestedId(localProvider)).toBe(true);
    }

    const userClaude = {
      providerBoundary: "local_user:acp" as const,
      defaultAdapterId: "acp",
      modelProfile: "claude-sonnet-4-6",
    };
    expect(adapterUsesCloudModelQoSHint(userClaude)).toBe(true);
    expect(runRequestedModelIdForSession(userClaude)).toBe("claude-sonnet-4-6");
  });

  it("denies every leaf-restricted control tool for leaf roles", () => {
    for (const toolName of [
      "send_agent_message",
      "spawn_background_agent",
      "spawn_agent",
      "run_agent_and_wait",
    ]) {
      expect(executionRoleAllowsTool("leaf", toolName)).toBe(false);
      expect(executionRoleAllowsTool("coordinator", toolName)).toBe(true);
    }
  });
});
