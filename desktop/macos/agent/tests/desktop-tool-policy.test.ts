import { describe, expect, it } from "vitest";
import { evaluateDesktopToolPolicy } from "../src/runtime/desktop-tool-policy.js";

describe("desktop tool policy", () => {
  it("allows selected read-only local context tools", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "execute_sql",
      selectedBundles: ["desktop.context.local_read"],
      sql: "select count(*) from action_items",
    });

    expect(result.decision).toBe("allow");
    expect(result.requiredBundles).toEqual(["desktop.context.local_read"]);
  });

  it("denies SQL writes even when local-read bundle is selected", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "execute_sql",
      selectedBundles: ["desktop.context.local_read"],
      sql: "update action_items set completed = 1",
    });

    expect(result.decision).toBe("deny");
    expect(result.reason).toContain("SQL writes");
  });

  it("does not hidden-allow sensitive screenshot image access", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "get_screenshot",
      selectedBundles: ["desktop.context.screenshot_image"],
      includesScreenshotImageBytes: true,
    });

    expect(result.decision).toBe("dispatch_required");
    expect(result.requiredBundles).toEqual(["desktop.context.screenshot_image"]);
  });

  it("keeps look_at_frame on the same scoped, audited screenshot path", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "look_at_frame",
      operation: "look_at_frame",
      resourceRef: "screenshot:42",
      selectedBundles: ["desktop.context.screenshot_image"],
      includesScreenshotImageBytes: true,
    });

    expect(result.decision).toBe("dispatch_required");
    expect(result.descriptor.privacyTier).toBe("sensitive");
    expect(result.descriptor.approvalPolicy).toBe("user_approval");
    expect(result.requiredBundles).toEqual(["desktop.context.screenshot_image"]);
    expect(result.reason).toContain("dispatch");
  });

  it("requires dispatch for task writes by default", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "complete_task",
      selectedBundles: ["desktop.tasks.readwrite"],
    });

    expect(result.decision).toBe("dispatch_required");
  });

  it("classifies create_memory as an approved coordinator write", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "create_memory",
      selectedBundles: ["desktop.memories.write"],
      userExplicitMutation: true,
    });

    expect(result.requiredBundles).toEqual(["desktop.memories.write"]);
    expect(result.decision).toBe("dispatch_required");
    expect(result.descriptor.readOnly).toBe(false);
  });

  it("requires dispatch for external sends and denies unselected bundles", () => {
    expect(
      evaluateDesktopToolPolicy({
        requestedBundles: ["external.write_send"],
        selectedBundles: ["external.write_send"],
        externalSend: true,
      }).decision,
    ).toBe("dispatch_required");

    const denied = evaluateDesktopToolPolicy({
      requestedBundles: ["external.write_send"],
      selectedBundles: ["external.write_prepare"],
      externalSend: true,
    });
    expect(denied.decision).toBe("deny");
    expect(denied.reason).toContain("Missing selected bundle");
  });

  it("keeps workstream external sends blocked until a matching scoped grant exists", () => {
    const base = {
      requestedBundles: ["external.write_send"] as const,
      selectedBundles: ["external.write_send"] as const,
      externalSend: true,
      operation: "send_email",
      resourceRef: "workstream:ws-launch",
      nowMs: 1_000,
    };

    expect(evaluateDesktopToolPolicy(base).decision).toBe("dispatch_required");
    expect(
      evaluateDesktopToolPolicy({
        ...base,
        grants: [
          {
            bundle: "external.write_send" as const,
            operation: "send_email",
            resourceRef: "workstream:ws-launch",
            effect: "allow" as const,
            expiresAtMs: 2_000,
          },
        ],
      }).decision,
    ).toBe("allow");
    expect(
      evaluateDesktopToolPolicy({
        ...base,
        resourceRef: "workstream:ws-other",
        grants: [
          {
            bundle: "external.write_send" as const,
            operation: "send_email",
            resourceRef: "workstream:ws-launch",
            effect: "allow" as const,
            expiresAtMs: 2_000,
          },
        ],
      }).decision,
    ).toBe("dispatch_required");
  });

  it("keeps automation actuation dev-only", () => {
    const prod = evaluateDesktopToolPolicy({
      requestedBundles: ["desktop.automation.act_dev_only"],
      selectedBundles: ["desktop.automation.act_dev_only"],
      isDevBundle: false,
    });
    const dev = evaluateDesktopToolPolicy({
      requestedBundles: ["desktop.automation.act_dev_only"],
      selectedBundles: ["desktop.automation.act_dev_only"],
      isDevBundle: true,
    });

    expect(prod.decision).toBe("deny");
    expect(dev.decision).toBe("dispatch_required");
  });

  it("treats a macOS permission request as a production user-approved capability", () => {
    const base = {
      toolName: "request_permission",
      selectedBundles: ["desktop.permissions.request"] as const,
      operation: "request_permission",
      resourceRef: "permission:screen_recording",
      nowMs: 1_000,
    };

    const pending = evaluateDesktopToolPolicy(base);
    expect(pending.decision).toBe("dispatch_required");
    expect(pending.requiredBundles).toEqual(["desktop.permissions.request"]);
    expect(pending.descriptor.approvalPolicy).toBe("user_approval");

    const granted = evaluateDesktopToolPolicy({
      ...base,
      grants: [{
        bundle: "desktop.permissions.request" as const,
        operation: "request_permission",
        resourceRef: "permission:screen_recording",
        effect: "allow" as const,
        expiresAtMs: 2_000,
      }],
    });
    expect(granted.decision).toBe("allow");
  });

  it("allows the JIT knowledge-ledger read tools without dispatch", () => {
    for (const toolName of ["search_knowledge", "read_playbook", "search_historical_facts", "get_entity_timeline_tool"]) {
      const result = evaluateDesktopToolPolicy({
        toolName,
        selectedBundles: ["desktop.context.local_read"],
      });

      expect(result.decision, toolName).toBe("allow");
      expect(result.requiredBundles, toolName).toEqual(["desktop.context.local_read"]);
      expect(result.descriptor.approvalPolicy, toolName).toBe("allow");
      expect(result.descriptor.readOnly, toolName).toBe(true);
    }
  });

  it("classifies the JIT knowledge-ledger write verbs as approved memory writes, like create_memory", () => {
    for (const toolName of ["save_playbook", "create_standing_trigger", "close_fact"]) {
      const result = evaluateDesktopToolPolicy({
        toolName,
        selectedBundles: ["desktop.memories.write"],
        userExplicitMutation: true,
      });

      expect(result.requiredBundles, toolName).toEqual(["desktop.memories.write"]);
      expect(result.decision, toolName).toBe("dispatch_required");
      expect(result.descriptor.readOnly, toolName).toBe(false);
      expect(result.descriptor.approvalPolicy, toolName).toBe("user_approval");
    }
  });

  it("denies the JIT knowledge-ledger write verbs when the memory-write bundle is not selected", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "save_playbook",
      selectedBundles: [],
    });

    expect(result.decision).toBe("deny");
    expect(result.reason).toContain("Missing selected bundle");
  });

  it("honors scoped allow grants without broadening other sensitive requests", () => {
    const nowMs = 1_000;
    const granted = evaluateDesktopToolPolicy({
      requestedBundles: ["desktop.context.screenshot_image"],
      selectedBundles: ["desktop.context.screenshot_image"],
      operation: "get_screenshot",
      resourceRef: "screenshot:42",
      nowMs,
      grants: [
        {
          bundle: "desktop.context.screenshot_image",
          operation: "get_screenshot",
          resourceRef: "screenshot:42",
          effect: "allow",
          expiresAtMs: nowMs + 100,
        },
      ],
    });
    const otherScreenshot = evaluateDesktopToolPolicy({
      requestedBundles: ["desktop.context.screenshot_image"],
      selectedBundles: ["desktop.context.screenshot_image"],
      operation: "get_screenshot",
      resourceRef: "screenshot:43",
      nowMs,
      grants: [
        {
          bundle: "desktop.context.screenshot_image",
          operation: "get_screenshot",
          resourceRef: "screenshot:42",
          effect: "allow",
          expiresAtMs: nowMs + 100,
        },
      ],
    });

    expect(granted.decision).toBe("allow");
    expect(otherScreenshot.decision).toBe("dispatch_required");
  });
});

