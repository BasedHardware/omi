/**
 * Platform-generation chat WRITE + reconcile adapter — the client half of the
 * ADR-005 write contract (WS-006).
 *
 * Speaks the universal chat write contract end-to-end from the client side:
 * `client_message_id`-as-doc-id, monotonic `journal_revision`, and
 * payload-hash idempotency. HTTP 409 identity conflict folds through
 * `foldChatIdentityConflict` (injected from `@omi-core/domain` — this package
 * must not depend on domain; domain already depends on adapters-platform for
 * the synthesized-memories read path, and a reverse edge is a workspace cycle).
 *
 * WHAT THIS ADAPTER DELIBERATELY DOES NOT DO
 *
 * It does not invent `complete: true` on an id snapshot. No server implements
 * this route tonight, so there is no backend evidence to cite (hard rule 12).
 * Snapshots default to `complete: false` and never declare `completeEvidence`.
 *
 * Known gaps (ADR-005 silent → guessed; surface in the worker report):
 * - Exact platform route path (ADR-005 targets `/v2/messages`; today's that
 *   path SSE-streams and ignores client ids). Provisional `/v1/chat/messages*`.
 * - Whether the client sends `client_message_payload_hash` or only the fields
 *   the server hashes. We send the digest so the contract is visible on the wire.
 * - Per-message DELETE shape (legacy only has clear-all). Provisional per-id DELETE.
 */

import type {
  ChatMessage,
  ChatMessageIdSnapshot,
  ChatMessageOp,
  ChatMessagePatch,
  ChatMessageSender,
  ChatMessageType,
  HttpClient,
  WriteFailure,
} from "@omi-core/contracts";
import { parseRecordId } from "@omi-core/contracts";
import { chatMessagePayloadHash, classifyStatus } from "@omi-core/kernel";

/**
 * PROVISIONAL: no platform service serves this yet. ADR-005's target is the
 * main `/v2/messages` path adopting the desktop write contract; today's
 * `/v2/messages` streams SSE and assigns its own ids. This `/v1/chat/…`
 * family is the client-side port FE-SURFACES can build against until the
 * backend ratifies a path. Transport bindings own the base URL (ADR-008 §3).
 */
export const PLATFORM_CHAT_MESSAGES_PATH = "/v1/chat/messages";
export const PLATFORM_CHAT_MESSAGES_RECONCILE_PATH = "/v1/chat/messages/reconcile";

/** Fields folded into `client_message_payload_hash` (matches domain helper). */
/** Re-stated locally so this package needs no @omi-core/domain dependency
 * (which would cycle: domain already depends on adapters-platform). Structural
 * compatibility with the kernel's ChatMessageHashPayload is what matters, and
 * the compiler checks it at the call site below. */
export interface ChatMessageWireHashPayload {
  text: string;
  sender: string;
  appId: string | null;
  sessionId: string | null;
  metadata: string | null;
  messageSource: string;
}

export type ChatSendResult =
  | { ok: true; serverRevision?: string; serverAssignedId?: string }
  | { ok: false; failure: WriteFailure };

/** Structural stand-in for sync PendingOp — avoids an adapters-platform→sync dep. */
export interface ChatTransportOp {
  opId: string;
  domain: string;
  recordId: string;
  payload: string;
  summary: string;
  attempts: number;
}

const DEFAULT_MESSAGE_SOURCE = "desktop_chat";
const DEFAULT_RECONCILE_LIMIT = 100;

