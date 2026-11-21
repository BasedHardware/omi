import { describe, expect, it } from "vitest";
import { evaluateDesktopToolPolicy } from "../src/runtime/desktop-tool-policy.js";
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

  it("allows a compose proposal without dispatch because the person sends it", () => {
    // Apple's compose window is the approval, as on iOS. An Omi card in front
    // of it would ask the person twice for the same effect.
    for (const toolName of ["propose_message", "propose_email"]) {
      const result = evaluateDesktopToolPolicy({
        toolName,
        selectedBundles: ["desktop.compose.propose"],
      });

      expect(result.decision, toolName).toBe("allow");
      expect(result.requiredBundles).toEqual(["desktop.compose.propose"]);
      expect(result.descriptor).toMatchObject({
        riskTier: "medium",
        privacyTier: "local_private",
        approvalPolicy: "allow",
        readOnly: false,
        destructive: false,
      });
      expect(result.reason).toContain("Omi never sends");
    }
  });

  it("denies a compose proposal when the compose bundle was never selected", () => {
    // Selecting the send bundle does not imply the compose bundle, or the reverse.
    const result = evaluateDesktopToolPolicy({
      toolName: "propose_message",
      selectedBundles: ["desktop.messaging.send"],
    });

    expect(result.decision).toBe("deny");
    expect(result.reason).toContain("desktop.compose.propose");
  });

  it("keeps approval for any other write requested beside the compose bundle", () => {
    const result = evaluateDesktopToolPolicy({
      requestedBundles: ["desktop.compose.propose", "desktop.tasks.readwrite"],
      selectedBundles: ["desktop.compose.propose", "desktop.tasks.readwrite"],
    });

    expect(result.decision).toBe("dispatch_required");
    expect(result.descriptor.approvalPolicy).toBe("user_approval");
  });

  it("still requires dispatch when a compose proposal is flagged as an external send", () => {
    const result = evaluateDesktopToolPolicy({
      toolName: "propose_email",
      selectedBundles: ["desktop.compose.propose"],
      externalSend: true,
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

describe("on-device tool manifest", () => {
  it("routes every device tool through the Swift chat tool executor", () => {
    for (const name of [
      "search_contacts",
      "list_message_chats",
      "read_message_history",
      "list_mail_messages",
      "send_message",
      "propose_message",
      "propose_email",
      "run_applescript",
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
  });

  it("describes the compose proposals as never sending, in the model-facing text", () => {
    for (const name of ["propose_message", "propose_email"]) {
      const entry = toolManifestEntry(name);
      expect(entry?.description, name).toContain("does NOT send");
      expect(entry?.description, name).toContain("never sent");
      expect(entry?.promptGuidelines?.join(" "), name).toContain("search_contacts");
      expect(entry?.promptGuidelines?.join(" "), name).toMatch(/Never say the (message|email) was sent/);
      // send_message's grounding rule carries over: no card stands in front of these.
      expect(entry?.promptGuidelines?.join(" "), name).toMatch(/did not name or confirm/);
      expect(entry?.promptGuidelines?.join(" "), name).toContain("recipient_needs_confirmation");
      expect(entry?.runtimePreconditions.join(" "), name).toContain("search_contacts result in the same run");
      expect(entry?.annotations).toMatchObject({ readOnlyHint: false, openWorldHint: false, idempotentHint: false });
      expect(entry?.inputSchema.required).toEqual(["to", "text"]);
      expect(entry?.inputSchema.properties.to).toMatchObject({ type: "array", items: { type: "string" } });
      // Only the coordinator the person is talking to may open a draft.
      expect(entry?.adapters["pi-mono"]?.condition, name).toBe("coordinatorOnly");
      expect(entry?.adapters["omi-tools-stdio"]?.condition, name).toBe("coordinatorOnly");
    }
    expect(toolManifestEntry("propose_email")?.inputSchema.properties).toHaveProperty("subject");
    expect(toolManifestEntry("propose_message")?.inputSchema.properties).not.toHaveProperty("subject");
  });

  it("steers the model to a draft unless the person asked Omi to send", () => {
    expect(toolManifestEntry("propose_message")?.promptGuidelines?.join(" ")).toContain(
      "Use send_message only when the person explicitly asked Omi to send it for them without reviewing it",
    );
    expect(toolManifestEntry("send_message")?.promptGuidelines?.join(" ")).toContain("propose_message");
    expect(toolManifestEntry("run_applescript")?.promptGuidelines?.join(" ")).toContain("propose_email");
    expect(toolManifestEntry("search_contacts")?.description).toContain("propose_email");
  });

  it("routes a request to text someone to propose_message, never through a pre-filed dispatch", () => {
    // A live build answered "text me at <number> '<msg>'" by filing a
    // create_desktop_dispatch approval for send_message, which dead-ended.
    const propose = toolManifestEntry("propose_message");
    const send = toolManifestEntry("send_message");
    const dispatch = toolManifestEntry("create_desktop_dispatch");

    expect(propose?.description).toContain("Use this for any request to text, message or iMessage someone");
    expect(propose?.promptGuidelines?.join(" ")).toContain(
      "This is the default for any request to text, message or iMessage someone",
    );
    expect(propose?.promptGuidelines?.join(" ")).toContain("text me at 555 010 0100 'on my way'");
    expect(propose?.promptGuidelines?.join(" ")).toContain("Never route a message through create_desktop_dispatch");

    // send_message no longer reads as "file an approval dispatch first".
    const sendText = [send?.description, ...(send?.promptGuidelines ?? []), ...(send?.runtimePreconditions ?? [])].join(" ");
    expect(sendText).not.toContain("always requires an approval dispatch");
    expect(sendText).not.toContain("Requires an approval dispatch");
    expect(send?.description).toContain("never file that approval yourself with create_desktop_dispatch");
    expect(send?.description).toContain("for any other request to text or message someone, use propose_message");
    expect(send?.capabilityDoc.bullets.join(" ")).not.toContain("approval dispatch");

    expect(dispatch?.promptGuidelines?.join(" ")).toContain(
      "Never use this to send or approve a text, message or email",
    );
  });

  it("tells the model the person sends an open draft, so \"send it\" never re-opens or sends it", () => {
    // A live build answered "send" after a draft by calling propose_message again.
    for (const name of ["propose_message", "propose_email"]) {
      const guidance = toolManifestEntry(name)?.promptGuidelines?.join(" ") ?? "";
      expect(guidance, name).toContain('If they then say "send" or "send it", tell them to press Send');
      expect(guidance, name).toContain("Never open the same draft again");
      expect(guidance, name).toContain("never call send_message or create_desktop_dispatch for it");
      expect(guidance, name).toContain("draft_already_open");
    }
    expect(toolManifestEntry("send_message")?.promptGuidelines?.join(" ")).toContain(
      "Never use this to send a draft already opened with propose_message",
    );
    expect(toolManifestEntry("send_message")?.promptGuidelines?.join(" ")).toContain("draft_in_messages");
    const propose = toolManifestEntry("propose_message");
    const proposeText = [propose?.description, ...(propose?.promptGuidelines ?? []), ...(propose?.runtimePreconditions ?? [])]
      .join(" ");
    expect(proposeText).not.toContain("sheet");
  });

  it("never assumes Mail is the email app", () => {
    const entry = toolManifestEntry("propose_email");
    const text = [
      entry?.description,
      entry?.promptSnippet,
      ...(entry?.promptGuidelines ?? []),
      ...(entry?.runtimePreconditions ?? []),
      entry?.capabilityDoc.summary,
      ...(entry?.capabilityDoc.bullets ?? []),
    ].join(" ");

    expect(text).toContain("default email app");
    expect(text).toContain("handed_to_email_app");
    expect(text).not.toContain("handed_to_mail");
    expect(text).not.toMatch(/\bMail compose window\b|\bopen in Mail\b|presses Send in Mail\b/);
  });

  it("states the permission each device tool depends on", () => {
    expect(toolManifestEntry("search_contacts")?.runtimePreconditions.join(" ")).toContain("Contacts");
    expect(toolManifestEntry("list_message_chats")?.runtimePreconditions.join(" ")).toContain(
      "Full Disk Access",
    );
    expect(toolManifestEntry("send_message")?.runtimePreconditions.join(" ")).toContain("Automation");
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