describe("ACP permission policy", () => {
  it("preserves ACP high-trust auto approval preference order", async () => {
    const { resolveAcpPermission } = await import("../src/runtime/desktop-tool-policy.js");
    const decision = resolveAcpPermission({
      requestId: 42,
      options: [
        { kind: "allow_once", optionId: "once" },
        { kind: "allow_always", optionId: "always" },
      ],
    });

    expect(decision.acpResult).toEqual({
      outcome: { outcome: "selected", optionId: "always" },
    });
    expect(decision.auditEvent).toMatchObject({
      type: "approval.resolved",
      policy: "desktop_high_trust",
      adapterId: "acp",
      requestId: 42,
      optionId: "always",
      automatic: true,
    });
  });

  it("falls back to allow_once, then default allow", async () => {
    const { resolveAcpPermission } = await import("../src/runtime/desktop-tool-policy.js");

    expect(resolveAcpPermission({
      options: [{ kind: "allow_once", optionId: "once" }],
    }).optionId).toBe("once");

    expect(resolveAcpPermission({ options: [] }).optionId).toBe("allow");
  });

  it("keeps external ACP adapters off permanent auto-approval", async () => {
    const { resolveExternalAcpPermission } = await import("../src/runtime/desktop-tool-policy.js");

    const once = resolveExternalAcpPermission({
      adapterId: "hermes",
      options: [
        { kind: "allow_always", optionId: "always" },
        { kind: "allow_once", optionId: "once" },
      ],
    });
    expect("acpResult" in once ? once.acpResult.outcome.optionId : "").toBe("once");

    const rejected = resolveExternalAcpPermission({
      adapterId: "openclaw",
      requestId: 9,
      options: [{ kind: "allow_always", optionId: "always" }],
    });
    expect("acpError" in rejected ? rejected.acpError.code : 0).toBe(-32001);
    expect(rejected.auditEvent).toMatchObject({
      policy: "external_constrained",
      adapterId: "openclaw",
      requestId: 9,
    });
  });
});
