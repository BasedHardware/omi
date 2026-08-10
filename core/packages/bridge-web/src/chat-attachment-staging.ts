/** Web binding for host-owned native Chat attachment pick-and-stage. */

import {
  BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL,
  BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION,
  type BridgeChatAttachmentStagingReply,
  type BridgeChatAttachmentStagingRequest,
  type ChatAttachmentStagingPort,
  type StagedChatAttachment,
} from "@omi-core/contracts";

interface ReplyHandler {
  postMessage(message: unknown): Promise<unknown>;
}

interface OneWayChannel {
  postMessage(message: string): void;
}

type Transport =
  | { kind: "reply"; handler: ReplyHandler }
  | { kind: "one-way"; channel: OneWayChannel };

function detectTransport(): Transport | null {
  const host = globalThis as unknown as {
    webkit?: { messageHandlers?: Record<string, ReplyHandler | undefined> };
  } & Record<string, unknown>;
  const oneWay = host[BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL] as OneWayChannel | undefined;
  if (oneWay && typeof oneWay.postMessage === "function") return { kind: "one-way", channel: oneWay };
  const reply = host.webkit?.messageHandlers?.[BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL];
  return reply && typeof reply.postMessage === "function" ? { kind: "reply", handler: reply } : null;
}

export function isBridgeChatAttachmentStagingAvailable(): boolean {
  return detectTransport() !== null;
}

function isDescriptor(value: unknown): value is StagedChatAttachment {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item["id"] === "string" && item["id"] !== "" && !item["id"].includes("://") &&
    typeof item["displayName"] === "string" && item["displayName"] !== "" &&
    !/[\\/\u0000-\u001f]/u.test(item["displayName"]) &&
    typeof item["mimeType"] === "string" && /^[^\s/]+\/[^\s/]+$/u.test(item["mimeType"]) &&
    Number.isSafeInteger(item["sizeBytes"]) && (item["sizeBytes"] as number) >= 0 &&
    typeof item["expiresAt"] === "string" && item["expiresAt"] !== "" &&
    !Number.isNaN(Date.parse(item["expiresAt"])) &&
    item["state"] === "staged"
  );
}

function parseReply(raw: unknown, id: string): StagedChatAttachment | null {
  let value = raw;
  if (typeof raw === "string") {
    try {
      value = JSON.parse(raw) as unknown;
    } catch {
      throw new Error("attachment staging host returned malformed JSON");
    }
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("attachment staging host returned a malformed reply");
  }
  const reply = value as BridgeChatAttachmentStagingReply;
  if (reply.id !== id) throw new Error("attachment staging host returned a mismatched id");
  if (reply.ok === false) {
    if (reply.reason === "cancelled") return null;
    throw new Error(`attachment staging host failed: ${reply.reason}`);
  }
  if (reply.ok !== true || !isDescriptor(reply.attachment)) {
    throw new Error("attachment staging host returned an unsafe descriptor");
  }
  return {
    id: reply.attachment.id,
    displayName: reply.attachment.displayName,
    mimeType: reply.attachment.mimeType,
    sizeBytes: reply.attachment.sizeBytes,
    expiresAt: reply.attachment.expiresAt,
    state: "staged",
  };
}

export function bridgeChatAttachmentStagingPort(): ChatAttachmentStagingPort {
  const transport = detectTransport();
  let sequence = 0;
  const pending = new Map<string, (reply: unknown) => void>();
  if (transport?.kind === "one-way") {
    (globalThis as unknown as Record<string, unknown>)[BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION] = (
      id: unknown,
      reply: unknown,
    ): void => {
      if (typeof id !== "string") return;
      const settle = pending.get(id);
      if (!settle) return;
      pending.delete(id);
      settle(reply);
    };
  }
  return {
    isAvailable: () => transport !== null,
    async pickAndStage() {
      if (!transport) {
        throw new Error(`attachment staging unavailable: no "${BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL}" channel`);
      }
      sequence += 1;
      const id = `a${sequence}`;
      const request: BridgeChatAttachmentStagingRequest = { t: "pick-and-stage", id };
      if (transport.kind === "reply") {
        return parseReply(await transport.handler.postMessage(request), id);
      }
      const reply = await new Promise<unknown>((resolve) => {
        pending.set(id, resolve);
        transport.channel.postMessage(JSON.stringify(request));
      });
      return parseReply(reply, id);
    },
  };
}
