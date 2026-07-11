import { describe, expect, it } from "vitest";
import {
  executionRoleAllowsTool,
  providerBoundaryForAdapter,
  resolveAdapterWithinBoundary,
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
