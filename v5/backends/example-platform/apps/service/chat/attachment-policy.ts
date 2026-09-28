/** One duration owner keeps staging and the admissible retry horizon from drifting. */
export const ATTACHMENT_STAGING_TTL_MS = 24 * 60 * 60 * 1_000;
export const CHAT_SEND_RETRY_HORIZON_MS = ATTACHMENT_STAGING_TTL_MS;
export const ATTACHMENT_CONTENT_RETENTION_MS = 30 * 24 * 60 * 60 * 1_000;

export const CHAT_MAX_ATTACHMENTS_PER_MESSAGE = 4;
export const CHAT_MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024;
export const CHAT_ALLOWED_ATTACHMENT_MIME_TYPES = Object.freeze([
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
  "application/pdf",
  "text/plain",
  "text/markdown",
] as const);

export type AllowedChatAttachmentMimeType =
  (typeof CHAT_ALLOWED_ATTACHMENT_MIME_TYPES)[number];

const ALLOWED = new Set<string>(CHAT_ALLOWED_ATTACHMENT_MIME_TYPES);

export const isAllowedChatAttachmentMimeType = (
  value: string,
): value is AllowedChatAttachmentMimeType => ALLOWED.has(value);

// domain-pending(DIV-CHAT-SESSION-001)
export const MAIN_CHAT_ATTACHMENT_SCOPE = "main";
