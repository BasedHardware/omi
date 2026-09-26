import { describe, expect, it } from "vitest";

import {
  ATTACHMENT_PRIORITY_INSTRUCTION,
  renderAttachmentsSection,
} from "../src/runtime/attachment-prompt.js";

describe("attachment prompt section", () => {
  it("renders nothing when the message has no attachments", () => {
    expect(renderAttachmentsSection(undefined)).toBe("");
    expect(renderAttachmentsSection([])).toBe("");
  });

  it("puts the priority instruction ahead of the file listing", () => {
    const section = renderAttachmentsSection([
      { attachmentId: "a1", displayName: "deck.pdf", mimeType: "application/pdf", uri: "file:///tmp/deck.pdf" },
    ]);
    expect(section.startsWith("\n\n# Attachments\n")).toBe(true);
    const instructionAt = section.indexOf(ATTACHMENT_PRIORITY_INSTRUCTION);
    const listingAt = section.indexOf("deck.pdf");
    expect(instructionAt).toBeGreaterThan(-1);
    expect(listingAt).toBeGreaterThan(instructionAt);
    expect(section).toContain("file:///tmp/deck.pdf");
  });

  it("names the attachment as the subject and defers the screen to an explicit ask", () => {
    expect(ATTACHMENT_PRIORITY_INSTRUCTION).toContain("primary subject");
    expect(ATTACHMENT_PRIORITY_INSTRUCTION).toMatch(/before consulting screen/);
    expect(ATTACHMENT_PRIORITY_INSTRUCTION).toMatch(/unless the user asks about the screen explicitly/);
  });
});
