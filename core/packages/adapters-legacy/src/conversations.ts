/**
 * Conversations adapter: old backend (`backend/routers/conversations.py` +
 * `backend/models/conversation.py` + `backend/routers/folders.py` folder-move
 * @ e0893286) impersonating the conversations contract. Every impedance
 * mismatch is named here and NOWHERE else — when the rewritten conversations
 * service is the only path, this file is deleted and the mismatches die with it.
 *
 * Known gaps it papers over (tracker: backend-handoff sync-layer section):
 * - No client create. `POST /v1/conversations` is
 *   `process_in_progress_conversation` — a pipeline entry that finalizes an
 *   already-server-owned in-progress record. It is not an idempotent
 *   client-id create. The contract therefore omits `create` (see
 *   `contracts/src/domain/conversations.ts` header). `conversationsTransport`
 *   still accepts an `onServerAssignedId` callback for signature parity with
 *   tasks/memories transports; it never fires until a rewrite honors D2 create.
 * - There is no ids-only endpoint (tasks' `/v1/action-items/ids` has no
 *   conversations analog). `fetchConversationIdSnapshot` synthesizes the
 *   closest honest snapshot: one bounded page of `GET /v1/conversations`
 *   (bare JSON array), `complete: true` only when the page came back short of
 *   the requested limit. A full page is `complete: false` so reconcile never
 *   deletes local rows on an under-read.
 * - That list endpoint defaults to `statuses=processing,completed` (and
 *   `include_discarded=true`). An "unfiltered" call is therefore NOT the whole
 *   set — `in_progress` / `merging` / `failed` are excluded. We leave the
 *   default filter in place rather than invent a product-wide status set;
 *   callers must treat the snapshot as filtered.
 * - `/v1/conversations/count` was considered and NOT used to strengthen
 *   `complete`: a count matching the page size proves cardinality, not set
 *   identity, and a count/page race under offset pagination can lie either
 *   direction. Wrong `complete: true` is data loss via `Projection.reconcile`.
 * - Patch is NOT one wire request. Memories already fans a keyed patch across
 *   per-field endpoints; conversations do the same with four legacy shapes:
 *     - title:      `PATCH /v1/conversations/{id}/title?title=`     (query, no body)
 *     - starred:    `PATCH /v1/conversations/{id}/starred?starred=` (query, no body)
 *     - visibility: `PATCH /v1/conversations/{id}/visibility?value=` (query, no body)
 *     - folderId:   `PATCH /v1/conversations/{id}/folder`           body `{folder_id}`
 *       (this last endpoint lives in the folders router, not conversations)
 *   Multi-field patches are sequential and NOT atomic: stop at first failure.
 * - Delete: `DELETE /v1/conversations/{id}?cascade=false`. The runtime default
 *   is currently `false`, but the source carries `# TODO(Q8-gated)` that the
 *   *ratified* default is `cascade=true` and has not been flipped. This adapter
 *   does not decide that product question — it sends `cascade=false`
 *   explicitly so behavior stays pinned to today's runtime default even if the
 *   server default flips later. Cascade-true (also delete derived memories /
 *   action items / audio) is out of scope for this sync slice.
 * - Omitted from the sync record (documented, not modeled): transcript_segments
 *   (list may OMIT them; detail may return [] for locked/redacted even when
 *   data exists — empty vs omitted is ambiguous, so we never collapse either
 *   into "transcript is empty" by putting the field on the sync record),
 *   photos, audio_files, apps_results / plugins_results, geolocation,
 *   external_data, post-processing, calendar_event, language, deferred,
 *   data_protection_level, suggested apps, action-items sub-resources, etc.
 * - Out-of-scope endpoints deliberately not modeled: finalize, reprocess,
 *   merge, search, calendar link/unlink, photos, transcripts, recording,
 *   analytics, suggested-apps, test-prompt, action-items sub-resources,
 *   segment speaker assignment, shared-conversation reads, segment text /
 *   summary app-result patches.
 */

import type { Conversation, ConversationIdSnapshot, ConversationOp, ConversationPatch } from "@omi-core/contracts";
import { parseRecordId } from "@omi-core/contracts";
import type { PendingOp } from "@omi-core/sync";
import { classifyStatus, type HttpClient } from "./http.js";

export type ConversationSendResult =
  | { ok: true; serverRevision?: string; serverAssignedId?: string }
  | { ok: false; failure: import("@omi-core/contracts").WriteFailure };

export async function sendConversationOp(http: HttpClient, op: ConversationOp): Promise<ConversationSendResult> {
  switch (op.op) {
    case "patch": {
      for (const step of wirePatchSteps(op.id, op.patch)) {
        const res = await http.request(step.method, step.path, step.body);
        if (res.status !== 200) {
          return { ok: false, failure: classifyStatus(res, `patch conversation ${op.id} (${step.field})`) };
        }
      }
      return { ok: true };
    }
    case "delete": {
      // Explicit cascade=false — see file header (Q8-gated default ambiguity).
      const res = await http.request(
        "DELETE",
        `/v1/conversations/${encodeURIComponent(op.id)}?cascade=false`,
      );
      if (res.status === 200 || res.status === 204) return { ok: true };
      // Deleting something already gone is success, not failure.
      if (res.status === 404) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `delete conversation ${op.id}`) };
    }
  }
}

