/**
 * Folders adapter: old backend (`backend/routers/folders.py` +
 * `backend/models/folder.py` @ e0893286) impersonating the folders contract.
 * Every impedance mismatch is named here and NOWHERE else — when the rewrite
 * lands, this file is deleted and the mismatches die with it.
 *
 * Known gaps it papers over (tracker: backend-handoff sync-layer section):
 * - `POST /v1/folders` never accepts a client-supplied id — `CreateFolderRequest`
 *   has no `id` field. The server always assigns one; we report it back as
 *   `serverAssignedId` and the caller maintains the alias (local slug ↔ server
 *   id) until a rewrite honors ADR-004 D2.
 * - `GET /v1/folders` is unpaginated and returns the entire set, so
 *   `fetchFolderIdSnapshot` reports `complete: true` honestly — the first
 *   domain where reconcile may delete local rows against a list-derived
 *   snapshot. Caveat: on an empty store the handler calls
 *   `initialize_system_folders(uid)` (a read with a write side effect), so the
 *   first snapshot fetch may materialize system folders server-side before ids
 *   are returned; reconcile must not assume a prior empty snapshot meant "no
 *   folders exist".
 * - Per-folder `order` is updated via `PATCH /v1/folders/{id}` (`order` in
 *   `UpdateFolderRequest`). Whole-list ordering also exists at
 *   `POST /v1/folders/reorder` (`{ folder_ids: [...] }`). That is split
 *   mutation authority — we implement only the keyed `order` patch (fits the
 *   ADR-004 patch contract); bulk reorder is a named gap with no `FolderOp`
 *   equivalent here.
 * - Conversation membership under folders (`GET .../conversations`,
 *   `PATCH /v1/conversations/{id}/folder`, bulk-move) is owned by the
 *   conversations domain slice, not modeled here.
 * - `DELETE /v1/folders/{id}` returns 204 with no body (not 200). Missing
 *   folder → 404 (treated as idempotent success on delete replay). System folder
 *   delete → 400 `Cannot delete system folder` → `permanent` / `validation`
 *   via the shared `classifyStatus` (correct: never retry).
 * - Folder limit on create: 400 `Maximum folder limit reached` → same
 *   `permanent` / `validation` mapping — also correct.
 */

import type { Folder, FolderIdSnapshot, FolderOp, FolderPatch } from "@omi-core/contracts";
import { parseRecordId } from "@omi-core/contracts";
import type { PendingOp } from "@omi-core/sync";
import { classifyStatus, type HttpClient } from "./http.js";

export type FolderSendResult =
  | { ok: true; serverRevision?: string; serverAssignedId?: string }
  | { ok: false; failure: import("@omi-core/contracts").WriteFailure };

export async function sendFolderOp(http: HttpClient, op: FolderOp): Promise<FolderSendResult> {
  switch (op.op) {
    case "create": {
      const res = await http.request("POST", "/v1/folders", {
        name: op.name,
        ...(op.description !== undefined ? { description: op.description } : {}),
        ...(op.color !== undefined ? { color: op.color } : {}),
        ...(op.icon !== undefined ? { icon: op.icon } : {}),
      });
      if (res.status === 200 || res.status === 201) {
        const body = res.json as { id?: string };
        return body.id !== undefined ? { ok: true, serverAssignedId: body.id } : { ok: true };
      }
      return { ok: false, failure: classifyStatus(res, `create folder ${op.id}`) };
    }
    case "patch": {
      const res = await http.request("PATCH", `/v1/folders/${encodeURIComponent(op.id)}`, wirePatch(op.patch));
      if (res.status === 200) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `patch folder ${op.id}`) };
    }
    case "delete": {
      const path =
        op.moveToFolderId !== undefined
          ? `/v1/folders/${encodeURIComponent(op.id)}?move_to_folder_id=${encodeURIComponent(op.moveToFolderId)}`
          : `/v1/folders/${encodeURIComponent(op.id)}`;
      const res = await http.request("DELETE", path);
      if (res.status === 200 || res.status === 204) return { ok: true };
      // Deleting something already gone is success, not failure.
      if (res.status === 404) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `delete folder ${op.id}`) };
    }
  }
}

