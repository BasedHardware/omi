/**
 * Client adapter for the ratified Chat wire.
 *
 * The service is canonical. Reads use its opaque backward keyset cursor; sends
 * replay the complete authored create operation; and a successful generation
 * terminates only with the typed canonical-message frame, never a final delta.
 * Base URL, credentials, and contract-version headers remain host concerns.
 */

import type {
  ChatAcceptedFrame,
  ChatAttachment,
  ChatCapabilitiesWire,
  ChatGenerationFrame,
  ChatHistoryEnvelope,
  ChatMessage,
  ChatMessageIdSnapshot,
  ChatMessageOp,
  ChatMessageSender,
  ChatMessageType,
  ChatTerminalFrame,
  HttpClient,
  WriteFailure,
} from "@omi-core/contracts";
import { parseRecordId } from "@omi-core/contracts";
import { classifyStatus } from "@omi-core/kernel";

export const PLATFORM_CHAT_MESSAGES_PATH = "/v1/chat-messages";
export const PLATFORM_CHAT_ATTACHMENTS_PATH = "/v1/chat-attachments";

export function platformChatGenerationEventsPath(generationId: string): string {
  return `${platformChatGenerationPath(generationId)}/events`;
}

export function platformChatGenerationPath(generationId: string): string {
  return `/v1/chat-generations/${encodeURIComponent(generationId)}`;
}

export type ChatSendResult =
  | {
      ok: true;
      accepted: ChatAcceptedFrame;
      terminal: ChatTerminalFrame;
      serverRevision?: string;
    }
  | { ok: false; failure: WriteFailure };

export interface ChatGenerationTerminalDelivery {
  readonly accepted: ChatAcceptedFrame;
  readonly terminal: ChatTerminalFrame;
}

export type ChatAdmissionResult =
  | { ok: true; serverRevision?: string }
  | { ok: false; failure: WriteFailure };

export interface ChatGenerationReconnectRequest {
  readonly method: "GET";
  readonly path: string;
  readonly headers: { readonly "Last-Event-ID": string };
}

/** Auth/base URL stay host-owned; this seam makes the SSE cursor non-optional. */
export interface ChatGenerationReconnectTransport {
  request(request: ChatGenerationReconnectRequest): Promise<import("@omi-core/contracts").HttpResponse>;
}

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0;
}

function parseSender(value: unknown): ChatMessageSender {
  if (value === "human" || value === "ai") return value;
  return "unknown";
}

function parseType(value: unknown): ChatMessageType {
  if (value === "text" || value === "day_summary") return value;
  return "unknown";
}

function wireToChatAttachment(raw: unknown): ChatAttachment | null {
  if (!isRecord(raw)) return null;
  if (
    typeof raw["id"] !== "string" ||
    typeof raw["displayName"] !== "string" ||
    typeof raw["mediaType"] !== "string" ||
    !isNonNegativeInteger(raw["sizeBytes"]) ||
    !isNullableString(raw["contentReference"]) ||
    raw["contentReference"] === ""
  ) {
    return null;
  }
  return {
    id: raw["id"],
    displayName: raw["displayName"],
    mediaType: raw["mediaType"],
    sizeBytes: raw["sizeBytes"],
    contentReference: raw["contentReference"],
  };
}

