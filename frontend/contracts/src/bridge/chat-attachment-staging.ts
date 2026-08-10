/**
 * Host-owned Chat attachment staging.
 *
 * The surface asks the native host to pick and stage one file. It never sees
 * bytes, a local path, a blob URL, an absolute service origin, a credential,
 * or caller-authored server metadata. The host uploads one multipart `file`
 * to the fixed ratified route and returns only this safe descriptor.
 */

export const BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL = "omiChatAttachmentStaging";
export const BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION = "__omiChatAttachmentStagingReply";

export interface StagedChatAttachment {
  /** Opaque server-issued staging identity. */
  id: string;
  /** Server-normalized safe display name. */
  displayName: string;
  /** Server-sniffed MIME type. */
  mimeType: string;
  sizeBytes: number;
  /** Server-issued ISO-8601 expiry instant; the client does not calculate it. */
  expiresAt: string;
  state: "staged";
}

export interface BridgeChatAttachmentStagingRequest {
  t: "pick-and-stage";
  id: string;
}

export type BridgeChatAttachmentStagingFailureReason =
  | "cancelled"
  | "unavailable"
  | "shell-error";

export type BridgeChatAttachmentStagingReply =
  | { ok: true; id: string; attachment: StagedChatAttachment }
  | { ok: false; id: string; reason: BridgeChatAttachmentStagingFailureReason };

/** Browser/test hosts must supply this port explicitly; there is no fake fallback. */
export interface ChatAttachmentStagingPort {
  isAvailable(): boolean;
  /** `null` means the native picker was cancelled by the user. */
  pickAndStage(): Promise<StagedChatAttachment | null>;
}
