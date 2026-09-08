import { listBoundAttachments } from "./attachments";
import { CHAT_CAPABILITIES } from "./wire";

export const GENERATION_ATTACHMENT_TEXT_BUDGET = 32 * 1024;
export const GENERATION_HISTORY_TEXT_BUDGET = 32 * 1024;
export const GENERATION_HISTORY_MESSAGE_LIMIT = 40;

export type GenerationHistoryMessage = {
  role: "user" | "assistant";
  content: string;
};

export type GenerationPromptResult =
  | { kind: "ok"; prompt: string; history: GenerationHistoryMessage[] }
  | { kind: "fail" }
  | { kind: "unavailable" };

export function isGenerationTextMimeType(mimeType: string): boolean {
  return (
    CHAT_CAPABILITIES.allowedAttachmentMimeTypes.includes(mimeType) &&
    mimeType.startsWith("text/")
  );
}

export function isVisibleGenerationText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export async function composeGenerationPrompt(
  db: D1Database,
  r2: R2Bucket | undefined,
  accountId: string,
  messageId: string,
  userText: string
): Promise<GenerationPromptResult> {
  const bound = await listBoundAttachments(db, accountId, messageId);
  if (
    r2 === undefined &&
    bound.some((attachment) => isGenerationTextMimeType(attachment.mediaType))
  ) {
    return { kind: "unavailable" };
  }
  const excerpts: string[] = [];
  let usedBytes = 0;

  for (const attachment of bound) {
    if (!isGenerationTextMimeType(attachment.mediaType)) continue;
    const remaining = GENERATION_ATTACHMENT_TEXT_BUDGET - usedBytes;
    if (remaining <= 0) continue;
    const excerpt = await readTextExcerpt(r2, attachment.r2Key, remaining);
    if (excerpt === null || !isVisibleGenerationText(excerpt)) continue;
    usedBytes += utf8Bytes(excerpt);
    excerpts.push(
      isVisibleGenerationText(attachment.displayName)
        ? `Attachment "${attachment.displayName}":\n${excerpt}`
        : excerpt
    );
  }

  const parts: string[] = [];
  if (isVisibleGenerationText(userText)) parts.push(userText);
  parts.push(...excerpts);
  const prompt = parts.join("\n\n");
  if (!isVisibleGenerationText(prompt)) {
    return { kind: "fail" };
  }
  return {
    kind: "ok",
    prompt,
    history: await readGenerationHistory(db, accountId, messageId),
  };
}

async function readGenerationHistory(
  db: D1Database,
  accountId: string,
  messageId: string
): Promise<GenerationHistoryMessage[]> {
  const result = await db
    .prepare(
      `SELECT prior.sender, prior.text
       FROM chat_messages AS prior
       JOIN chat_messages AS current ON current.id = ? AND current.account_id = ?
       WHERE prior.account_id = current.account_id AND prior.position < current.position
         AND ${recoveredPayloadTextKeySql(
           "prior",
           "chatSessionId"
         )} IS ${recoveredPayloadTextKeySql("current", "chatSessionId")}
         AND ${recoveredPayloadTextKeySql(
           "prior",
           "appId"
         )} IS ${recoveredPayloadTextKeySql("current", "appId")}
         AND (prior.sender = 'human' OR (prior.sender = 'ai' AND prior.generation_outcome = 'completed'))
       ORDER BY prior.position DESC
       LIMIT ?`
    )
    .bind(messageId, accountId, GENERATION_HISTORY_MESSAGE_LIMIT)
    .all<{ sender: "human" | "ai"; text: string }>();
  const history: GenerationHistoryMessage[] = [];
  let remaining = GENERATION_HISTORY_TEXT_BUDGET;
  for (const row of result.results) {
    if (!isVisibleGenerationText(row.text)) continue;
    const size = utf8Bytes(row.text);
    if (size > remaining) break;
    remaining -= size;
    history.push({
      role: row.sender === "human" ? "user" : "assistant",
      content: row.text,
    });
  }
  return history.reverse();
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

export function recoveredPayloadSql(alias: string): string {
  const payload = `${alias}.payload`;
  const admission = `COALESCE((SELECT CASE WHEN json_valid(admissions.payload) THEN admissions.payload END FROM chat_admissions AS admissions WHERE admissions.account_id = ${alias}.account_id AND (admissions.message_id = ${alias}.id OR admissions.generation_id = ${alias}.id) LIMIT 1), '{}')`;
  return `CASE WHEN json_valid(${payload}) THEN CASE WHEN json_type(${payload}) = 'object' THEN ${payload} ELSE ${admission} END ELSE ${admission} END`;
}

export function recoveredPayloadTextKeySql(
  alias: string,
  key: "chatSessionId" | "appId"
): string {
  return `(SELECT CASE WHEN type = 'text' THEN value END FROM json_each(${recoveredPayloadSql(
    alias
  )}) WHERE key = '${key}' ORDER BY id DESC LIMIT 1)`;
}

function utf8Bytes(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}
