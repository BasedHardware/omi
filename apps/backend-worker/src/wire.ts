import type {
  ChatCapabilitiesWire,
  ChatGenerationFrame,
  ChatMessage,
  ChatMessageOp,
  StagedChatAttachment,
} from "@omi-core/contracts";

export type StagedAttachment = StagedChatAttachment;

export type { ChatMessage } from "@omi-core/contracts";

type DomainChatCreate = Extract<ChatMessageOp, { op: "create" }>;
export type ChatCreate = Omit<DomainChatCreate, "id"> & { id: string };
export type GenerationEvent = ChatGenerationFrame & { id: string };

export const CHAT_CAPABILITIES: ChatCapabilitiesWire = {
  maxAttachmentsPerMessage: 4,
  maxAttachmentBytes: 52_428_800,
  allowedAttachmentMimeTypes: [
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/markdown",
  ] as readonly string[],
};

export const MAX_CLIENT_ID_LENGTH = 128;

export function isClientId(value: string): boolean {
  return value.length > 0 && value.length <= MAX_CLIENT_ID_LENGTH;
}

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
  retryable = false,
  headers?: HeadersInit
): Response => json({ error: { code, retryable, action } }, status, headers);

export async function withTimeout<T>(
  timeoutMilliseconds: number,
  operation: (signal: AbortSignal) => Promise<T>
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMilliseconds);
  try {
    return await operation(controller.signal);
  } finally {
    clearTimeout(timer);
  }
}

const CHAT_CREATE_REQUIRED = [
  "op",
  "opId",
  "id",
  "at",
  "text",
  "sender",
  "journalRevision",
] as const;
const CHAT_CREATE_OPTIONAL = [
  "type",
  "appId",
  "chatSessionId",
  "messageSource",
  "metadata",
  "attachmentIds",
] as const;
const CHAT_CREATE_KEYS = new Set<string>([
  ...CHAT_CREATE_REQUIRED,
  ...CHAT_CREATE_OPTIONAL,
]);

function isOptionalBoundedString(value: unknown, maxLength: number): boolean {
  return typeof value === "string" && value.length <= maxLength;
}

export function parseChatCreate(value: unknown): ChatCreate | null {
  if (
    value === null ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.getPrototypeOf(value) !== Object.prototype
  ) {
    return null;
  }
  const item = value as Record<string, unknown>;
  if (
    CHAT_CREATE_REQUIRED.some((key) => !Object.hasOwn(item, key)) ||
    Object.keys(item).some((key) => !CHAT_CREATE_KEYS.has(key))
  ) {
    return null;
  }
  if (
    item["op"] !== "create" ||
    !isBoundedString(item["opId"], 128) ||
    !isRecordId(item["id"]) ||
    !Number.isSafeInteger(item["at"]) ||
    (item["at"] as number) < 0 ||
    !Number.isFinite(new Date(item["at"] as number).getTime()) ||
    typeof item["text"] !== "string" ||
    item["text"].length > 32_768 ||
    item["sender"] !== "human" ||
    !Number.isSafeInteger(item["journalRevision"]) ||
    (item["journalRevision"] as number) < 0 ||
    !(
      item["type"] === undefined ||
      item["type"] === "text" ||
      item["type"] === "day_summary"
    ) ||
    !(
      item["appId"] === undefined ||
      item["appId"] === null ||
      isBoundedString(item["appId"], 128)
    ) ||
    !(
      item["chatSessionId"] === undefined ||
      item["chatSessionId"] === null ||
      isBoundedString(item["chatSessionId"], 128)
    ) ||
    !(
      item["messageSource"] === undefined ||
      isOptionalBoundedString(item["messageSource"], 128)
    ) ||
    !(
      item["metadata"] === undefined ||
      item["metadata"] === null ||
      isOptionalBoundedString(item["metadata"], 16_384)
    )
  ) {
    return null;
  }
  let attachmentIds: readonly string[];
  if (item["attachmentIds"] === undefined) {
    attachmentIds = [];
  } else if (
    Array.isArray(item["attachmentIds"]) &&
    item["attachmentIds"].length <= 16 &&
    item["attachmentIds"].every((id) => isBoundedString(id, 128))
  ) {
    attachmentIds = item["attachmentIds"];
  } else {
    return null;
  }
  return {
    op: "create",
    opId: item["opId"],
    id: item["id"],
    at: item["at"] as number,
    text: item["text"],
    sender: "human",
    journalRevision: item["journalRevision"] as number,
    ...(item["type"] === undefined
      ? {}
      : { type: item["type"] as ChatCreate["type"] }),
    ...(item["appId"] === undefined
      ? {}
      : { appId: item["appId"] as string | null }),
    ...(item["chatSessionId"] === undefined
      ? {}
      : { chatSessionId: item["chatSessionId"] as string | null }),
    ...(item["messageSource"] === undefined
      ? {}
      : { messageSource: item["messageSource"] as string }),
    ...(item["metadata"] === undefined
      ? {}
      : { metadata: item["metadata"] as string | null }),
    attachmentIds,
  };
}

export const isChatCreate = (value: unknown): value is ChatCreate =>
  parseChatCreate(value) !== null;

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
