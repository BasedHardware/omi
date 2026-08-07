/**
 * Folders: op builders + the projection codec. Mirrors tasks-codec.ts over
 * the folders contract — optimistic overlays for create, keyed patch, delete.
 */

import type { Folder, FolderOp, FolderPatch, RecordId } from "@omi-core/contracts";
import { generateSlug, type Env } from "@omi-core/kernel";
import type { PendingOp, ProjectionCodec } from "@omi-core/sync";

export function buildCreateFolder(
  env: Env,
  name: string,
  opts?: { description?: string; color?: string; icon?: string },
): FolderOp {
  const id = generateSlug(() => env.random());
  return {
    op: "create",
    opId: generateSlug(() => env.random()),
    id,
    at: env.now(),
    name,
    ...(opts?.description !== undefined ? { description: opts.description } : {}),
    ...(opts?.color !== undefined ? { color: opts.color } : {}),
    ...(opts?.icon !== undefined ? { icon: opts.icon } : {}),
  };
}

export function buildPatchFolder(env: Env, id: RecordId, patch: FolderPatch): FolderOp {
  return { op: "patch", opId: generateSlug(() => env.random()), id, at: env.now(), patch };
}

export function buildDeleteFolder(env: Env, id: RecordId, moveToFolderId?: RecordId): FolderOp {
  const base = { op: "delete" as const, opId: generateSlug(() => env.random()), id, at: env.now() };
  return moveToFolderId === undefined ? base : { ...base, moveToFolderId };
}

/** Contract op → outbox record, with the human summary the dead-letter
 * surface renders (a retained op nobody can read is still lost content). */
export function folderToPendingOp(op: FolderOp): PendingOp {
  const summary =
    op.op === "create"
      ? `Add folder: ${op.name}`
      : op.op === "delete"
        ? `Delete folder ${op.id}`
        : `Edit folder ${op.id}: ${Object.keys(op.patch).join(", ")}`;
  return { opId: op.opId, domain: "folders", recordId: op.id, payload: JSON.stringify(op), summary, attempts: 0 };
}

/** Optimistic overlay: how a pending op changes what the screen shows. */
export const foldersCodec: ProjectionCodec<Folder> = {
  id: (f) => f.id,
  applyOp: (payload, current) => {
    const op = JSON.parse(payload) as FolderOp;
    switch (op.op) {
      case "create":
        return {
          id: op.id,
          name: op.name,
          description: op.description ?? null,
          color: op.color ?? "#6B7280",
          icon: op.icon ?? "folder",
          createdAt: op.at,
          updatedAt: op.at,
          order: 0,
          isDefault: false,
          isSystem: false,
          revision: null,
        };
      case "delete":
        return null;
      case "patch": {
        if (!current) return current;
        const next: Folder = { ...current, updatedAt: op.at };
        const p = op.patch;
        if (p.name !== undefined) next.name = p.name;
        if (p.description !== undefined) next.description = p.description;
        if (p.color !== undefined) next.color = p.color;
        if (p.icon !== undefined) next.icon = p.icon;
        if (p.order !== undefined) next.order = p.order;
        return next;
      }
    }
  },
};
