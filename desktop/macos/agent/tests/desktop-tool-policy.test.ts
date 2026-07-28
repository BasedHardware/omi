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

  it("requires dispatch for task writes by default", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "complete_task",
      selectedBundles: ["desktop.tasks.readwrite"],
    });

    expect(result.decision).toBe("dispatch_required");
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
