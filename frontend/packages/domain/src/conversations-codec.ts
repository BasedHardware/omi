/**
 * Conversations: op builders + the projection codec. Mirrors tasks-codec.ts
 * over the conversations contract — optimistic overlays for keyed patch and
 * delete. No create: conversations are server-originated (contract header /
 * ADR-004 amendment 2026-08-07).
 */

import type { Conversation, ConversationOp, ConversationPatch, RecordId } from "@omi-core/contracts";
import { generateSlug, type Env } from "@omi-core/kernel";
import type { PendingOp, ProjectionCodec } from "@omi-core/sync";

export function buildPatchConversation(env: Env, id: RecordId, patch: ConversationPatch): ConversationOp {
  return { op: "patch", opId: generateSlug(() => env.random()), id, at: env.now(), patch };
}

export function buildDeleteConversation(env: Env, id: RecordId): ConversationOp {
  return { op: "delete", opId: generateSlug(() => env.random()), id, at: env.now() };
}

/** Contract op → outbox record, with the human summary the dead-letter
 * surface renders (a retained op nobody can read is still lost content). */
export function conversationToPendingOp(op: ConversationOp): PendingOp {
  const summary =
    op.op === "delete"
      ? `Delete conversation ${op.id}`
      : `Edit conversation ${op.id}: ${Object.keys(op.patch).join(", ")}`;
  return {
    opId: op.opId,
    domain: "conversations",
    recordId: op.id,
    payload: JSON.stringify(op),
    summary,
    attempts: 0,
  };
}

/** Optimistic overlay: how a pending op changes what the screen shows. */
export const conversationsCodec: ProjectionCodec<Conversation> = {
  id: (c) => c.id,
  applyOp: (payload, current) => {
    const op = JSON.parse(payload) as ConversationOp;
    switch (op.op) {
      case "delete":
        return null;
      case "patch": {
        if (!current) return current;
        const next: Conversation = { ...current, updatedAt: op.at };
        const p = op.patch;
        if (p.title !== undefined) next.title = p.title;
        if (p.starred !== undefined) next.starred = p.starred;
        if (p.visibility !== undefined) next.visibility = p.visibility;
        if (p.folderId !== undefined) next.folderId = p.folderId;
        return next;
      }
    }
  },
};