/** Ratified camel-case wire row → domain record. Unparseable → null. */
export function wireToChatMessage(raw: unknown): ChatMessage | null {
  if (!isRecord(raw)) return null;
  const parsedId = typeof raw["id"] === "string" ? parseRecordId(raw["id"]) : null;
  const sender = parseSender(raw["sender"]);
  const type = parseType(raw["type"]);
  const generationOutcome = raw["generationOutcome"];
  if (
    parsedId === null ||
    typeof raw["text"] !== "string" ||
    !isNonNegativeInteger(raw["createdAt"]) ||
    !isNonNegativeInteger(raw["updatedAt"]) ||
    !isNullableString(raw["chatSessionId"]) ||
    !isNullableString(raw["appId"]) ||
    !isNonNegativeInteger(raw["journalRevision"]) ||
    typeof raw["payloadHash"] !== "string" ||
    typeof raw["messageSource"] !== "string" ||
    !(raw["rating"] === null || typeof raw["rating"] === "number") ||
    typeof raw["reported"] !== "boolean" ||
    !(generationOutcome === null ||
      generationOutcome === "completed" ||
      generationOutcome === "cancelled") ||
    (sender === "human" && generationOutcome !== null) ||
    (sender === "ai" && generationOutcome === null) ||
    !isNullableString(raw["revision"]) ||
    !Array.isArray(raw["attachments"])
  ) {
    return null;
  }
  const attachments: ChatAttachment[] = [];
  for (const attachment of raw["attachments"]) {
    const parsed = wireToChatAttachment(attachment);
    if (parsed === null) return null;
    attachments.push(parsed);
  }
  const fields = {
    id: parsedId.id,
    text: raw["text"],
    type,
    createdAt: raw["createdAt"],
    updatedAt: raw["updatedAt"],
    chatSessionId: raw["chatSessionId"],
    appId: raw["appId"],
    journalRevision: raw["journalRevision"],
    payloadHash: raw["payloadHash"],
    messageSource: raw["messageSource"],
    rating: raw["rating"],
    reported: raw["reported"],
    revision: raw["revision"],
    attachments,
  };
  if (sender === "human") return { ...fields, sender, generationOutcome: null };
  if (sender === "ai") {
    return generationOutcome === "completed"
      ? { ...fields, sender, generationOutcome }
      : { ...fields, sender, generationOutcome: "cancelled" };
  }
  return { ...fields, sender, generationOutcome };
}

function wireToCapabilities(raw: unknown): ChatCapabilitiesWire | null {
  if (!isRecord(raw)) return null;
  if (
    !isNonNegativeInteger(raw["maxAttachmentsPerMessage"]) ||
    !isNonNegativeInteger(raw["maxAttachmentBytes"]) ||
    !Array.isArray(raw["allowedAttachmentMimeTypes"]) ||
    !raw["allowedAttachmentMimeTypes"].every((value) => typeof value === "string")
  ) {
    return null;
  }
  return {
    maxAttachmentsPerMessage: raw["maxAttachmentsPerMessage"],
    maxAttachmentBytes: raw["maxAttachmentBytes"],
    allowedAttachmentMimeTypes: [...raw["allowedAttachmentMimeTypes"]] as string[],
  };
}

/** Strict ratified history envelope. A malformed row invalidates the page. */
export function wireToChatHistoryEnvelope(raw: unknown): ChatHistoryEnvelope | null {
  if (!isRecord(raw) || !Array.isArray(raw["messages"]) || !isRecord(raw["page"])) {
    return null;
  }
  const capabilities = wireToCapabilities(raw["capabilities"]);
  const olderCursor = raw["page"]["olderCursor"];
  const hasOlder = raw["page"]["hasOlder"];
  if (
    capabilities === null ||
    !isNullableString(olderCursor) ||
    typeof hasOlder !== "boolean"
  ) {
    return null;
  }
  let page: ChatHistoryEnvelope["page"];
  if (hasOlder) {
    if (olderCursor === null) return null;
    page = { olderCursor, hasOlder: true };
  } else {
    if (olderCursor !== null) return null;
    page = { olderCursor, hasOlder: false };
  }
  const messages: ChatMessage[] = [];
  const seen = new Set<string>();
  for (const rawMessage of raw["messages"]) {
    const message = wireToChatMessage(rawMessage);
    if (message === null) return null;
    if (seen.has(message.id)) return null;
    seen.add(message.id);
    messages.push(message);
  }
  return { messages, page, capabilities };
}

export interface ChatHistoryRequest {
  readonly limit?: number;
  readonly olderCursor?: string | null;
}

/** Newest or older canonical page. The cursor is opaque and only round-tripped. */
export async function fetchChatHistoryPage(
  http: HttpClient,
  request: ChatHistoryRequest = {},
): Promise<ChatHistoryEnvelope | null> {
  const limit = clampLimit(request.limit);
  const query =
    request.olderCursor !== undefined && request.olderCursor !== null && request.olderCursor !== ""
      ? `?limit=${limit}&olderCursor=${encodeURIComponent(request.olderCursor)}`
      : `?limit=${limit}`;
  const response = await http.request("GET", `${PLATFORM_CHAT_MESSAGES_PATH}${query}`);
  if (response.status !== 200) return null;
  return wireToChatHistoryEnvelope(response.json);
}

