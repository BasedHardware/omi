/**
 * Memories adapter: old backend (`backend/routers/memories.py` +
 * `backend/models/memories.py` @ e0893286) impersonating the memories
 * contract. Every impedance mismatch is named here and NOWHERE else — when
 * the canonical memory service is the only path, this file is deleted and
 * the mismatches die with it.
 *
 * Known gaps it papers over (tracker: backend-handoff sync-layer section):
 * - `POST /v3/memories` never accepts a client-supplied id — `Memory` (the
 *   request model) has no `id` field at all. The server always assigns one
 *   deterministically as a hash of `content` (`document_id_from_seed`), so
 *   two creates with identical content collapse onto the SAME server row
 *   (content-idempotent), not opId-idempotent like the sync layer assumes.
 *   We report the server id back as `serverAssignedId` on every create (it
 *   always differs from the local slug) and the caller maintains the alias
 *   until a rewrite honors ADR-004 D2.
 * - There is no ids-only endpoint (tasks' `/v1/action-items/ids` has no
 *   memories analog; `database.memories.get_memory_ids` exists server-side
 *   but no router exposes it), so the closest source is one bounded page of
 *   the full list endpoint. That list is SERVER-SIDE FILTERED, in two ways
 *   that both defeat a completeness claim:
 *     - `database.memories.get_memories` drops user-rejected memories
 *       (`user_review is not False`) and superseded/retracted ones
 *       (`invalid_at is None`, since `include_invalidated` defaults false).
 *     - Those drops happen in Python AFTER Firestore's `.limit()/.offset()`,
 *       so a SHORT page does not even prove the set was exhausted: a full
 *       page of 5000 with 4000 filtered out returns 1000 rows with more
 *       still unread. The "short page = complete" heuristic is unsound here
 *       on its own terms, independent of the filter rule.
 *   Per hard rule 12 (and the conversations precedent, which hit the same
 *   shape), `fetchMemoryIdSnapshot` therefore NEVER claims completeness: the
 *   snapshot only ever ADDS knowledge and can never drive a reconcile delete.
 *   An unfiltered ids endpoint is a backend-rewrite requirement.
 * - Patch is NOT one wire request. The exemplar (tasks) has a single PATCH
 *   endpoint that takes any subset of fields; memories fragments the same
 *   operation across three legacy endpoints with three different shapes:
 *     - content:    `PATCH /v3/memories/{id}`            body `{ value }`
 *     - visibility: `PATCH /v3/memories/{id}/visibility` body `{ value }`
 *     - userReview: `POST  /v3/memories/{id}/review`     query `?value=`
 *   A patch touching more than one key therefore issues sequential HTTP
 *   requests and is NOT atomic: a crash between them can leave some fields
 *   applied and others not. We stop at the first failure and report it —
 *   there is no server-side transaction to fall back on — so a partially
 *   applied multi-field patch is a real possibility the sync layer's retry
 *   (same opId, same patch) will converge on, but is not hidden here.
 * - `category` has no update endpoint at all in the legacy router; the
 *   contract's `MemoryPatch` omits it for exactly that reason (see
 *   `contracts/src/domain/memories.ts`).
 * - Locked memories are serialized with a TRUNCATED body: the list handler
 *   rewrites `content` to `content[:70] + '...'` behind a paid-plan gate
 *   (`backend/routers/memories.py`, the `is_locked` branch of the legacy list
 *   path). The truncation is indistinguishable from real content at the type
 *   level, so `wireToMemory` carries the `is_locked` signal through to
 *   `Memory.locked` and the store refuses a `content` patch on such a row —
 *   otherwise an editable surface writes the truncation back and destroys the
 *   record. `is_locked` survives the API exposure contract
 *   (`memory_api_contract.memory_api_payload` strips neither internal- nor
 *   canonical-lifecycle-listed fields that would cover it), so this is a
 *   signal we may rely on rather than infer.
 */

import type { Memory, MemoryIdSnapshot, MemoryOp, MemoryPatch } from "@omi-core/contracts";
import { parseRecordId } from "@omi-core/contracts";
import type { PendingOp } from "@omi-core/sync";
import { classifyStatus, type HttpClient } from "./http.js";

export type MemorySendResult =
  | { ok: true; serverRevision?: string; serverAssignedId?: string }
  | { ok: false; failure: import("@omi-core/contracts").WriteFailure };

export async function sendMemoryOp(http: HttpClient, op: MemoryOp): Promise<MemorySendResult> {
  switch (op.op) {
    case "create": {
      const res = await http.request("POST", "/v3/memories", {
        content: op.content,
        ...(op.category !== undefined ? { category: op.category } : {}),
        ...(op.visibility !== undefined ? { visibility: op.visibility } : {}),
      });
      if (res.status === 200 || res.status === 201) {
        const body = res.json as { id?: string };
        // The server never honors a client id here (Memory has no `id` field
        // on create) — report the alias unconditionally, not only on mismatch.
        return body.id !== undefined ? { ok: true, serverAssignedId: body.id } : { ok: true };
      }
      return { ok: false, failure: classifyStatus(res, `create memory ${op.id}`) };
    }
    case "patch": {
      for (const step of wirePatchSteps(op.id, op.patch)) {
        const res = await http.request(step.method, step.path, step.body);
        if (res.status !== 200) return { ok: false, failure: classifyStatus(res, `patch memory ${op.id} (${step.field})`) };
      }
      return { ok: true };
    }
    case "delete": {
      const res = await http.request("DELETE", `/v3/memories/${encodeURIComponent(op.id)}`);
      if (res.status === 200 || res.status === 204) return { ok: true };
      // Deleting something already gone is success, not failure.
      if (res.status === 404) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `delete memory ${op.id}`) };
    }
  }
}

