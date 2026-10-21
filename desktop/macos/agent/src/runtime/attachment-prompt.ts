import { stableJsonStringify } from "./kernel-support.js";

export interface PromptAttachment {
  attachmentId: string;
  displayName: string;
  mimeType: string;
  sizeBytes?: number;
  uri?: string;
}

/**
 * The instruction that rides with every attached file.
 *
 * A file the user just attached is the subject of the message. Without saying so, a
 * bare "look" or "what do you think of this" next to a PDF was read against the
 * ambient screen context that precedes it in the prompt, and the model answered about
 * the desktop ("I see a blank page") instead of the file. The rule is stated once, in
 * plain terms, ahead of the listing so it applies to every reference below it.
 */
export const ATTACHMENT_PRIORITY_INSTRUCTION =
  "The user attached these files to this exact message. They are the primary subject of the message: " +
  'read "this", "it", "look", "what do you think", and similar references as pointing at the attachments, ' +
  "and inspect their contents (uri / local path) before consulting screen, work, or memory context. " +
  "Do not describe the screen unless the user asks about the screen explicitly.";

/** Renders the `# Attachments` prompt section, or an empty string when there is nothing attached. */
export function renderAttachmentsSection(attachments: readonly PromptAttachment[] | undefined): string {
  if (!attachments?.length) return "";
  return `\n\n# Attachments\n${ATTACHMENT_PRIORITY_INSTRUCTION}\n${stableJsonStringify(attachments)}`;
}