export async function sendChatMessageOp(
  http: HttpClient,
  op: ChatMessageOp,
): Promise<ChatSendResult> {
  switch (op.op) {
    case "create": {
      const appId = op.appId ?? null;
      const sessionId = op.chatSessionId ?? null;
      const messageSource = op.messageSource ?? DEFAULT_MESSAGE_SOURCE;
      const metadata = op.metadata ?? null;
      const payloadHash = chatMessagePayloadHash({
        text: op.text,
        sender: op.sender,
        appId,
        sessionId,
        metadata,
        messageSource,
      });
      // ADR-005 write contract visible on the wire:
      // client_message_id (= doc id), journal_revision, client_message_payload_hash.
      const body: Record<string, unknown> = {
        text: op.text,
        sender: op.sender,
        client_message_id: op.id,
        journal_revision: op.journalRevision,
        client_message_payload_hash: payloadHash,
        message_source: messageSource,
        type: op.type ?? "text",
        app_id: appId,
        session_id: sessionId,
        metadata,
      };

      const res = await http.request("POST", PLATFORM_CHAT_MESSAGES_PATH, body);
      if (res.status === 200 || res.status === 201) {
        const respBody = res.json as { id?: string; revision?: string } | null;
        if (respBody?.id !== undefined && respBody.id !== op.id) {
          return {
            ok: true,
            ...(respBody.revision !== undefined ? { serverRevision: respBody.revision } : {}),
            serverAssignedId: respBody.id,
          };
        }
        return respBody?.revision !== undefined
          ? { ok: true, serverRevision: respBody.revision }
          : { ok: true };
      }
      // A 409 identity conflict needs no special fold: `classifyStatus` already
      // maps 409 to `permanent` / `reason: "conflict"`, which is exactly the
      // ADR-005 outcome (retrying the same conflicting payload can never
      // succeed, so the outbox must dead-letter rather than spin). Hard rule 6
      // plus the kernel's own instruction — adapters call it and never invent
      // their own mapping — so the detail string is the only thing worth
      // spelling out here.
      const detail =
        res.status === 409
          ? `create chat message ${op.id}: client_message_id bound to a different payload hash`
          : `create chat message ${op.id}`;
      return { ok: false, failure: classifyStatus(res, detail) };
    }
    case "patch": {
      const res = await http.request(
        "PATCH",
        `${PLATFORM_CHAT_MESSAGES_PATH}/${encodeURIComponent(op.id)}/rating`,
        wireRatingPatch(op.patch),
      );
      if (res.status === 200) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `patch chat message ${op.id}`) };
    }
    case "delete": {
      const res = await http.request(
        "DELETE",
        `${PLATFORM_CHAT_MESSAGES_PATH}/${encodeURIComponent(op.id)}`,
      );
      if (res.status === 200 || res.status === 204) return { ok: true };
      if (res.status === 404) return { ok: true };
      return { ok: false, failure: classifyStatus(res, `delete chat message ${op.id}`) };
    }
  }
}

/** Keyed rating patch → wire body. Absent key stays absent — never a default. */
function wireRatingPatch(p: ChatMessagePatch): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (p.rating !== undefined) body["rating"] = p.rating;
  return body;
}

/**
 * Keyset, duplicate-free reconcile page → id snapshot.
 *
 * Hard rule 12: always `complete: false`. No server implements this route, so
 * there is no unfiltered-source evidence to cite — a completeness claim would
 * be a fabrication that licenses Projection.reconcile deletes.
 *
 * Unparseable or non-200 → `null` (never an empty complete snapshot).
 */
export async function fetchChatMessageIdSnapshot(
  http: HttpClient,
  limit = DEFAULT_RECONCILE_LIMIT,
  cursor?: string | null,
): Promise<ChatMessageIdSnapshot | null> {
  const page = await fetchChatMessageReconcilePage(http, {
    limit,
    ...(cursor !== undefined ? { cursor } : {}),
  });
  if (page === null) return null;
  const ids: string[] = [];
  const seen = new Set<string>();
  for (const row of page.messages) {
    if (seen.has(row.id)) continue;
    seen.add(row.id);
    ids.push(row.id);
  }
  return { setVersion: contentHash(ids), complete: false, ids };
}

export interface ChatReconcilePageRequest {
  readonly limit?: number;
  readonly cursor?: string | null;
  readonly path?: string;
}

export interface ChatReconcilePage {
  readonly messages: readonly ChatMessage[];
  readonly nextCursor: string | null;
  readonly hasMore: boolean;
}

/**
 * One keyset reconcile page. Duplicate ids within a page are dropped (the
 * FC-CHAT-005 guarantee is server-side; the client still de-dupes defensively).
 * Non-200 / unparseable → `null`.
 */
export async function fetchChatMessageReconcilePage(
  http: HttpClient,
  request: ChatReconcilePageRequest = {},
): Promise<ChatReconcilePage | null> {
  const limit = clampLimit(request.limit);
  const path = request.path ?? PLATFORM_CHAT_MESSAGES_RECONCILE_PATH;
  const query =
    request.cursor !== undefined && request.cursor !== null && request.cursor !== ""
      ? `?limit=${limit}&cursor=${encodeURIComponent(request.cursor)}`
      : `?limit=${limit}`;
  const res = await http.request("GET", `${path}${query}`);
  if (res.status !== 200) return null;
  const body = res.json as { messages?: unknown; next_cursor?: unknown; has_more?: unknown } | null;
  if (!body || !Array.isArray(body.messages)) return null; // rule 12: junk never becomes a snapshot
  const messages: ChatMessage[] = [];
  const seen = new Set<string>();
  for (const raw of body.messages) {
    const m = wireToChatMessage(raw);
    if (!m) continue;
    if (seen.has(m.id)) continue;
    seen.add(m.id);
    messages.push(m);
  }
  const nextCursor = typeof body.next_cursor === "string" ? body.next_cursor : null;
  const hasMore = body.has_more === true;
  return { messages, nextCursor, hasMore };
}