export interface ChatReconcilePageRequest {
  readonly limit?: number;
  /** Opaque backward cursor; retained name for the projection-facing port. */
  readonly cursor?: string | null;
}

export interface ChatReconcilePage {
  readonly messages: readonly ChatMessage[];
  readonly nextCursor: string | null;
  readonly hasMore: boolean;
  readonly capabilities: ChatCapabilitiesWire;
}

/** Projection-facing view of one ratified keyset page. */
export async function fetchChatMessageReconcilePage(
  http: HttpClient,
  request: ChatReconcilePageRequest = {},
): Promise<ChatReconcilePage | null> {
  const envelope = await fetchChatHistoryPage(http, {
    ...(request.limit !== undefined ? { limit: request.limit } : {}),
    ...(request.cursor !== undefined ? { olderCursor: request.cursor } : {}),
  });
  if (envelope === null) return null;
  return {
    messages: envelope.messages,
    nextCursor: envelope.page.olderCursor,
    hasMore: envelope.page.hasOlder,
    capabilities: envelope.capabilities,
  };
}

/** Keyset page → deliberately incomplete id snapshot. */
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
  const ids = page.messages.map((message) => message.id);
  return { setVersion: contentHash(ids), complete: false, ids };
}

/** Fetch one canonical page of rows for projection upsert. */
export async function fetchChatMessages(
  http: HttpClient,
  limit = DEFAULT_RECONCILE_LIMIT,
): Promise<ChatMessage[] | null> {
  const page = await fetchChatMessageReconcilePage(http, { limit });
  return page === null ? null : [...page.messages];
}

/** Validate one parsed SSE data object against the ratified frame grammar. */
export function wireToChatGenerationFrame(raw: unknown): ChatGenerationFrame | null {
  if (!isRecord(raw) || typeof raw["kind"] !== "string") return null;
  switch (raw["kind"]) {
    case "accepted": {
      const message = wireToChatMessage(raw["message"]);
      const generation = raw["generation"];
      if (
        message === null ||
        message.sender !== "human" ||
        !isRecord(generation) ||
        typeof generation["id"] !== "string" ||
        generation["id"] === ""
      ) {
        return null;
      }
      return { kind: "accepted", message, generation: { id: generation["id"] } };
    }
    case "snapshot":
    case "delta":
      return typeof raw["text"] === "string" ? { kind: raw["kind"], text: raw["text"] } : null;
    case "done": {
      const message = wireToChatMessage(raw["message"]);
      if (
        message === null ||
        message.sender !== "ai" ||
        message.generationOutcome !== "completed"
      ) return null;
      return { kind: "done", message };
    }
    case "cancelled": {
      const message = wireToChatMessage(raw["message"]);
      if (
        message === null ||
        message.sender !== "ai" ||
        message.generationOutcome !== "cancelled"
      ) return null;
      return { kind: "cancelled", message };
    }
    case "failed": {
      const error = raw["error"];
      if (
        !isRecord(error) ||
        typeof error["code"] !== "string" ||
        typeof error["retryable"] !== "boolean"
      ) {
        return null;
      }
      return { kind: "failed", error: { code: error["code"], retryable: error["retryable"] } };
    }
    default:
      return null;
  }
}

/**
 * Parse a complete SSE transcript. Every data event needs an opaque id and its
 * event name must agree with `data.kind`; comments/heartbeats are ignored.
 */
interface ParsedChatGenerationEvent {
  readonly id: string;
  readonly frame: ChatGenerationFrame;
}

function parseChatGenerationEvents(text: string): readonly ParsedChatGenerationEvent[] | null {
  const events: ParsedChatGenerationEvent[] = [];
  const seenEventIds = new Set<string>();
  for (const block of text.replaceAll("\r\n", "\n").split("\n\n")) {
    if (block.trim() === "") continue;
    let eventName: string | null = null;
    let eventId: string | null = null;
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue;
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("id:")) eventId = line.slice(3).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length === 0) continue;
    if (eventId === null || eventId === "") return null;
    if (seenEventIds.has(eventId)) continue;
    seenEventIds.add(eventId);
    let raw: unknown;
    try {
      raw = JSON.parse(data.join("\n")) as unknown;
    } catch {
      return null;
    }
    const frame = wireToChatGenerationFrame(raw);
    if (frame === null || eventName !== frame.kind) return null;
    events.push({ id: eventId, frame });
  }
  return events;
}