/** Keyed patch → wire body. Absent key stays absent — never a default. */
function wirePatch(p: FolderPatch): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (p.name !== undefined) body["name"] = p.name;
  if (p.description !== undefined) body["description"] = p.description;
  if (p.color !== undefined) body["color"] = p.color;
  if (p.icon !== undefined) body["icon"] = p.icon;
  if (p.order !== undefined) body["order"] = p.order;
  return body;
}

/**
 * Honest ids snapshot: `GET /v1/folders` is unpaginated — the response is the
 * whole set, so `complete: true` is defensible (unlike memories' bounded page).
 */
export async function fetchFolderIdSnapshot(http: HttpClient): Promise<FolderIdSnapshot | null> {
  const res = await http.request("GET", "/v1/folders");
  if (res.status !== 200) return null;
  if (!Array.isArray(res.json)) return null; // a 200 with an unexpected body must never become a complete empty snapshot
  const rows = res.json as unknown[];
  const ids: string[] = [];
  for (const raw of rows) {
    const r = raw as Record<string, unknown>;
    if (typeof r["id"] === "string") ids.push(r["id"]);
  }
  return { setVersion: contentHash(ids), complete: true, ids };
}

export async function fetchFolders(http: HttpClient): Promise<Folder[] | null> {
  const res = await http.request("GET", "/v1/folders");
  if (res.status !== 200) return null;
  if (!Array.isArray(res.json)) return null; // a 200 with an unexpected body must never become a complete empty snapshot
  const rows = res.json as unknown[];
  const folders: Folder[] = [];
  for (const raw of rows) {
    const f = wireToFolder(raw);
    if (f) folders.push(f);
  }
  return folders;
}

/** Wire row → contract Folder. Unparseable rows are dropped by the caller's
 * Degraded path — this function only says yes or no. */
export function wireToFolder(raw: unknown): Folder | null {
  const r = raw as Record<string, unknown>;
  const parsed = typeof r["id"] === "string" ? parseRecordId(r["id"]) : null;
  if (!parsed) return null;
  return {
    id: parsed.id,
    name: typeof r["name"] === "string" ? r["name"] : "",
    description: typeof r["description"] === "string" ? r["description"] : null,
    color: typeof r["color"] === "string" ? r["color"] : "#6B7280",
    icon: typeof r["icon"] === "string" ? r["icon"] : "folder",
    createdAt: isoToMs(r["created_at"]) ?? 0,
    updatedAt: isoToMs(r["updated_at"]) ?? 0,
    order: typeof r["order"] === "number" ? r["order"] : 0,
    isDefault: r["is_default"] === true,
    isSystem: r["is_system"] === true,
    revision: null,
  };
}

function isoToMs(v: unknown): number | null {
  if (typeof v !== "string") return null;
  const ms = Date.parse(v);
  return Number.isNaN(ms) ? null : ms;
}

/** FNV-1a over the sorted id list — a stable synthetic set version. */
function contentHash(ids: readonly string[]): string {
  let h = 0x811c9dc5;
  for (const id of [...ids].sort()) {
    for (let i = 0; i < id.length; i++) {
      h ^= id.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    h ^= 0x2c; // separator
    h = Math.imul(h, 0x01000193);
  }
  return `fnv-${(h >>> 0).toString(16)}`;
}

/** Bind the adapter to the sync Transport interface. The caller supplies the
 * alias hook for server-assigned create ids (ADR-004 D2 gap). */
export function foldersTransport(
  http: HttpClient,
  onServerAssignedId: (localId: string, serverId: string) => void,
): { send(op: PendingOp): Promise<FolderSendResult> } {
  return {
    async send(op: PendingOp): Promise<FolderSendResult> {
      const domainOp = JSON.parse(op.payload) as FolderOp;
      const result = await sendFolderOp(http, domainOp);
      if (result.ok && result.serverAssignedId !== undefined) {
        onServerAssignedId(domainOp.id, result.serverAssignedId);
      }
      return result;
    },
  };
}
