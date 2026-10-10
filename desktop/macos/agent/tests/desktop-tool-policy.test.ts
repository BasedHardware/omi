import { describe, expect, it } from "vitest";
import {
  DESKTOP_APPROVAL_TTL_MS,
  buildDesktopToolApprovalRequest,
  evaluateDesktopToolPolicy,
} from "../src/runtime/desktop-tool-policy.js";

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

  it("requires an exact resource for automation grants", () => {
    const base = {
      requestedBundles: ["desktop.automation.act"] as const,
      selectedBundles: ["desktop.automation.act"] as const,
      operation: "run_applescript",
      resourceRef: "tell application \\\"Finder\\\" to activate",
      nowMs: 1_000,
    };

    expect(
      evaluateDesktopToolPolicy({
        ...base,
        grants: [{
          bundle: "desktop.automation.act" as const,
          operation: "run_applescript",
          effect: "allow" as const,
          expiresAtMs: 2_000,
        }],
      }).decision,
    ).toBe("dispatch_required");
    expect(
      evaluateDesktopToolPolicy({
        ...base,
        grants: [{
          bundle: "desktop.automation.act" as const,
          operation: "run_applescript",
          resourceRef: base.resourceRef,
          effect: "allow" as const,
          expiresAtMs: 2_000,
        }],
      }).decision,
    ).toBe("allow");
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

describe("desktop tool approval requests", () => {
  const nowMs = 1_700_000_000_000;

  function dispatchRequired(toolName: string, resourceRef?: string) {
    const policy = evaluateDesktopToolPolicy({
      toolName,
      operation: toolName,
      resourceRef,
      selectedBundles: toolName === "send_message"
        ? ["desktop.messaging.send"]
        : toolName === "run_applescript"
          ? ["desktop.automation.act"]
          : toolName === "list_mail_messages"
            ? ["desktop.mail.read"]
            : toolName === "capture_screen"
              ? ["desktop.context.screenshot_image"]
              : toolName === "ui_snapshot"
                ? ["desktop.automation.observe"]
                : ["desktop.messaging.read"],
      nowMs,
    });
    expect(policy.decision).toBe("dispatch_required");
    return policy;
  }

  it("asks a yes/no question bound to the exact send with deny as the default", () => {
    const request = buildDesktopToolApprovalRequest({
      toolName: "send_message",
      toolInput: { to: "+15551234567", text: "Running 10 minutes late", service: "auto", file_path: "/Users/me/Documents/receipt.pdf" },
      policy: dispatchRequired("send_message", "+15551234567"),
      resourceRef: "+15551234567",
      nowMs,
    });

    expect(request).toMatchObject({
      policy: "default_user_approval",
      capability: "desktop.messaging.send",
      operation: "send_message",
      resourceRef: "+15551234567",
      defaultOptionId: "deny",
      requestedAtMs: nowMs,
      expiresAtMs: nowMs + DESKTOP_APPROVAL_TTL_MS,
      previewTruncated: false,
    });
    expect(request.options.map((option) => option.id)).toEqual(["allow_once", "allow_session", "deny"]);
    expect(request.options.find((option) => option.id === "allow_session")).toEqual({
      id: "allow_session",
      effect: "allow",
      scope: "session",
      covers: "any message or attachment to this recipient",
    });
    expect(request.decisionPrompt).toContain("+15551234567");
    // The recipient and the exact text are what the user approves; the
    // attachment path is reduced to its file name.
    expect(request.preview).toEqual({
      to: "+15551234567",
      text: "Running 10 minutes late",
      service: "auto",
      file_path: "receipt.pdf",
    });
  });

  it("asks to read one app's window and shows only the window fields", () => {
    const request = buildDesktopToolApprovalRequest({
      toolName: "ui_snapshot",
      toolInput: { bundle_id: "com.apple.TextEdit", pid: 812, window_title: "Untitled", max_nodes: 100 },
      policy: dispatchRequired("ui_snapshot", "com.apple.textedit"),
      resourceRef: "com.apple.textedit",
      nowMs,
    });

    expect(request).toMatchObject({
      capability: "desktop.automation.observe",
      operation: "ui_snapshot",
      resourceRef: "com.apple.textedit",
      title: "Read an app window",
      decisionPrompt: "Let Omi read the window of com.apple.textedit?",
    });
    // The app is the target row; the pid and the element limit mean nothing to a person.
    expect(request.preview).toEqual({ window_title: "Untitled" });
    expect(request.options.map((option) => option.id)).toEqual(["allow_once", "allow_session", "deny"]);
    expect(request.options.find((option) => option.id === "allow_session")?.covers).toBe("reading any window of this app");
  });

  it("offers a session grant only when there is an exact resource for it to cover", () => {
    const unscopedRead = buildDesktopToolApprovalRequest({
      toolName: "read_message_history",
      toolInput: { limit: 5 },
      policy: dispatchRequired("read_message_history"),
      resourceRef: undefined,
      nowMs,
    });
    const script = "tell application \"Finder\" to activate";
    const scriptRun = buildDesktopToolApprovalRequest({
      toolName: "run_applescript",
      toolInput: { script },
      policy: dispatchRequired("run_applescript", script),
      resourceRef: script,
      nowMs,
    });

    // Nothing to mint a grant against: allow once or deny.
    expect(unscopedRead.options.map((option) => option.id)).toEqual(["allow_once", "deny"]);
    // A script grant covers that script byte for byte, and the card says so.
    expect(scriptRun.options.find((option) => option.id === "allow_session")?.covers).toBe("only this exact script");
  });

  it("keeps fields outside the tool's allowlist out of the preview and bounds long values", () => {
    const script = "tell application \"Finder\"\n".repeat(400);
    const request = buildDesktopToolApprovalRequest({
      toolName: "run_applescript",
      toolInput: { script, timeout_seconds: 10, secret_context: "never shown", nested: { token: "x" } },
      policy: dispatchRequired("run_applescript", script),
      resourceRef: script,
      nowMs,
    });

    expect(Object.keys(request.preview).sort()).toEqual(["script", "timeout_seconds"]);
    expect(request.previewTruncated).toBe(true);
    expect(Buffer.byteLength(String(request.preview.script), "utf8")).toBeLessThanOrEqual(4_096);
    expect(String(request.preview.script).endsWith("…")).toBe(true);
    expect(request.title).toBe("Run an AppleScript");
  });

  it("names the thread for reads and never asks the model's question for it", () => {
    const byHandle = buildDesktopToolApprovalRequest({
      toolName: "read_message_history",
      toolInput: { handle: "alice@example.com", limit: 20 },
      policy: dispatchRequired("read_message_history", "alice@example.com"),
      resourceRef: "alice@example.com",
      nowMs,
    });
    const mail = buildDesktopToolApprovalRequest({
      toolName: "list_mail_messages",
      toolInput: { limit: 30 },
      policy: dispatchRequired("list_mail_messages", "mail:inbox"),
      resourceRef: "mail:inbox",
      nowMs,
    });

    expect(byHandle.capability).toBe("desktop.messaging.read");
    expect(byHandle.decisionPrompt).toContain("alice@example.com");
    expect(mail.capability).toBe("desktop.mail.read");
    expect(mail.resourceRef).toBe("mail:inbox");
    expect(mail.decisionPrompt).toContain("headers only");
  });

  it("asks in plain words before a live screenshot, with nothing technical on the card", () => {
    const request = buildDesktopToolApprovalRequest({
      toolName: "capture_screen",
      toolInput: {},
      policy: dispatchRequired("capture_screen", "screen"),
      resourceRef: "screen",
      nowMs,
    });

    expect(request).toMatchObject({
      capability: "desktop.context.screenshot_image",
      operation: "capture_screen",
      resourceRef: "screen",
      title: "Take a screenshot",
      decisionPrompt: "Let Omi take a screenshot of your whole screen?",
      preview: {},
      previewTruncated: false,
      defaultOptionId: "deny",
    });
    // Each screenshot is asked for on its own: no "Allow for This Chat".
    expect(request.options.map((option) => option.id)).toEqual(["allow_once", "deny"]);
  });

  it("never lets a grant cover a live screenshot, and needs an exact resource for any screen-image grant", () => {
    const grant = {
      bundle: "desktop.context.screenshot_image" as const,
      operation: "capture_screen",
      resourceRef: "screen",
      expiresAtMs: nowMs + 60_000,
      effect: "allow" as const,
    };
    const capture = evaluateDesktopToolPolicy({
      toolName: "capture_screen",
      operation: "capture_screen",
      resourceRef: "screen",
      selectedBundles: ["desktop.context.screenshot_image"],
      grants: [grant],
      nowMs,
    });
    expect(capture.decision).toBe("dispatch_required");

    const storedFrame = (resourceRef: string | undefined) => evaluateDesktopToolPolicy({
      toolName: "get_screenshot",
      operation: "get_screenshot",
      resourceRef: "frame:42",
      selectedBundles: ["desktop.context.screenshot_image"],
      grants: [{ ...grant, operation: "get_screenshot", resourceRef }],
      nowMs,
    });
    expect(storedFrame(undefined).decision).toBe("dispatch_required");
    expect(storedFrame("frame:42").decision).toBe("allow");
  });

  it("refuses to build a request for a decision that was not dispatch_required", () => {
    const allowed = evaluateDesktopToolPolicy({
      toolName: "get_memories",
      selectedBundles: ["desktop.context.local_read"],
    });
    expect(allowed.decision).toBe("allow");
    expect(() => buildDesktopToolApprovalRequest({
      toolName: "get_memories",
      toolInput: {},
      policy: allowed,
      resourceRef: undefined,
      nowMs,
    })).toThrow("dispatch_required");
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
