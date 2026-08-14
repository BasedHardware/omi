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

const STAGING_REGISTRY = Symbol.for("@omi-core/bridge-web/chat-attachment-staging-registry");

interface PendingStagingReply {
  resolve(reply: unknown): void;
  reject(error: Error): void;
}

interface RealmStagingRegistry {
  sequence: number;
  readonly pending: Map<string, PendingStagingReply>;
  readonly sink: (id: unknown, reply: unknown) => void;
}

function realmStagingRegistry(): RealmStagingRegistry {
  const realm = globalThis as unknown as Record<PropertyKey, unknown>;
  const existing = realm[STAGING_REGISTRY] as RealmStagingRegistry | undefined;
  if (existing !== undefined) return existing;
  const pending = new Map<string, PendingStagingReply>();
  const registry: RealmStagingRegistry = {
    sequence: 0,
    pending,
    sink(id, reply) {
      if (typeof id !== "string") return;
      const settle = pending.get(id);
      if (!settle) return;
      pending.delete(id);
      settle.resolve(reply);
    },
  };
  realm[STAGING_REGISTRY] = registry;
  return registry;
}

function installRealmStagingSink(registry: RealmStagingRegistry): void {
  const realm = globalThis as unknown as Record<string, unknown>;
  if (realm[BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION] === registry.sink) return;
  for (const pending of registry.pending.values()) {
    pending.reject(new Error("attachment staging reply sink was replaced"));
  }
  registry.pending.clear();
  realm[BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION] = registry.sink;
}

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
  const expiresAt = item["expiresAt"];
  return (
    typeof item["id"] === "string" &&
    /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(item["id"]) &&
    typeof item["mimeType"] === "string" && item["mimeType"].length <= 127 &&
    /^[!#$%&'*+.^_`|~0-9A-Za-z-]+\/[!#$%&'*+.^_`|~0-9A-Za-z-]+$/u.test(item["mimeType"]) &&
    Number.isSafeInteger(item["sizeBytes"]) && (item["sizeBytes"] as number) > 0 &&
    typeof expiresAt === "string" && expiresAt.length === 24 &&
    !Number.isNaN(Date.parse(expiresAt)) && new Date(expiresAt).toISOString() === expiresAt &&
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
  const extras = scanExtrasFromHost(reply.attachment);
  return {
    id: reply.attachment.id,
    mimeType: reply.attachment.mimeType,
    sizeBytes: reply.attachment.sizeBytes,
    expiresAt: reply.attachment.expiresAt,
    state: "staged",
    ...extras,
  };
}

const HOST_SCAN_STATES = new Set([
  "staged",
  "scanning",
  "clean",
  "rejected",
  "timed_out",
  "error",
  "bound",
]);

function scanExtrasFromHost(attachment: StagedChatAttachment): {
  scanState?: string;
  scannerId?: string;
} {
  const item = attachment as StagedChatAttachment & Record<string, unknown>;
  const extras: { scanState?: string; scannerId?: string } = {};
  if ("scanState" in item) {
    if (typeof item["scanState"] !== "string" || !HOST_SCAN_STATES.has(item["scanState"])) {
      throw new Error("attachment staging host returned an unsafe descriptor");
    }
    extras.scanState = item["scanState"];
  }
  if ("scannerId" in item) {
    if (
      typeof item["scannerId"] !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9._-]{0,64}$/u.test(item["scannerId"])
    ) {
      throw new Error("attachment staging host returned an unsafe descriptor");
    }
    extras.scannerId = item["scannerId"];
  }
  return extras;
}

export function bridgeChatAttachmentStagingPort(): ChatAttachmentStagingPort {
  const transport = detectTransport();
  const registry = realmStagingRegistry();
  if (transport?.kind === "one-way") {
    installRealmStagingSink(registry);
  }
  return {
    isAvailable: () => transport !== null,
    async pickAndStage() {
      if (!transport) {
        throw new Error(`attachment staging unavailable: no "${BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL}" channel`);
      }
      registry.sequence += 1;
      const id = `a${registry.sequence}`;
      const request: BridgeChatAttachmentStagingRequest = { t: "pick-and-stage", id };
      if (transport.kind === "reply") {
        return parseReply(await transport.handler.postMessage(request), id);
      }
      const reply = await new Promise<unknown>((resolve, reject) => {
        registry.pending.set(id, { resolve, reject });
        try {
          transport.channel.postMessage(JSON.stringify(request));
        } catch (error) {
          registry.pending.delete(id);
          reject(error);
        }
      });
      return parseReply(reply, id);
    },
  };
}
