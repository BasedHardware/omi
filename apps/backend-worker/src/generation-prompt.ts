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
  return typeof value === "string" && visibleGenerationTrim(value).length > 0;
}

export function visibleGenerationTrim(value: string): string {
  return value.replace(/^[\s\u0085]+|[\s\u0085]+$/gu, "");
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
    if (remaining <= 0) {
      if (!(await boundTextObjectPresent(r2, attachment.r2Key))) {
        return { kind: "fail" };
      }
      continue;
    }
    const excerpt = await readTextExcerpt(r2, attachment.r2Key, remaining);
    if (excerpt.kind === "missing") {
      return { kind: "fail" };
    }
    if (excerpt.kind !== "text" || !isVisibleGenerationText(excerpt.value))
      continue;
    usedBytes += utf8Bytes(excerpt.value);
    excerpts.push(
      isVisibleGenerationText(attachment.displayName)
        ? `Attachment "${visibleGenerationTrim(attachment.displayName)}":\n${
            excerpt.value
          }`
        : excerpt.value
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
       WHERE prior.account_id = current.account_id
         AND prior.position < current.position
         AND ${recoveredPayloadTextKeySql(
           "prior",
           "chatSessionId"
         )} IS ${recoveredPayloadTextKeySql("current", "chatSessionId")}
         AND ${recoveredPayloadTextKeySql(
           "prior",
           "appId"
         )} IS ${recoveredPayloadTextKeySql("current", "appId")}
         AND (prior.sender = 'human' OR (prior.sender = 'ai' AND prior.generation_outcome = 'completed'))
         AND ${visibleStoredTextSql("prior")}
       ORDER BY prior.created_at DESC, prior.position DESC
       LIMIT ?`
    )
    .bind(messageId, accountId, GENERATION_HISTORY_MESSAGE_LIMIT)
    .all<{ sender: "human" | "ai"; text: string }>();
  const history: GenerationHistoryMessage[] = [];
  let remaining = GENERATION_HISTORY_TEXT_BUDGET;
  const rows = result.results;
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index]!;
    if (!isVisibleGenerationText(row.text)) continue;
    const visible = visibleGenerationTrim(row.text);
    const visibleSize = utf8Bytes(visible);
    if (visibleSize <= remaining) {
      remaining -= visibleSize;
      history.push({
        role: row.sender === "human" ? "user" : "assistant",
        content: visible,
      });
      continue;
    }
    const prefix = utf8Prefix(row.text, remaining);
    if (isVisibleGenerationText(prefix)) {
      history.push({
        role: row.sender === "human" ? "user" : "assistant",
        content: prefix,
      });
      break;
    }
    const visiblePrefix = utf8Prefix(visible, remaining);
    if (isVisibleGenerationText(visiblePrefix) && index === rows.length - 1) {
      history.push({
        role: row.sender === "human" ? "user" : "assistant",
        content: visiblePrefix,
      });
      break;
    }
  }
  return history.reverse();
}

async function boundTextObjectPresent(
  r2: R2Bucket | undefined,
  r2Key: string
): Promise<boolean> {
  if (r2 === undefined) return false;
  try {
    return (await r2.get(r2Key, { range: { offset: 0, length: 1 } })) !== null;
  } catch {
    return false;
  }
}

type TextExcerpt =
  | { kind: "text"; value: string }
  | { kind: "empty" }
  | { kind: "missing" };

type TextExcerptChunk =
  | {
      kind: "text";
      value: string;
      byteLength: number;
      truncated: boolean;
    }
  | { kind: "empty" }
  | { kind: "missing" };

async function readTextExcerpt(
  r2: R2Bucket | undefined,
  r2Key: string,
  maxBytes: number
): Promise<TextExcerpt> {
  if (r2 === undefined || maxBytes <= 0) return { kind: "empty" };
  let offset = 0;
  let skipped = 0;
  for (;;) {
    const chunk = await readTextExcerptRange(r2, r2Key, maxBytes, offset);
    if (chunk.kind !== "text") return chunk;
    const visible = visibleGenerationTrim(chunk.value);
    if (isVisibleGenerationText(visible)) {
      return { kind: "text", value: utf8Prefix(visible, maxBytes) };
    }
    if (!chunk.truncated || chunk.byteLength === 0) return { kind: "empty" };
    skipped += chunk.byteLength;
    if (skipped > GENERATION_ATTACHMENT_TEXT_BUDGET) return { kind: "empty" };
    offset += chunk.byteLength;
  }
}

async function readTextExcerptRange(
  r2: R2Bucket,
  r2Key: string,
  maxBytes: number,
  offset: number
): Promise<TextExcerptChunk> {
  try {
    const object = await r2.get(r2Key, {
      range: { offset, length: maxBytes },
    });
    if (object === null) return { kind: "missing" };
    const bytes = new Uint8Array(await object.arrayBuffer());
    if (bytes.byteLength === 0) return { kind: "empty" };
    if (bytes.includes(0)) return { kind: "missing" };
    const truncated =
      typeof object.size === "number" &&
      object.size > offset + bytes.byteLength;
    try {
      return {
        kind: "text",
        value: new TextDecoder("utf-8", { fatal: true }).decode(
          bytes,
          truncated ? { stream: true } : undefined
        ),
        byteLength: bytes.byteLength,
        truncated,
      };
    } catch {
      return { kind: "missing" };
    }
  } catch {
    return { kind: "missing" };
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
  const extracted = `(SELECT CASE WHEN type = 'text' THEN value END FROM json_each(${recoveredPayloadSql(
    alias
  )}) WHERE key = '${key}' ORDER BY id DESC LIMIT 1)`;
  if (key !== "chatSessionId") return extracted;
  return `(SELECT CASE WHEN typeof(value) = 'text' AND length(CAST(trim(value) AS BLOB)) > 0 AND trim(value) != 'chat-main' THEN value END FROM (SELECT ${extracted} AS value))`;
}

export function visibleStoredTextTrimSql(expr: string): string {
  return `trim(${expr}, char(9,10,11,12,13,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288,65279))`;
}

function visibleStoredTextSql(alias: string): string {
  return `length(${visibleStoredTextTrimSql(`${alias}.text`)}) > 0`;
}

function utf8Bytes(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function utf8Prefix(value: string, maxBytes: number): string {
  if (maxBytes <= 0) return "";
  const bytes = new TextEncoder().encode(value);
  if (bytes.byteLength <= maxBytes) return value;
  return new TextDecoder("utf-8", { fatal: true }).decode(
    bytes.subarray(0, maxBytes),
    { stream: true }
  );
}
