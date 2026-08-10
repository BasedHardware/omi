import type { ChatAttachment as DomainChatAttachment } from "@omi-core/contracts";

/**
 * Pure chat mirror logic (ADR-005). Self-contained: no relative imports so
 * Node can execute this module directly from hermetic tests.
 */

export type ChatRole = "user" | "assistant";

export type ChatAttachment = DomainChatAttachment;

/** Delivery is a closed union. Every message reaches a terminal outcome. */
export type ChatDelivery =
  | {
      readonly kind: "canonical";
      readonly serverId: string;
      readonly clientMessageId: string | null;
      /** null for human rows; assistant terminals state how generation ended. */
      readonly generationOutcome: "completed" | "cancelled" | null;
    }
  | { readonly kind: "streaming"; readonly generationId: string }
  | { readonly kind: "echo"; readonly clientMessageId: string }
  | { readonly kind: "failed"; readonly clientMessageId: string; readonly retryable: boolean };

export type ChatMessage = {
  readonly role: ChatRole;
  readonly text: string;
  readonly delivery: ChatDelivery;
  readonly attachments: readonly ChatAttachment[];
};

export type ChatHistoryPage = {
  readonly messages: readonly ChatMessage[];
  readonly hasOlder: boolean;
  /** Opaque server cursor. Never parsed, never constructed client-side. */
  readonly olderCursor: string | null;
};

export type ChatCapabilities = {
  /** null = the server has not reported a cap; attachments stay unavailable. */
  readonly maxAttachmentsPerMessage: number | null;
};

function clientMessageIdOf(message: ChatMessage): string | null {
  if (message.delivery.kind === "canonical") return message.delivery.clientMessageId;
  if (message.delivery.kind === "streaming") return null;
  return message.delivery.clientMessageId;
}

/**
 * Stable React key derived from the delivery union so an echo and its
 * canonical replacement share a DOM identity and do not remount.
 */
export function messageKey(message: ChatMessage): string {
  const clientMessageId = clientMessageIdOf(message);
  if (clientMessageId !== null) return `cid:${clientMessageId}`;
  if (message.delivery.kind === "canonical") return `server:${message.delivery.serverId}`;
  if (message.delivery.kind === "streaming") return `generation:${message.delivery.generationId}`;
  return `cid:${message.delivery.clientMessageId}`;
}

/**
 * Server order wins. A canonical incoming message replaces any local echo or
 * failed entry with the same clientMessageId, in the incoming position. Local
 * echoes/failed entries the server has not acknowledged are appended after the
 * canonical tail, in their original relative order. The client never sorts.
 */
export function reconcileMessages(
  local: readonly ChatMessage[],
  incoming: readonly ChatMessage[],
): readonly ChatMessage[] {
  const acknowledged = new Set<string>();
  for (const message of incoming) {
    if (message.delivery.kind === "canonical" && message.delivery.clientMessageId !== null) {
      acknowledged.add(message.delivery.clientMessageId);
    }
  }

  const merged: ChatMessage[] = [...incoming];
  for (const message of local) {
    if (message.delivery.kind !== "echo" && message.delivery.kind !== "failed") continue;
    if (acknowledged.has(message.delivery.clientMessageId)) continue;
    merged.push(message);
  }
  return merged;
}

/**
 * Prepends an older keyset page without duplicating messages already present
 * and without reordering either side. Idempotent when the same page is merged twice.
 */
export function mergeOlderPage(
  current: readonly ChatMessage[],
  older: ChatHistoryPage,
): readonly ChatMessage[] {
  const seen = new Set(current.map(messageKey));
  const prepended: ChatMessage[] = [];
  for (const message of older.messages) {
    const key = messageKey(message);
    if (seen.has(key)) continue;
    seen.add(key);
    prepended.push(message);
  }
  return [...prepended, ...current];
}

export function attachmentCapState(
  capabilities: ChatCapabilities,
  selectedCount: number,
): { enabled: boolean; atLimit: boolean; reason: "unknown-cap" | "at-limit" | null } {
  const cap = capabilities.maxAttachmentsPerMessage;
  if (cap === null) {
    return { enabled: false, atLimit: false, reason: "unknown-cap" };
  }
  if (selectedCount >= cap) {
    return { enabled: false, atLimit: true, reason: "at-limit" };
  }
  return { enabled: true, atLimit: false, reason: null };
}