/**
 * Keyed patch → an ordered list of wire requests. Absent key = no request
 * for that field at all — never a default, and never a field smuggled onto
 * another field's request. Order (title, starred, visibility, folderId) is
 * arbitrary but fixed, so retries of the same patch hit the same sequence.
 */
function wirePatchSteps(
  id: string,
  p: ConversationPatch,
): Array<{ field: string; method: "PATCH"; path: string; body?: unknown }> {
  const steps: Array<{ field: string; method: "PATCH"; path: string; body?: unknown }> = [];
  const encoded = encodeURIComponent(id);
  if (p.title !== undefined) {
    steps.push({
      field: "title",
      method: "PATCH",
      path: `/v1/conversations/${encoded}/title?title=${encodeURIComponent(p.title)}`,
    });
  }
  if (p.starred !== undefined) {
    steps.push({
      field: "starred",
      method: "PATCH",
      path: `/v1/conversations/${encoded}/starred?starred=${p.starred ? "true" : "false"}`,
    });
  }
  if (p.visibility !== undefined) {
    steps.push({
      field: "visibility",
      method: "PATCH",
      path: `/v1/conversations/${encoded}/visibility?value=${encodeURIComponent(p.visibility)}`,
    });
  }
  if (p.folderId !== undefined) {
    steps.push({
      field: "folderId",
      method: "PATCH",
      path: `/v1/conversations/${encoded}/folder`,
      body: { folder_id: p.folderId },
    });
  }
  return steps;
}

/**
 * Honest ids snapshot: no legacy endpoint returns ids alone, so we page the
 * list endpoint once and only claim completeness when the page came back
 * short of what we asked for (a full page means there may be more). See file
 * header for the default-statuses filter caveat and why `/count` is unused.
 */
export async function fetchConversationIdSnapshot(
  http: HttpClient,
  limit = 5000,
): Promise<ConversationIdSnapshot | null> {
  const res = await http.request("GET", `/v1/conversations?limit=${limit}&offset=0`);
  if (res.status !== 200) return null;
  if (!Array.isArray(res.json)) return null; // a 200 with an unexpected body must never become a snapshot
  const rows = res.json as unknown[];
  const ids: string[] = [];
  for (const raw of rows) {
    const r = raw as Record<string, unknown>;
    if (typeof r["id"] === "string") ids.push(r["id"]);
  }
  // ARCHITECT RULING (2026-08-07): the list endpoint filters by default
  // statuses (processing,completed), so this snapshot structurally cannot see
  // in_progress/merging/failed conversations. A filtered source may NEVER back
  // a complete snapshot — reconcile would delete the filtered-out rows locally.
  // Until an unfiltered ids endpoint exists (backend-rewrite requirement),
  // this snapshot only ever ADDS knowledge.
  return { setVersion: contentHash(ids), complete: false, ids };
}

export async function fetchConversations(
  http: HttpClient,
  limit = 500,
  offset = 0,
): Promise<Conversation[] | null> {
  const res = await http.request("GET", `/v1/conversations?limit=${limit}&offset=${offset}`);
  if (res.status !== 200) return null;
  const rows = Array.isArray(res.json) ? (res.json as unknown[]) : [];
  const conversations: Conversation[] = [];
  for (const raw of rows) {
    const c = wireToConversation(raw);
    if (c) conversations.push(c);
  }
  return conversations;
}

/** Wire row → contract Conversation. Unparseable rows are dropped by the
 * caller's Degraded path — this function only says yes or no. */
export function wireToConversation(raw: unknown): Conversation | null {
  const r = raw as Record<string, unknown>;
  const parsed = typeof r["id"] === "string" ? parseRecordId(r["id"]) : null;
  if (!parsed) return null;
  const structured =
    r["structured"] !== null && typeof r["structured"] === "object"
      ? (r["structured"] as Record<string, unknown>)
      : {};
  const visibilityRaw = r["visibility"];
  const visibility: Conversation["visibility"] =
    visibilityRaw === "public" ? "public" : visibilityRaw === "shared" ? "shared" : "private";
  return {
    id: parsed.id,
    title: typeof structured["title"] === "string" ? structured["title"] : "",
    overview: typeof structured["overview"] === "string" ? structured["overview"] : "",
    createdAt: isoToMs(r["created_at"]) ?? 0,
    updatedAt: isoToMs(r["updated_at"]) ?? 0,
    startedAt: isoToMs(r["started_at"]),
    finishedAt: isoToMs(r["finished_at"]),
    source: typeof r["source"] === "string" ? r["source"] : "omi",
    status: typeof r["status"] === "string" ? r["status"] : "unknown", // absent must not masquerade as terminal
    discarded: r["discarded"] === true,
    starred: r["starred"] === true,
    visibility,
    isLocked: r["is_locked"] === true,
    folderId: typeof r["folder_id"] === "string" ? r["folder_id"] : null,
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

/** Bind the adapter to the sync Transport interface. Alias hook kept for
 * signature parity with tasks/memories; unused while create is omitted. */
export function conversationsTransport(
  http: HttpClient,
  onServerAssignedId: (localId: string, serverId: string) => void,
): { send(op: PendingOp): Promise<ConversationSendResult> } {
  return {
    async send(op: PendingOp): Promise<ConversationSendResult> {
      const domainOp = JSON.parse(op.payload) as ConversationOp;
      const result = await sendConversationOp(http, domainOp);
      if (result.ok && result.serverAssignedId !== undefined) {
        onServerAssignedId(domainOp.id, result.serverAssignedId);
      }
      return result;
    },
  };
}