/**
 * Keyed patch → an ordered list of wire requests. Absent key = no request
 * for that field at all — never a default, and never a field smuggled onto
 * another field's request. Order (content, visibility, userReview) is
 * arbitrary but fixed, so retries of the same patch hit the same sequence.
 */
function wirePatchSteps(
  id: string,
  p: MemoryPatch,
): Array<{ field: string; method: "PATCH" | "POST"; path: string; body?: unknown }> {
  const steps: Array<{ field: string; method: "PATCH" | "POST"; path: string; body?: unknown }> = [];
  const encoded = encodeURIComponent(id);
  if (p.content !== undefined) {
    steps.push({ field: "content", method: "PATCH", path: `/v3/memories/${encoded}`, body: { value: p.content } });
  }
  if (p.visibility !== undefined) {
    steps.push({
      field: "visibility",
      method: "PATCH",
      path: `/v3/memories/${encoded}/visibility`,
      body: { value: p.visibility },
    });
  }
  if (p.userReview !== undefined && p.userReview !== null) {
    steps.push({
      field: "userReview",
      method: "POST",
      path: `/v3/memories/${encoded}/review?value=${p.userReview ? "true" : "false"}`,
    });
  }
  return steps;
}

/**
 * Honest ids snapshot: no legacy endpoint returns ids alone, so we page the
 * list endpoint once — but that list is server-side filtered and the filter
 * runs after the page limit (see the file header), so completeness is not
 * observable from here at all.
 */
export async function fetchMemoryIdSnapshot(http: HttpClient, limit = 5000): Promise<MemoryIdSnapshot | null> {
  const res = await http.request("GET", `/v3/memories?limit=${limit}&offset=0`);
  if (res.status !== 200) return null;
  if (!Array.isArray(res.json)) return null; // rule 12: junk body never becomes a snapshot
  const rows = res.json as unknown[];
  const ids: string[] = [];
  for (const raw of rows) {
    const r = raw as Record<string, unknown>;
    if (typeof r["id"] === "string") ids.push(r["id"]);
  }
  // Rule 12: the list endpoint hides user-rejected and invalidated memories,
  // and filters after the limit, so neither a short page nor a full one
  // proves we saw the whole set. A filtered source may NEVER back a complete
  // snapshot — reconcile would delete the filtered-out rows locally.
  return { setVersion: contentHash(ids), complete: false, ids };
}

export async function fetchMemories(http: HttpClient, limit = 500, offset = 0): Promise<Memory[] | null> {
  const res = await http.request("GET", `/v3/memories?limit=${limit}&offset=${offset}`);
  if (res.status !== 200) return null;
  const rows = Array.isArray(res.json) ? (res.json as unknown[]) : [];
  const memories: Memory[] = [];
  for (const raw of rows) {
    const m = wireToMemory(raw);
    if (m) memories.push(m);
  }
  return memories;
}

/** Wire row → contract Memory. Unparseable rows are dropped by the caller's
 * Degraded path — this function only says yes or no. */
export function wireToMemory(raw: unknown): Memory | null {
  const r = raw as Record<string, unknown>;
  const parsed = typeof r["id"] === "string" ? parseRecordId(r["id"]) : null;
  if (!parsed) return null;
  const visibility = r["visibility"] === "public" ? "public" : "private";
  return {
    id: parsed.id,
    content: typeof r["content"] === "string" ? r["content"] : "",
    category: typeof r["category"] === "string" ? r["category"] : "interesting",
    visibility,
    reviewed: r["reviewed"] === true,
    userReview: typeof r["user_review"] === "boolean" ? r["user_review"] : null,
    createdAt: isoToMs(r["created_at"]) ?? 0,
    updatedAt: isoToMs(r["updated_at"]) ?? 0,
    revision: null,
    // Absent/non-boolean `is_locked` means NOT locked: the field defaults to
    // False server-side (`MemoryDB.is_locked`) and is not stripped by the API
    // exposure contract, so its absence is a real "unlocked", not a gap.
    locked: r["is_locked"] === true,
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
export function memoriesTransport(
  http: HttpClient,
  onServerAssignedId: (localId: string, serverId: string) => void,
  /** Maps a local slug to the wire id the legacy server knows it by (the
   * alias created when create returned serverAssignedId). Identity default. */
  resolveWireId: (localId: string) => string = (id) => id,
): { send(op: PendingOp): Promise<MemorySendResult> } {
  return {
    async send(op: PendingOp): Promise<MemorySendResult> {
      const domainOp = JSON.parse(op.payload) as MemoryOp;
      if (domainOp.op !== "create") {
        (domainOp as { id: string }).id = resolveWireId(domainOp.id);
      }
      const result = await sendMemoryOp(http, domainOp);
      if (result.ok && result.serverAssignedId !== undefined) {
        onServerAssignedId(domainOp.id, result.serverAssignedId);
      }
      return result;
    },
  };
}