export function parseChatGenerationEventStream(text: string): readonly ChatGenerationFrame[] | null {
  return parseChatGenerationEvents(text)?.map((event) => event.frame) ?? null;
}

function parseChatErrorCode(raw: unknown): string | null {
  if (!isRecord(raw) || !isRecord(raw["error"])) return null;
  return typeof raw["error"]["code"] === "string" ? raw["error"]["code"] : null;
}

function classifyChatSendStatus(response: Parameters<typeof classifyStatus>[0], detail: string): WriteFailure {
  if (response.status === 403) {
    // Chat's ratified wire makes forbidden permanent for this authorization
    // context. The shared taxonomy stays wrong-but-untouched here because its
    // 403=auth-invalid behavior is already consumed by tasks, memories,
    // folders, and conversations; changing that shared meaning requires a
    // separate blast-radius audit of contracts those domains do not share.
    return { kind: "permanent", reason: "validation", detail };
  }
  return classifyStatus(response, detail);
}

function malformedSuccess(detail: string): ChatSendResult {
  return {
    ok: false,
    failure: { kind: "retryable", unclassified: true, detail },
  };
}

/** Admit a send and consume its complete ratified SSE transcript. */
export async function sendChatMessageOp(
  http: HttpClient,
  op: ChatMessageOp,
  reconnect?: ChatGenerationReconnectTransport,
): Promise<ChatSendResult> {
  if (op.op !== "create") {
    return {
      ok: false,
      failure: {
        kind: "permanent",
        reason: "validation",
        detail: `ratified Chat wire does not define ${op.op} for message ${op.id}`,
      },
    };
  }
  const body: Extract<ChatMessageOp, { op: "create" }> = {
    op: "create",
    opId: op.opId,
    id: op.id,
    at: op.at,
    text: op.text,
    sender: "human",
    journalRevision: op.journalRevision,
    type: op.type ?? "text",
    appId: op.appId ?? null,
    chatSessionId: op.chatSessionId ?? null,
    messageSource: op.messageSource ?? DEFAULT_MESSAGE_SOURCE,
    metadata: op.metadata ?? null,
    attachmentIds: [...op.attachmentIds],
  };
  const response = await http.request("POST", PLATFORM_CHAT_MESSAGES_PATH, body);
  if (response.status !== 200 && response.status !== 201) {
    const code = parseChatErrorCode(response.json);
    const detail = `create chat message ${op.id}${code === null ? "" : `: ${code}`}`;
    return { ok: false, failure: classifyChatSendStatus(response, detail) };
  }
  if (response.text === undefined) {
    return malformedSuccess(`create chat message ${op.id}: successful response omitted SSE bytes`);
  }
  const initialEvents = parseChatGenerationEvents(response.text);
  let events = initialEvents === null ? null : [...initialEvents];
  let frames = events?.map((event) => event.frame) ?? null;
  if (
    frames === null ||
    frames.length < 1 ||
    frames[0]?.kind !== "accepted" ||
    frames.slice(1).some((frame) => frame.kind === "accepted")
  ) {
    return malformedSuccess(`create chat message ${op.id}: malformed or incomplete SSE transcript`);
  }
  const accepted = frames[0];
  if (accepted.message.id !== op.id) {
    return {
      ok: false,
      failure: {
        kind: "permanent",
        reason: "conflict",
        detail: `create chat message ${op.id}: accepted record id was ${accepted.message.id}`,
      },
    };
  }
  let terminal = frames.at(-1);
  let terminalCount = frames.filter(
    (frame) => frame.kind === "done" || frame.kind === "failed" || frame.kind === "cancelled",
  ).length;
  if (
    terminalCount === 0 &&
    reconnect !== undefined &&
    events !== null &&
    events.length > 0
  ) {
    const resumed = await reconnect.request({
      method: "GET",
      path: platformChatGenerationEventsPath(accepted.generation.id),
      headers: { "Last-Event-ID": events.at(-1)!.id },
    });
    if (resumed.status !== 200 || resumed.text === undefined) {
      return malformedSuccess(
        `create chat message ${op.id}: generation reconnect did not return SSE bytes`,
      );
    }
    const resumedEvents = parseChatGenerationEvents(resumed.text);
    if (resumedEvents === null) {
      return malformedSuccess(`create chat message ${op.id}: malformed generation reconnect`);
    }
    const observedIds = new Set(events.map((event) => event.id));
    const freshEvents = resumedEvents.filter((event) => !observedIds.has(event.id));
    if (freshEvents[0]?.frame.kind !== "snapshot") {
      return malformedSuccess(
        `create chat message ${op.id}: generation reconnect omitted its leading snapshot`,
      );
    }
    events = [...events, ...freshEvents];
    frames = events.map((event) => event.frame);
    terminal = frames.at(-1);
    terminalCount = frames.filter(
      (frame) => frame.kind === "done" || frame.kind === "failed" || frame.kind === "cancelled",
    ).length;
  }
  if (
    terminal === undefined ||
    terminalCount !== 1 ||
    (terminal.kind !== "done" && terminal.kind !== "failed" && terminal.kind !== "cancelled")
  ) {
    return malformedSuccess(`create chat message ${op.id}: stream ended without a terminal frame`);
  }
  const serverRevision = accepted.message.revision;
  return {
    ok: true,
    accepted,
    terminal,
    ...(serverRevision === null ? {} : { serverRevision }),
  };
}