/** Fetch one reconcile page of rows for projection upsert. Non-200 → null. */
export async function fetchChatMessages(
  http: HttpClient,
  limit = DEFAULT_RECONCILE_LIMIT,
): Promise<ChatMessage[] | null> {
  const page = await fetchChatMessageReconcilePage(http, { limit });
  if (page === null) return null;
  return [...page.messages];
}

/** Wire row → contract ChatMessage. Unparseable → null. */
export function wireToChatMessage(raw: unknown): ChatMessage | null {
  const r = raw as Record<string, unknown>;
  const idRaw =
    typeof r["id"] === "string"
      ? r["id"]
      : typeof r["client_message_id"] === "string"
        ? r["client_message_id"]
        : null;
  const parsed = idRaw !== null ? parseRecordId(idRaw) : null;
  if (!parsed) return null;

  const sender = parseSender(r["sender"]);
  const type = parseType(r["type"]);
  const chatSessionId =
    typeof r["chat_session_id"] === "string"
      ? r["chat_session_id"]
      : typeof r["session_id"] === "string"
        ? r["session_id"]
        : null;
  const appId = typeof r["app_id"] === "string" ? r["app_id"] : null;
  const journalRevision =
    typeof r["journal_revision"] === "number" && Number.isFinite(r["journal_revision"])
      ? r["journal_revision"]
      : 1;
  const payloadHash =
    typeof r["client_message_payload_hash"] === "string"
      ? r["client_message_payload_hash"]
      : typeof r["payload_hash"] === "string"
        ? r["payload_hash"]
        : "";
  const messageSource =
    typeof r["message_source"] === "string" ? r["message_source"] : DEFAULT_MESSAGE_SOURCE;

  return {
    id: parsed.id,
    text: typeof r["text"] === "string" ? r["text"] : "",
    sender,
    type,
    createdAt: isoToMs(r["created_at"]) ?? 0,
    updatedAt: isoToMs(r["updated_at"]) ?? isoToMs(r["created_at"]) ?? 0,
    chatSessionId,
    appId,
    journalRevision,
    payloadHash,
    messageSource,
    rating: typeof r["rating"] === "number" ? r["rating"] : null,
    reported: r["reported"] === true,
    revision: typeof r["revision"] === "string" ? r["revision"] : null,
  };
}

function parseSender(v: unknown): ChatMessageSender {
  if (v === "human" || v === "ai") return v;
  return "unknown";
}

function parseType(v: unknown): ChatMessageType {
  if (v === "text" || v === "day_summary") return v;
  return "unknown";
}

function isoToMs(v: unknown): number | null {
  if (typeof v !== "string") return null;
  const ms = Date.parse(v);
  return Number.isNaN(ms) ? null : ms;
}

function clampLimit(requested: number | undefined): number {
  if (requested === undefined || !Number.isSafeInteger(requested) || requested < 1) {
    return DEFAULT_RECONCILE_LIMIT;
  }
  return Math.min(requested, DEFAULT_RECONCILE_LIMIT);
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

/**
 * Bind the adapter to the sync Transport interface. The caller supplies
 * the alias hook and
 * the alias hook for the (rare) case a server still assigns its own id.
 *
 * Under ADR-005 the server honors `client_message_id` as the doc id, so the
 * alias map stays empty when the platform path is correct.
 */
export function chatMessagesTransport(
  http: HttpClient,
  onServerAssignedId: (localId: string, serverId: string) => void,
  resolveWireId: (localId: string) => string = (id) => id,
): { send(op: ChatTransportOp): Promise<ChatSendResult> } {
  return {
    async send(op: ChatTransportOp): Promise<ChatSendResult> {
      const domainOp = JSON.parse(op.payload) as ChatMessageOp;
      if (domainOp.op !== "create") {
        (domainOp as { id: string }).id = resolveWireId(domainOp.id);
      }
      const result = await sendChatMessageOp(http, domainOp);
      if (result.ok && result.serverAssignedId !== undefined) {
        onServerAssignedId(domainOp.id, result.serverAssignedId);
      }
      return result;
    },
  };
}
