/**
 * Memories: op builders + the projection codec. Mirrors tasks-codec.ts over
 * the memories contract — optimistic overlays for create, keyed patch, delete.
 */

import type { Memory, MemoryOp, MemoryPatch, RecordId } from "@omi-core/contracts";
import { generateSlug, type Env } from "@omi-core/kernel";
import type { PendingOp, ProjectionCodec } from "@omi-core/sync";

export function buildCreateMemory(
  env: Env,
  content: string,
  opts?: { category?: string; visibility?: "public" | "private" },
): MemoryOp {
  const id = generateSlug(() => env.random());
  return {
    op: "create",
    opId: generateSlug(() => env.random()),
    id,
    at: env.now(),
    content,
    ...(opts?.category !== undefined ? { category: opts.category } : {}),
    ...(opts?.visibility !== undefined ? { visibility: opts.visibility } : {}),
  };
}

export function buildPatchMemory(env: Env, id: RecordId, patch: MemoryPatch): MemoryOp {
  return { op: "patch", opId: generateSlug(() => env.random()), id, at: env.now(), patch };
}

export function buildDeleteMemory(env: Env, id: RecordId): MemoryOp {
  return { op: "delete", opId: generateSlug(() => env.random()), id, at: env.now() };
}

/** Contract op → outbox record, with the human summary the dead-letter
 * surface renders (a retained op nobody can read is still lost content). */
export function memoryToPendingOp(op: MemoryOp): PendingOp {
  const summary =
    op.op === "create"
      ? `Add memory: ${op.content.slice(0, 80)}${op.content.length > 80 ? "…" : ""}`
      : op.op === "delete"
        ? `Delete memory ${op.id}`
        : `Edit memory ${op.id}: ${Object.keys(op.patch).join(", ")}`;
  return { opId: op.opId, domain: "memories", recordId: op.id, payload: JSON.stringify(op), summary, attempts: 0 };
}

/** Optimistic overlay: how a pending op changes what the screen shows. */
export const memoriesCodec: ProjectionCodec<Memory> = {
  id: (m) => m.id,
  applyOp: (payload, current) => {
    const op = JSON.parse(payload) as MemoryOp;
    switch (op.op) {
      case "create":
        return {
          id: op.id,
          content: op.content,
          category: op.category ?? "interesting",
          visibility: op.visibility ?? "private",
          reviewed: false,
          userReview: null,
          createdAt: op.at,
          updatedAt: op.at,
          revision: null,
          // A memory we just wrote locally is never a server truncation.
          locked: false,
        };
      case "delete":
        return null;
      case "patch": {
        if (!current) return current;
        const next: Memory = { ...current, updatedAt: op.at };
        const p = op.patch;
        if (p.content !== undefined) next.content = p.content;
        if (p.visibility !== undefined) next.visibility = p.visibility;
        if (p.userReview !== undefined) next.userReview = p.userReview;
        return next;
      }
    }
  },
};
