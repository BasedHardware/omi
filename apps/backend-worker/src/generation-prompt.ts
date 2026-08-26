import { listBoundAttachments } from "./attachments";
import { CHAT_CAPABILITIES } from "./wire";

export const GENERATION_ATTACHMENT_TEXT_BUDGET = 32 * 1024;

export type GenerationPromptResult =
  | { kind: "ok"; prompt: string }
  | { kind: "fail" };

export function isGenerationTextMimeType(mimeType: string): boolean {
  return (
    CHAT_CAPABILITIES.allowedAttachmentMimeTypes.includes(mimeType) &&
    mimeType.startsWith("text/")
  );
}

export async function composeGenerationPrompt(
  db: D1Database,
  r2: R2Bucket | undefined,
  accountId: string,
  messageId: string,
  userText: string
): Promise<GenerationPromptResult> {
  const bound = await listBoundAttachments(db, accountId, messageId);
  const excerpts: string[] = [];
  let usedBytes = 0;
  let textFiles = 0;
  let loadedTextFiles = 0;

  for (const attachment of bound) {
    if (!isGenerationTextMimeType(attachment.mediaType)) continue;
    textFiles += 1;
    const remaining = GENERATION_ATTACHMENT_TEXT_BUDGET - usedBytes;
    if (remaining <= 0) continue;
    const excerpt = await readTextExcerpt(r2, attachment.r2Key, remaining);
    if (excerpt === null) continue;
    loadedTextFiles += 1;
    usedBytes += utf8Bytes(excerpt);
    excerpts.push(`Attachment "${attachment.displayName}":\n${excerpt}`);
  }

  const parts: string[] = [];
  if (userText.length > 0) parts.push(userText);
  parts.push(...excerpts);
  const prompt = parts.join("\n\n");
  if (prompt.length === 0 && (textFiles === 0 || loadedTextFiles === 0)) {
    return { kind: "fail" };
  }
  return { kind: "ok", prompt };
}

async function readTextExcerpt(
  r2: R2Bucket | undefined,
  r2Key: string,
  maxBytes: number
): Promise<string | null> {
  if (r2 === undefined || maxBytes <= 0) return null;
  try {
    const object = await r2.get(r2Key, {
      range: { offset: 0, length: maxBytes },
    });
    if (object === null) return null;
    const bytes = new Uint8Array(await object.arrayBuffer());
    if (bytes.byteLength === 0 || bytes.includes(0)) return null;
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      return null;
    }
  } catch {
    return null;
  }
}

function utf8Bytes(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}
