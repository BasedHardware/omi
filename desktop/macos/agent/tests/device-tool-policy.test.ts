import { describe, expect, it } from "vitest";
import { evaluateDesktopToolPolicy, type DesktopCoordinatorBundle } from "../src/runtime/desktop-tool-policy.js";
import { toolManifestEntry } from "../src/runtime/omi-tool-manifest.js";

const HOUR_MS = 60 * 60 * 1000;

describe("on-device tool surface policy", () => {
  it("allows contact resolution with only the contacts bundle", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "search_contacts",
      selectedBundles: ["desktop.contacts.read"],
    });

    expect(result.decision).toBe("allow");
    expect(result.requiredBundles).toEqual(["desktop.contacts.read"]);
    expect(result.descriptor.readOnly).toBe(true);
  });

  it("requires dispatch to read message history even though it is read-only", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "read_message_history",
      selectedBundles: ["desktop.messaging.read"],
    });

    expect(result.decision).toBe("dispatch_required");
    expect(result.descriptor.privacyTier).toBe("sensitive");
  });

  it("requires dispatch to list mail even though it is read-only", () => {
    // Who is writing to the user and about what is the same class of disclosure
    // as a message thread, so mail headers take the same durable approval
    // rather than riding along as an ordinary local read.
    const result = evaluateDesktopToolPolicy({
      toolName: "list_mail_messages",
      selectedBundles: ["desktop.mail.read"],
    });

    expect(result.decision).toBe("dispatch_required");
    expect(result.descriptor.privacyTier).toBe("sensitive");
    expect(result.descriptor.readOnly).toBe(true);
  });

  it("denies a mail read when the mail bundle was never selected", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "list_mail_messages",
      selectedBundles: ["desktop.context.local_read"],
    });

    expect(result.decision).toBe("deny");
    expect(result.reason).toContain("desktop.mail.read");
  });

  it("does not let a messaging grant authorize a mail read", () => {
    // Separate bundles, separate approvals: agreeing to let the agent read a
    // text thread is not agreeing to let it read the inbox.
    const result = evaluateDesktopToolPolicy({
      toolName: "list_mail_messages",
      selectedBundles: ["desktop.messaging.read"],
    });

    expect(result.decision).toBe("deny");
  });

  it("requires dispatch before sending a message", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "send_message",
      selectedBundles: ["desktop.messaging.send"],
    });

    expect(result.decision).toBe("dispatch_required");
    expect(result.descriptor.riskTier).toBe("high");
    expect(result.descriptor.readOnly).toBe(false);
  });

  it("denies a send when the messaging bundle was never selected", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "send_message",
      selectedBundles: ["desktop.context.local_read"],
    });

    expect(result.decision).toBe("deny");
    expect(result.reason).toContain("desktop.messaging.send");
  });

  it("honors a scoped send grant bound to one recipient", () => {
    const nowMs = 1_000_000;
    const request = {
      toolName: "send_message",
      selectedBundles: ["desktop.messaging.send"] as const,
      resourceRef: "+15550100",
      nowMs,
      grants: [
        {
          bundle: "desktop.messaging.send" as const,
          resourceRef: "+15550100",
          expiresAtMs: nowMs + HOUR_MS,
          effect: "allow" as const,
        },
      ],
    };

    expect(evaluateDesktopToolPolicy(request).decision).toBe("allow");

    // The same grant must not cover a different recipient.
    expect(
      evaluateDesktopToolPolicy({ ...request, resourceRef: "+15550199" }).decision,
    ).toBe("dispatch_required");
  });

  it("does not let an unscoped send grant cover any recipient", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "send_message",
      selectedBundles: ["desktop.messaging.send"],
      resourceRef: "+15550100",
      grants: [
        {
          bundle: "desktop.messaging.send",
          expiresAtMs: Date.now() + HOUR_MS,
          effect: "allow",
        },
      ],
    });

    expect(result.decision).toBe("dispatch_required");
  });

  it("stops honoring a send grant once it expires", () => {
    const nowMs = 1_000_000;
    const result = evaluateDesktopToolPolicy({
      toolName: "send_message",
      selectedBundles: ["desktop.messaging.send"],
      nowMs,
      grants: [
        {
          bundle: "desktop.messaging.send",
          expiresAtMs: nowMs - 1,
          effect: "allow",
        },
      ],
    });

    expect(result.decision).toBe("dispatch_required");
  });

  it("requires dispatch for AppleScript actuation in a production bundle", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "run_applescript",
      selectedBundles: ["desktop.automation.act"],
      isDevBundle: false,
    });

    // Unlike act_dev_only this is reachable in a release build, but never
    // without an approval record.
    expect(result.decision).toBe("dispatch_required");
    expect(result.requiredBundles).toEqual(["desktop.automation.act"]);
  });

  it("keeps the dev-only automation bundle denied outside dev bundles", () => {
    const result = evaluateDesktopToolPolicy({
      requestedBundles: ["desktop.automation.act_dev_only"],
      selectedBundles: ["desktop.automation.act_dev_only"],
      isDevBundle: false,
    });

    expect(result.decision).toBe("deny");
    expect(result.reason).toContain("dev/test bundles");
  });
});

