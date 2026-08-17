import type {
  ChatCapabilitiesWire,
  ChatGenerationFrame,
  ChatMessage,
  ChatMessageOp,
} from "@omi-core/contracts";

export type { ChatMessage } from "@omi-core/contracts";

type DomainChatCreate = Extract<ChatMessageOp, { op: "create" }>;
export type ChatCreate = Omit<DomainChatCreate, "id"> & { id: string };
export type GenerationEvent = ChatGenerationFrame & { id: string };

export const CHAT_CAPABILITIES: ChatCapabilitiesWire = {
  maxAttachmentsPerMessage: 0,
  maxAttachmentBytes: 0,
  allowedAttachmentMimeTypes: [] as string[],
};

export const json = (
  value: unknown,
  status = 200,
  headers?: HeadersInit
): Response =>
  Response.json(value, {
    status,
    headers: { "cache-control": "no-store", ...headers },
  });

export const backendError = (
  code: string,
  action: string,
  status: number,
  retryable = false
): Response => json({ error: { code, retryable, action } }, status);

export const isChatCreate = (value: unknown): value is ChatCreate => {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    return false;
  const item = value as Record<string, unknown>;
  return (
    item["op"] === "create" &&
    isBoundedString(item["opId"], 128) &&
    isRecordId(item["id"]) &&
    Number.isSafeInteger(item["at"]) &&
    (item["at"] as number) >= 0 &&
    isBoundedString(item["text"], 32_768) &&
    item["sender"] === "human" &&
    Number.isSafeInteger(item["journalRevision"]) &&
    (item["journalRevision"] as number) >= 0 &&
    (item["type"] === undefined ||
      item["type"] === "text" ||
      item["type"] === "day_summary") &&
    (item["appId"] === undefined ||
      item["appId"] === null ||
      isBoundedString(item["appId"], 128)) &&
    (item["chatSessionId"] === undefined ||
      item["chatSessionId"] === null ||
      isBoundedString(item["chatSessionId"], 128)) &&
    (item["messageSource"] === undefined ||
      isBoundedString(item["messageSource"], 128)) &&
    (item["metadata"] === undefined ||
      item["metadata"] === null ||
      isBoundedString(item["metadata"], 16_384)) &&
    Array.isArray(item["attachmentIds"]) &&
    item["attachmentIds"].length <= 16 &&
    item["attachmentIds"].every((id) => isBoundedString(id, 128))
  );
};

function isBoundedString(value: unknown, maxLength: number): value is string {
  return (
    typeof value === "string" && value.length > 0 && value.length <= maxLength
  );
}

function isRecordId(value: unknown): value is string {
  if (!isBoundedString(value, 128)) return false;
  return (
    /^[a-z]{2,12}(?:-[a-z]{2,12}){2,4}$/.test(value) ||
    /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
      value
    ) ||
    /^[A-Za-z0-9_-]{4,128}$/.test(value)
  );
}