/** Cancel is idempotent: 202 is newly accepted; 204 was already terminal/applied. */
export async function cancelChatGeneration(
  http: HttpClient,
  generationId: string,
): Promise<{ ok: true; state: "accepted" | "already-terminal" } | { ok: false; failure: WriteFailure }> {
  const response = await http.request("DELETE", platformChatGenerationPath(generationId));
  if (response.status === 204) return { ok: true, state: "already-terminal" };
  if (
    response.status === 202 &&
    isRecord(response.json) &&
    isRecord(response.json["cancellation"]) &&
    response.json["cancellation"]["state"] === "accepted"
  ) {
    return { ok: true, state: "accepted" };
  }
  return {
    ok: false,
    failure: classifyStatus(response, `cancel chat generation ${generationId}`),
  };
}

function clampLimit(requested: number | undefined): number {
  if (requested === undefined || !Number.isSafeInteger(requested) || requested < 1) {
    return DEFAULT_RECONCILE_LIMIT;
  }
  return Math.min(requested, DEFAULT_RECONCILE_LIMIT);
}

/** FNV-1a over the sorted id list — a stable synthetic set version. */
function contentHash(ids: readonly string[]): string {
  let hash = 0x811c9dc5;
  for (const id of [...ids].sort()) {
    for (let index = 0; index < id.length; index += 1) {
      hash ^= id.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
    }
    hash ^= 0x2c;
    hash = Math.imul(hash, 0x01000193);
  }
  return `fnv-${(hash >>> 0).toString(16)}`;
}

/** Bind the ratified create/replay operation to the sync Transport interface. */
export function chatMessagesTransport(
  http: HttpClient,
  onGenerationTerminal: (delivery: ChatGenerationTerminalDelivery) => void | Promise<void>,
  reconnect?: ChatGenerationReconnectTransport,
): { send(op: ChatTransportOp): Promise<ChatAdmissionResult> } {
  return {
    async send(op: ChatTransportOp): Promise<ChatAdmissionResult> {
      const domainOp = JSON.parse(op.payload) as ChatMessageOp;
      const result = await sendChatMessageOp(http, domainOp, reconnect);
      if (!result.ok) return result;
      // Admission belongs to the outbox; assistant generation delivery belongs
      // to the Chat store. Requiring this callback prevents a successful
      // admission from structurally discarding a failed terminal frame.
      await onGenerationTerminal({ accepted: result.accepted, terminal: result.terminal });
      return result.serverRevision === undefined
        ? { ok: true }
        : { ok: true, serverRevision: result.serverRevision };
    },
  };
}