describe("ui_snapshot policy", () => {
  const nowMs = 1_000_000;
  const observe = ["desktop.automation.observe"] as const;
  const grant = (overrides: Partial<{ bundle: DesktopCoordinatorBundle; resourceRef: string; expiresAtMs: number }> = {}) => ({
    bundle: "desktop.automation.observe" as DesktopCoordinatorBundle,
    resourceRef: "com.apple.textedit",
    expiresAtMs: nowMs + HOUR_MS,
    effect: "allow" as const,
    ...overrides,
  });
  const snapshot = (resourceRef: string | undefined, grants: ReturnType<typeof grant>[] = []) =>
    evaluateDesktopToolPolicy({
      toolName: "ui_snapshot",
      operation: "ui_snapshot",
      selectedBundles: observe,
      resourceRef,
      nowMs,
      grants,
    });

  it("requires dispatch even though it only reads", () => {
    const result = snapshot("com.apple.textedit");

    expect(result.decision).toBe("dispatch_required");
    expect(result.requiredBundles).toEqual(["desktop.automation.observe"]);
    expect(result.descriptor).toMatchObject({ riskTier: "high", privacyTier: "sensitive", readOnly: true });
  });

  it("is denied when the observe bundle was never selected", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "ui_snapshot",
      selectedBundles: ["desktop.automation.act"],
      resourceRef: "com.apple.textedit",
    });

    expect(result.decision).toBe("deny");
    expect(result.reason).toContain("desktop.automation.observe");
  });

  it("lets a grant for one app cover that app and no other", () => {
    expect(snapshot("com.apple.textedit", [grant()]).decision).toBe("allow");
    expect(snapshot("com.apple.notes", [grant()]).decision).toBe("dispatch_required");
  });

  it("never lets an unscoped or expired observe grant cover anything", () => {
    const unscoped = { ...grant(), resourceRef: undefined };

    expect(snapshot("com.apple.textedit", [unscoped]).decision).toBe("dispatch_required");
    expect(snapshot("com.apple.textedit", [grant({ expiresAtMs: nowMs - 1 })]).decision).toBe("dispatch_required");
  });

  it("does not let an act or messaging grant authorize a read of an app", () => {
    const act = grant({ bundle: "desktop.automation.act" });
    const messaging = grant({ bundle: "desktop.messaging.read" });

    expect(snapshot("com.apple.textedit", [act, messaging]).decision).toBe("dispatch_required");
  });

  it("hard-denies the refused apps and malformed bundle ids before any card", () => {
    for (const refused of ["com.apple.terminal", "com.googlecode.iterm2", "com.1password.1password", "com.apple.securityagent", "com.omi.desktop-dev", "com.omi.computer-macos"]) {
      const result = snapshot(refused, [grant({ resourceRef: refused })]);
      expect(result.decision, refused).toBe("deny");
      expect(result.reason).toContain("never reads");
    }
    for (const malformed of [undefined, "TextEdit", "com..apple", "com.apple.text edit"]) {
      expect(snapshot(malformed).decision, String(malformed)).toBe("deny");
    }
  });

  it("lets System Settings reach the card because only some of its panes are refused", () => {
    expect(snapshot("com.apple.systempreferences").decision).toBe("dispatch_required");
  });
});

describe("on-device tool manifest", () => {
  it("routes every device tool through the Swift chat tool executor", () => {
    for (const name of [
      "search_contacts",
      "list_message_chats",
      "read_message_history",
      "list_mail_messages",
      "send_message",
      "run_applescript",
      "ui_snapshot",
    ]) {
      const entry = toolManifestEntry(name);
      expect(entry, `${name} is missing from the manifest`).toBeDefined();
      expect(entry?.executor.kind).toBe("swiftTool");
    }
  });

  it("marks reads read-only and effects open-world", () => {
    expect(toolManifestEntry("list_message_chats")?.annotations.readOnlyHint).toBe(true);
    expect(toolManifestEntry("read_message_history")?.annotations.readOnlyHint).toBe(true);
    expect(toolManifestEntry("search_contacts")?.annotations.readOnlyHint).toBe(true);
    expect(toolManifestEntry("send_message")?.annotations.openWorldHint).toBe(true);
    expect(toolManifestEntry("run_applescript")?.annotations.openWorldHint).toBe(true);
    expect(toolManifestEntry("ui_snapshot")?.annotations).toMatchObject({ readOnlyHint: true, openWorldHint: false });
  });

  it("states the permission each device tool depends on", () => {
    expect(toolManifestEntry("search_contacts")?.runtimePreconditions.join(" ")).toContain("Contacts");
    expect(toolManifestEntry("list_message_chats")?.runtimePreconditions.join(" ")).toContain(
      "Full Disk Access",
    );
    expect(toolManifestEntry("send_message")?.runtimePreconditions.join(" ")).toContain("Automation");
    expect(toolManifestEntry("ui_snapshot")?.runtimePreconditions.join(" ")).toContain("Accessibility");
  });

  it("offers the device tool permissions through request_permission", () => {
    const permissionEnum = (toolManifestEntry("request_permission")?.inputSchema.properties.type as {
      enum: string[];
    }).enum;

    expect(permissionEnum).toContain("contacts");
    expect(permissionEnum).toContain("calendars");
    expect(permissionEnum).toContain("reminders");
    expect(permissionEnum).toContain("photos");
  });
});
