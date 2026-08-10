/**
 * Chat messages: op builders + the projection codec.
 *
 * The payload hash moved to `@omi-core/kernel` — one definition, shared by the
 * codec and by every transport binding, and re-exported here so existing
 * callers keep their import path.
 * Mirrors tasks-codec.ts / memories-codec.ts over the chat contract (ADR-005).
 *
 * Payload hash is a PURE function of the caller-controlled immutable fields —
 * no Env clock, no Math.random — including the ratified ordered attachment id
 * list so client and server agree on identity-conflict detection.
 */

export { chatMessagePayloadHash, type ChatMessageHashPayload } from "@omi-core/kernel";

import type {
  ChatIdentityConflictFailure,
  ChatMessage,
  ChatMessageOp,
  ChatMessagePatch,
  ChatMessageType,
  RecordId,
  WriteFailure,
} from "@omi-core/contracts";
import { chatMessagePayloadHash, generateSlug, type Env } from "@omi-core/kernel";
import type { PendingOp, ProjectionCodec } from "@omi-core/sync";

const DEFAULT_MESSAGE_SOURCE = "desktop_chat";

export function buildCreateChatMessage(
  env: Env,
  text: string,
  opts?: {
    type?: ChatMessageType;
    journalRevision?: number;
    appId?: string | null;
    chatSessionId?: string | null;
    messageSource?: string;
    metadata?: string | null;
    attachmentIds?: readonly string[];
  },
): ChatMessageOp {
  const id = generateSlug(() => env.random());
  const base = {
    op: "create" as const,
    opId: generateSlug(() => env.random()),
    id,
    at: env.now(),
    text,
    sender: "human" as const,
    journalRevision: opts?.journalRevision ?? 1,
    attachmentIds: opts?.attachmentIds ?? [],
  };
  return {
    ...base,
    ...(opts?.type !== undefined ? { type: opts.type } : {}),
    ...(opts?.appId !== undefined ? { appId: opts.appId } : {}),
    ...(opts?.chatSessionId !== undefined ? { chatSessionId: opts.chatSessionId } : {}),
    ...(opts?.messageSource !== undefined ? { messageSource: opts.messageSource } : {}),
    ...(opts?.metadata !== undefined ? { metadata: opts.metadata } : {}),
  };
}

export function buildPatchChatMessage(env: Env, id: RecordId, patch: ChatMessagePatch): ChatMessageOp {
  return { op: "patch", opId: generateSlug(() => env.random()), id, at: env.now(), patch };
}

export function buildDeleteChatMessage(env: Env, id: RecordId): ChatMessageOp {
  return { op: "delete", opId: generateSlug(() => env.random()), id, at: env.now() };
}

/** Contract op → outbox record, with the human summary the dead-letter
 * surface renders (a retained op nobody can read is still lost content). */
export function chatMessageToPendingOp(op: ChatMessageOp): PendingOp {
  const summary =
    op.op === "create"
      ? `Send chat: ${op.text.slice(0, 80)}${op.text.length > 80 ? "…" : ""}`
      : op.op === "delete"
        ? `Delete chat message ${op.id}`
        : `Edit chat message ${op.id}: ${Object.keys(op.patch).join(", ")}`;
  return {
    opId: op.opId,
    domain: "chat",
    recordId: op.id,
    payload: JSON.stringify(op),
    summary,
    attempts: 0,
  };
}

/**
 * Fold an HTTP 409 identity conflict onto the WriteFailure taxonomy.
 *
 * Kind is `permanent` / `reason: "conflict"` — NOT retryable. Same
 * client_message_id with a different payload hash will 409 forever if
 * retried; the outbox must dead-letter (user-visible) instead of spinning.
 * See `ChatIdentityConflictFailure` on the contract.
 */
export function foldChatIdentityConflict(detail: string): ChatIdentityConflictFailure {
  return { kind: "permanent", reason: "conflict", detail };
}

/** Narrow helper so adapters can assert the folded shape without casting. */
export function isChatIdentityConflictFailure(
  failure: WriteFailure,
): failure is ChatIdentityConflictFailure {
  return failure.kind === "permanent" && failure.reason === "conflict";
}

/** Optimistic overlay: how a pending op changes what the screen shows. */
export const chatMessagesCodec: ProjectionCodec<ChatMessage> = {
  id: (m) => m.id,
  applyOp: (payload, current) => {
    const op = JSON.parse(payload) as ChatMessageOp;
    switch (op.op) {
      case "create": {
        const appId = op.appId ?? null;
        const chatSessionId = op.chatSessionId ?? null;
        const messageSource = op.messageSource ?? DEFAULT_MESSAGE_SOURCE;
        const metadata = op.metadata ?? null;
        return {
          id: op.id,
          text: op.text,
          sender: op.sender,
          type: op.type ?? "text",
          createdAt: op.at,
          updatedAt: op.at,
          chatSessionId,
          appId,
          journalRevision: op.journalRevision,
          payloadHash: chatMessagePayloadHash({
            text: op.text,
            sender: op.sender,
            appId,
            sessionId: chatSessionId,
            metadata,
            messageSource,
            attachmentIds: op.attachmentIds,
          }),
          messageSource,
          rating: null,
          reported: false,
          generationOutcome: null,
          // Optimistic rows know staged ids but not canonical durable metadata.
          // The next server reconcile replaces this with the authoritative list.
          attachments: [],
          revision: null,
        };
      }
      case "delete":
        return null;
      case "patch": {
        if (!current) return current;
        // Keyed patch: absent key = unchanged. Never setdefault.
        const next: ChatMessage = { ...current, updatedAt: op.at };
        const p = op.patch;
        if (p.rating !== undefined) next.rating = p.rating;
        return next;
      }
    }
  },
};
