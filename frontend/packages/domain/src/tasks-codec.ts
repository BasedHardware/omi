/**
 * Tasks: op builders + the projection codec. This is the exemplar for how a
 * domain package expresses "what the user did" as contract ops and "what the
 * screen shows" as optimistic overlays.
 */

import type { RecordId, Task, TaskOp, TaskPatch } from "@omi-core/contracts";
import { generateSlug, type Env } from "@omi-core/kernel";
import type { PendingOp } from "@omi-core/sync";
import type { ProjectionCodec } from "@omi-core/sync";

export function buildCreateTask(env: Env, description: string, dueAt?: number): TaskOp {
  const id = generateSlug(() => env.random());
  const base = { op: "create" as const, opId: generateSlug(() => env.random()), id, at: env.now(), description, source: "user" };
  return dueAt === undefined ? base : { ...base, dueAt };
}

export function buildPatchTask(env: Env, id: RecordId, patch: TaskPatch): TaskOp {
  return { op: "patch", opId: generateSlug(() => env.random()), id, at: env.now(), patch };
}

export function buildDeleteTask(env: Env, id: RecordId): TaskOp {
  return { op: "delete", opId: generateSlug(() => env.random()), id, at: env.now() };
}

/** Contract op → outbox record, with the human summary the dead-letter
 * surface renders (a retained op nobody can read is still lost content). */
export function taskToPendingOp(op: TaskOp): PendingOp {
  const summary =
    op.op === "create"
      ? `Add task: ${op.description}`
      : op.op === "delete"
        ? `Delete task ${op.id}`
        : `Edit task ${op.id}: ${Object.keys(op.patch).join(", ")}`;
  return { opId: op.opId, domain: "tasks", recordId: op.id, payload: JSON.stringify(op), summary, attempts: 0 };
}

/** Optimistic overlay: how a pending op changes what the screen shows. */
export const tasksCodec: ProjectionCodec<Task> = {
  id: (t) => t.id,
  applyOp: (payload, current) => {
    const op = JSON.parse(payload) as TaskOp;
    switch (op.op) {
      case "create":
        return {
          id: op.id,
          description: op.description,
          completed: false,
          completedAt: null,
          dueAt: op.dueAt ?? null,
          owner: null,
          source: op.source,
          provenance: [],
          sortOrder: 0,
          indentLevel: 0,
          createdAt: op.at,
          updatedAt: op.at,
          revision: null,
        };
      case "delete":
        return null;
      case "patch": {
        if (!current) return current;
        const next: Task = { ...current, updatedAt: op.at };
        const p = op.patch;
        if (p.description !== undefined) next.description = p.description;
        if (p.completed !== undefined) {
          next.completed = p.completed;
          next.completedAt = p.completed ? op.at : null;
        }
        if (p.completedAt !== undefined) next.completedAt = p.completedAt;
        if (p.dueAt !== undefined) next.dueAt = p.dueAt;
        if (p.owner !== undefined) next.owner = p.owner;
        if (p.sortOrder !== undefined) next.sortOrder = p.sortOrder;
        if (p.indentLevel !== undefined) next.indentLevel = p.indentLevel;
        return next;
      }
    }
  },
};
