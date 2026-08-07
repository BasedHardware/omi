/**
 * Tasks adapter: old backend (`backend/routers/action_items.py` @ e0893286)
 * impersonating the tasks contract. Every impedance mismatch is named here
 * and NOWHERE else — when David's rewritten service lands, this file is
 * deleted and the mismatches die with it.
 *
 * Known gaps it papers over (tracker: backend-handoff sync-layer section):
 * - Create is content-idempotent on (uid, normalized description), NOT
 *   opId-idempotent, and ignores client-supplied ids over HTTP → the server
 *   assigns its own id; we report it back as `serverAssignedId` and the
 *   caller maintains the alias (local slug ↔ server id) until the rewrite
 *   honors ADR-004 D2.
 * - `GET /v1/action-items/ids` has no set version and no pagination → the
 *   snapshot IS complete (single response), and we synthesize `setVersion`
 *   as a content hash so Projection.reconcile's idempotence rule works.
 * - List pagination is offset-based (finding 6): a concurrent insert can
 *   shift pages. We mitigate by fetching ids first and diffing, never by
 *   trusting offset pages for deletion decisions.
 */

import type { Task, TaskIdSnapshot, TaskOp, TaskPatch } from "@omi-core/contracts";
import { parseRecordId } from "@omi-core/contracts";
import type { PendingOp } from "@omi-core/sync";
import { classifyStatus, type HttpClient } from "./http.js";

export type TaskSendResult =
  | { ok: true; serverRevision?: string; serverAssignedId?: string }
  | { ok: false; failure: import("@omi-core/contracts").WriteFailure };

export async function sendTaskOp(http: HttpClient, op: TaskOp): Promise<TaskSendResult> {
  switch (op.op) {
    case "create": {
      const res = await http.request("POST", "/v1/action-items", {
        description: op.description,
        ...(op.dueAt !== undefined ? { due_at: new Date(op.dueAt).toISOString() } : {}),
        source: op.source,
      });
      if (res.status === 200 || res.status === 201) {
        const body = res.json as { id?: string };
        return body.id !== undefined && body.id !== op.id
          ? { ok: true, serverAssignedId: body.id }
          : { ok: true };
      }
      return { ok: false, failure: classifyStatus(res, `create task ${op.id}`) };
    }
    case "patch": {
      const res = await http.request("PATCH", `/v1/action-items/${encodeURIComponent(op.id)}`, wirePatch(op.patch));
      if (res.status === 200) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `patch task ${op.id}`) };
    }
    case "delete": {
      const res = await http.request("DELETE", `/v1/action-items/${encodeURIComponent(op.id)}`);
      if (res.status === 200 || res.status === 204) return { ok: true };
      // Deleting something already gone is success, not failure.
      if (res.status === 404) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `delete task ${op.id}`) };
    }
  }
}

/** Keyed patch → wire body. Absent key stays absent — never a default. */
function wirePatch(p: TaskPatch): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (p.description !== undefined) body["description"] = p.description;
  if (p.completed !== undefined) body["completed"] = p.completed;
  if (p.dueAt !== undefined) body["due_at"] = p.dueAt === null ? null : new Date(p.dueAt).toISOString();
  if (p.owner !== undefined) body["owner"] = p.owner;
  if (p.sortOrder !== undefined) body["sort_order"] = p.sortOrder;
  if (p.indentLevel !== undefined) body["indent_level"] = p.indentLevel;
  return body;
}

export async function fetchIdSnapshot(http: HttpClient): Promise<TaskIdSnapshot | null> {
  const res = await http.request("GET", "/v1/action-items/ids");
  if (res.status !== 200) return null;
  const body = res.json as { ids?: unknown } | null;
  if (!body || !Array.isArray(body.ids)) return null; // rule 12: junk body never becomes a snapshot
  const ids = body.ids.filter((x): x is string => typeof x === "string");
  return { setVersion: contentHash(ids), complete: true, ids };
}

export async function fetchTasks(http: HttpClient, limit = 500, offset = 0): Promise<Task[] | null> {
  const res = await http.request("GET", `/v1/action-items?limit=${limit}&offset=${offset}`);
  if (res.status !== 200) return null;
  const items = (res.json as { action_items?: unknown[] }).action_items ?? [];
  const tasks: Task[] = [];
  for (const raw of items) {
    const t = wireToTask(raw);
    if (t) tasks.push(t);
  }
  return tasks;
}

/** Wire row → contract Task. Unparseable rows are dropped by the caller's
 * Degraded path — this function only says yes or no. */
export function wireToTask(raw: unknown): Task | null {
  const r = raw as Record<string, unknown>;
  const parsed = typeof r["id"] === "string" ? parseRecordId(r["id"]) : null;
  if (!parsed) return null;
  return {
    id: parsed.id,
    description: typeof r["description"] === "string" ? r["description"] : "",
    completed: r["completed"] === true,
    completedAt: isoToMs(r["completed_at"]),
    dueAt: isoToMs(r["due_at"]),
    owner: typeof r["owner"] === "string" ? r["owner"] : null,
    source: typeof r["source"] === "string" ? r["source"] : "legacy",
    provenance: Array.isArray(r["provenance"]) ? (r["provenance"].filter((x) => typeof x === "string") as string[]) : [],
    sortOrder: typeof r["sort_order"] === "number" ? r["sort_order"] : 0,
    indentLevel: typeof r["indent_level"] === "number" ? r["indent_level"] : 0,
    createdAt: isoToMs(r["created_at"]) ?? 0,
    updatedAt: isoToMs(r["updated_at"]) ?? 0,
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
export function tasksTransport(
  http: HttpClient,
  onServerAssignedId: (localId: string, serverId: string) => void,
): { send(op: PendingOp): Promise<TaskSendResult> } {
  return {
    async send(op: PendingOp): Promise<TaskSendResult> {
      const domainOp = JSON.parse(op.payload) as TaskOp;
      const result = await sendTaskOp(http, domainOp);
      if (result.ok && result.serverAssignedId !== undefined) {
        onServerAssignedId(domainOp.id, result.serverAssignedId);
      }
      return result;
    },
  };
}
