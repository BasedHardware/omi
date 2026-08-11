// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import { createHash } from "node:crypto";
import type { Hono } from "hono";

import {
  APP_CONTRACT_VERSION_HEADER,
  resolveDeclaredContractVersion,
} from "@omi-core/ratified-contracts/projections/synthesized";

import type { DevPrincipal } from "../auth/dev-token";
import type { AccountControlProjectionStore } from "../control/projection-store";
import type { ChatGenerationSupervisor } from "../chat/generation-supervisor";
import {
  ExpiredChatHistoryCursorError,
  InvalidChatHistoryCursorError,
  type ChatHistoryCursorCodec,
} from "../chat/history-cursor";
import type { ServedCounter } from "../observability/served-count";
import type { ChatAdmission } from "../stores/chat-admission";
import type { ChatAttachmentsStore } from "../stores/chat-attachments-store";
import {
  CHAT_ALLOWED_ATTACHMENT_MIME_TYPES,
  CHAT_MAX_ATTACHMENT_BYTES,
  CHAT_MAX_ATTACHMENTS_PER_MESSAGE,
  isAllowedChatAttachmentMimeType,
  MAIN_CHAT_ATTACHMENT_SCOPE,
} from "../chat/attachment-policy";
import type {
  ChatMessageRecord,
  ChatMessagesStore,
  WritableChatMessageType,
} from "../stores/chat-messages-store";
import type {
  ChatGenerationEvent,
  ChatGenerationEventsStore,
} from "../stores/chat-generation-events-store";

export const CHAT_MESSAGES_PATH = "/v1/chat-messages";
export const CHAT_GENERATIONS_PATH = "/v1/chat-generations";
export const CHAT_CAPABILITIES = Object.freeze({
  maxAttachmentsPerMessage: CHAT_MAX_ATTACHMENTS_PER_MESSAGE,
  maxAttachmentBytes: CHAT_MAX_ATTACHMENT_BYTES,
  allowedAttachmentMimeTypes: CHAT_ALLOWED_ATTACHMENT_MIME_TYPES,
});

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 100;
const SERVICE_UNAVAILABLE_RETRY_AFTER_SECONDS = 60;
const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

export interface ChatMessagesRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly messages: ChatMessagesStore;
  readonly attachments: ChatAttachmentsStore;
  readonly control: AccountControlProjectionStore;
  readonly admission: ChatAdmission;
  readonly supervisor: ChatGenerationSupervisor;
  readonly events: ChatGenerationEventsStore;
  readonly cursor: ChatHistoryCursorCodec;
  readonly counter: ServedCounter;
  readonly nowEpochMilliseconds: () => number;
  readonly nowEpochSeconds: () => number;
  readonly cursorTtlSeconds: number;
  readonly generationId: (accountId: string, messageId: string) => string;
  readonly acceptedEventId: (accountId: string, generationId: string) => string;
  /** Counts only a newly committed message + accepted-generation admission. */
  readonly recordAcceptedAdmission: () => void;
  readonly revision: (
    accountId: string,
    messageId: string,
    journalRevision: number,
    payloadHash: string,
  ) => string;
}

interface ParsedCreate {
  readonly id: string;
  readonly at: number;
  readonly text: string;
  readonly journalRevision: number;
  readonly type: WritableChatMessageType;
  readonly messageSource: string;
  readonly metadata: string | null;
  readonly attachmentIds: readonly string[];
}

const errorBody = (code: string, action: string, retryable = false): string =>
  JSON.stringify({ error: { code, retryable, action } });

const response = (
  value: unknown,
  status: number,
  extraHeaders: Readonly<Record<string, string>> = {},
): Response =>
  new Response(typeof value === "string" ? value : JSON.stringify(value), {
    status,
    headers: { ...JSON_HEADERS, ...extraHeaders },
  });

const unauthorized = (): Response => response(errorBody("unauthorized", "reauthenticate"), 401);
const badRequest = (): Response => response(errorBody("bad_request", "edit_request"), 400);
const validation = (): Response => response(errorBody("validation", "edit_request"), 422);
const conflict = (): Response => response(
  errorBody("client_message_id_conflict", "edit_request"),
  409,
);
const entitlement = (): Response => response(errorBody("entitlement", "upgrade"), 402);
const unavailable = (): Response => response(
  errorBody("service_unavailable", "retry", true),
  503,
  { "retry-after": String(SERVICE_UNAVAILABLE_RETRY_AFTER_SECONDS) },
);
const generationNotFound = (): Response => response(
  JSON.stringify({ error: { code: "not_found", retryable: false } }),
  404,
);
const generationReplayExpired = (): Response => response(
  errorBody("generation_replay_expired", "refresh_history"),
  410,
);
const attachmentNotFound = (): Response => response(errorBody("not_found", "edit_request"), 404);

const bearerPrincipal = (
  authorization: string | undefined,
  resolvePrincipal: ChatMessagesRouteDependencies["resolvePrincipal"],
): DevPrincipal | null => {
  return bearerAuthentication(authorization, resolvePrincipal)?.principal ?? null;
};

const bearerAuthentication = (
  authorization: string | undefined,
  resolvePrincipal: ChatMessagesRouteDependencies["resolvePrincipal"],
): { readonly token: string; readonly principal: DevPrincipal } | null => {
  if (authorization === undefined || !authorization.startsWith("Bearer ")) return null;
  const token = authorization.slice("Bearer ".length);
  if (token.length === 0) return null;
  const principal = resolvePrincipal(token);
  return principal === null ? null : Object.freeze({ token, principal });
};

const recordContractVersion = (header: string | undefined): void => {
  void resolveDeclaredContractVersion(header);
};

const exactObject = (
  value: unknown,
  required: readonly string[],
  optional: readonly string[] = [],
): value is Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return false;
  const keys = Object.keys(value);
  const allowed = new Set([...required, ...optional]);
  return required.every((key) => Object.hasOwn(value, key))
    && keys.every((key) => allowed.has(key));
};

const parseStringArray = (value: unknown): readonly string[] | null => {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || item.length === 0)) {
    return null;
  }
  return Object.freeze([...value]);
};

const parseCreate = (value: unknown): ParsedCreate | null => {
  if (!exactObject(
    value,
    ["op", "opId", "id", "at", "text", "sender", "journalRevision"],
    [
      "type", "appId", "chatSessionId", "messageSource", "metadata",
      "attachmentIds",
    ],
  )) return null;
  if (value.op !== "create" || typeof value.opId !== "string" || value.opId.length === 0
    || typeof value.id !== "string" || value.id.length === 0
    || !Number.isSafeInteger(value.at) || (value.at as number) < 0
    || typeof value.text !== "string" || value.sender !== "human"
    || !Number.isSafeInteger(value.journalRevision) || (value.journalRevision as number) < 0
    || !(value.type === undefined || value.type === "text" || value.type === "day_summary")
    || !(value.appId === undefined || value.appId === null)
    || !(value.chatSessionId === undefined || value.chatSessionId === null)
    || !(value.messageSource === undefined || typeof value.messageSource === "string")
    || !(value.metadata === undefined || value.metadata === null || typeof value.metadata === "string")) {
    return null;
  }
  const attachmentIds = value.attachmentIds === undefined
    ? Object.freeze([] as string[])
    : parseStringArray(value.attachmentIds);
  if (attachmentIds === null) return null;
  return Object.freeze({
    id: value.id,
    at: value.at as number,
    text: value.text,
    journalRevision: value.journalRevision as number,
    type: (value.type ?? "text") as WritableChatMessageType,
    messageSource: (value.messageSource ?? "desktop_chat") as string,
    metadata: (value.metadata ?? null) as string | null,
    attachmentIds,
  });
};

type Json = null | boolean | number | string | readonly Json[] | { readonly [key: string]: Json };
const canonicalJson = (value: Json): string => {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.entries(value).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
    .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`).join(",")}}`;
};

export const chatMessagePayloadHash = (create: ParsedCreate): string => {
  const subject: { readonly [key: string]: Json } = {
    at: create.at,
    attachmentIds: create.attachmentIds,
    appId: null,
    chatSessionId: null,
    messageSource: create.messageSource,
    metadata: create.metadata,
    sender: "human",
    text: create.text,
    type: create.type,
  };
  return `sha256:${createHash("sha256").update(canonicalJson(subject), "utf8").digest("hex")}`;
};

const parseHistoryQuery = (request: Request): {
  readonly limit: number;
  readonly olderCursor: string | null;
} | null => {
  let url: URL;
  try {
    url = new URL(request.url);
  } catch {
    return null;
  }
  const counts = new Map<string, number>();
  for (const [key] of url.searchParams) counts.set(key, (counts.get(key) ?? 0) + 1);
  if ([...counts].some(([key, count]) => !["limit", "olderCursor"].includes(key) || count !== 1)) {
    return null;
  }
  const rawLimit = url.searchParams.get("limit");
  if (rawLimit !== null && !/^(?:[1-9]|[1-9][0-9]|100)$/.test(rawLimit)) return null;
  const olderCursor = url.searchParams.get("olderCursor");
  if (olderCursor === "") return null;
  return { limit: rawLimit === null ? DEFAULT_LIMIT : Number(rawLimit), olderCursor };
};

const TERMINAL_KINDS = new Set(["done", "failed", "cancelled"]);
const isTerminal = (event: ChatGenerationEvent): boolean => TERMINAL_KINDS.has(event.frame.kind);

type ChatGenerationOutcome = "completed" | "cancelled" | null;
type ChatWireMessage = ChatMessageRecord & {
  readonly generationOutcome: ChatGenerationOutcome;
};

const withGenerationOutcome = (
  message: ChatMessageRecord,
  generationOutcome: ChatGenerationOutcome,
): ChatWireMessage => Object.freeze({ ...message, generationOutcome });

const sameCanonicalMessage = (left: ChatMessageRecord, right: ChatMessageRecord): boolean =>
  canonicalJson(left as unknown as Json) === canonicalJson(right as unknown as Json);

/**
 * The terminal event is the authority for an assistant's outcome. The message
 * row deliberately does not duplicate that state, so an orphan or a mismatched
 * terminal fails closed instead of silently becoming a completed answer.
 */
const projectHistoryMessage = (
  accountId: string,
  message: ChatMessageRecord,
  messages: ChatMessagesStore,
  events: ChatGenerationEventsStore,
): ChatWireMessage => {
  if (message.sender !== "ai") return withGenerationOutcome(message, null);
  const stored = messages.readMessage(accountId, message.id);
  if (stored === null || stored.generationId === null
    || !sameCanonicalMessage(stored.message, message)) {
    throw new TypeError("canonical assistant has no matching generation identity");
  }
  const generationEvents = events.listAfter(accountId, stored.generationId, null);
  const terminals = generationEvents?.filter(isTerminal) ?? [];
  if (terminals.length !== 1) {
    throw new TypeError("canonical assistant has no unique terminal event");
  }
  const terminal = terminals[0]!;
  if ((terminal.frame.kind !== "done" && terminal.frame.kind !== "cancelled")
    || terminal.frame.message === null
    || !sameCanonicalMessage(terminal.frame.message, message)) {
    throw new TypeError("canonical assistant disagrees with its terminal event");
  }
  return withGenerationOutcome(
    message,
    terminal.frame.kind === "done" ? "completed" : "cancelled",
  );
};

type ExternalChatGenerationEvent = ChatGenerationEvent & {
  readonly frame: Exclude<ChatGenerationEvent["frame"], { readonly kind: "accepted" }>;
};

const isExternalGenerationEvent = (
  event: ChatGenerationEvent,
): event is ExternalChatGenerationEvent => event.frame.kind !== "accepted";

const projectExternalFrame = (
  frame: ExternalChatGenerationEvent["frame"],
): ExternalChatGenerationEvent["frame"] | Readonly<{
  kind: "done" | "cancelled";
  message: ChatWireMessage;
}> => {
  if (frame.kind !== "done" && frame.kind !== "cancelled") return frame;
  if (frame.kind === "cancelled" && frame.message === null) return frame;
  if (frame.message === null || frame.message.sender !== "ai") {
    throw new TypeError("terminal Chat frame has no canonical assistant message");
  }
  return Object.freeze({
    kind: frame.kind,
    message: withGenerationOutcome(
      frame.message,
      frame.kind === "done" ? "completed" : "cancelled",
    ),
  });
};

const encodeSse = (event: ExternalChatGenerationEvent): Uint8Array => new TextEncoder().encode(
  `event: ${event.frame.kind}\nid: ${event.id}\ndata: ${JSON.stringify(projectExternalFrame(event.frame))}\n\n`,
);

const streamEvents = (input: {
  readonly accountId: string;
  readonly generationId: string;
  readonly events: ChatGenerationEventsStore;
  readonly initial: readonly ChatGenerationEvent[];
  readonly afterEventId: string | null;
  readonly signal: AbortSignal;
  readonly revalidate: () => boolean;
}): Response => {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;
  let cursor = input.afterEventId;
  const body = new ReadableStream<Uint8Array>({
    start(controller): void {
      const close = (): void => {
        if (stopped) return;
        stopped = true;
        if (timer !== null) clearTimeout(timer);
        controller.close();
      };
      const emit = (events: readonly ChatGenerationEvent[]): boolean => {
        for (const event of events) {
          cursor = event.id;
          // Admission is a durable dispatch record, not part of the external
          // generation grammar. Advance past it without projecting it.
          if (!isExternalGenerationEvent(event)) continue;
          controller.enqueue(encodeSse(event));
          if (isTerminal(event)) {
            close();
            return true;
          }
        }
        return false;
      };
      if (emit(input.initial)) return;
      const poll = (): void => {
        if (stopped) return;
        if (input.signal.aborted) {
          close();
          return;
        }
        try {
          if (!input.revalidate()) {
            close();
            return;
          }
        } catch {
          close();
          return;
        }
        let events: readonly ChatGenerationEvent[] | null;
        try {
          events = input.events.listAfter(input.accountId, input.generationId, cursor);
        } catch {
          close();
          return;
        }
        if (events === null) {
          close();
          return;
        }
        if (emit(events)) return;
        timer = setTimeout(poll, 5);
      };
      poll();
    },
    cancel(): void {
      stopped = true;
      if (timer !== null) clearTimeout(timer);
    },
  });
  return new Response(body, {
    status: 200,
    headers: {
      "cache-control": "no-store",
      "content-type": "text/event-stream",
      "x-accel-buffering": "no",
    },
  });
};

const currentSnapshot = (
  generationId: string,
  events: readonly ChatGenerationEvent[],
): ChatGenerationEvent | null => {
  const advisory = events.filter((event) =>
    event.frame.kind === "snapshot" || event.frame.kind === "delta");
  const latest = advisory.at(-1);
  if (latest === undefined) return null;
  let text = "";
  for (const event of advisory) {
    if (event.frame.kind === "snapshot") text = event.frame.text;
    if (event.frame.kind === "delta") text += event.frame.text;
  }
  return Object.freeze({
    id: latest.id,
    generationId,
    sequence: latest.sequence,
    createdAt: latest.createdAt,
    frame: { kind: "snapshot", text },
  });
};

export const registerChatMessagesRoutes = (
  app: Hono,
  deps: ChatMessagesRouteDependencies,
): void => {
  app.get(CHAT_MESSAGES_PATH, (context) => {
    const principal = bearerPrincipal(
      context.req.header("authorization"),
      deps.resolvePrincipal,
    );
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return unauthorized();
    }
    recordContractVersion(context.req.header(APP_CONTRACT_VERSION_HEADER));
    const query = parseHistoryQuery(context.req.raw);
    if (query === null) {
      deps.counter.recordDomainRead("denied");
      return badRequest();
    }
    try {
      const accountEpoch = deps.control.read(principal.uid)?.account_epoch ?? null;
      const cursor = query.olderCursor === null ? null : deps.cursor.verify(query.olderCursor, {
        accountId: principal.uid,
        accountEpoch,
        nowEpochSeconds: deps.nowEpochSeconds(),
      });
      const snapshotSequence = cursor?.snapshotSequence
        ?? deps.messages.readSnapshotSequence(principal.uid);
      const page = deps.messages.listHistory(principal.uid, {
        limit: query.limit,
        snapshotSequence,
        olderThan: cursor?.olderThan ?? null,
      });
      const nowEpochMilliseconds = deps.nowEpochMilliseconds();
      const messages = Object.freeze(page.messages.map((message): ChatWireMessage => {
        const projected = projectHistoryMessage(
          principal.uid,
          message,
          deps.messages,
          deps.events,
        );
        return Object.freeze({
          ...projected,
          attachments: deps.attachments.projectMessageAttachments({
            accountId: principal.uid,
            messageId: message.id,
            attachments: message.attachments ?? Object.freeze([]),
            nowEpochMilliseconds,
          }),
        });
      }));
      const oldest = messages[0];
      const cursorIssuedAt = cursor?.issuedAtEpochSeconds ?? deps.nowEpochSeconds();
      const olderCursor = page.hasOlder && oldest !== undefined
        ? deps.cursor.issue({
            accountId: principal.uid,
            accountEpoch,
            snapshotSequence,
            olderThan: { createdAt: oldest.createdAt, id: oldest.id },
            issuedAtEpochSeconds: cursorIssuedAt,
            ttlSeconds: deps.cursorTtlSeconds,
          })
        : null;
      deps.counter.recordDomainRead("served");
      return response({
        messages,
        page: { olderCursor, hasOlder: page.hasOlder },
        capabilities: CHAT_CAPABILITIES,
      }, 200);
    } catch (error) {
      if (error instanceof ExpiredChatHistoryCursorError) {
        deps.counter.recordDomainRead("denied");
        return response(errorBody("cursor_expired", "refresh_history"), 410);
      }
      if (error instanceof InvalidChatHistoryCursorError) {
        deps.counter.recordDomainRead("denied");
        return response(errorBody("bad_request", "refresh_history"), 400);
      }
      deps.counter.recordDomainRead("failed");
      return unavailable();
    }
  });

  app.post(CHAT_MESSAGES_PATH, async (context) => {
    const authentication = bearerAuthentication(
      context.req.header("authorization"),
      deps.resolvePrincipal,
    );
    if (authentication === null) return unauthorized();
    const { principal } = authentication;
    recordContractVersion(context.req.header(APP_CONTRACT_VERSION_HEADER));
    let value: unknown;
    try {
      value = JSON.parse(await context.req.text()) as unknown;
    } catch {
      return badRequest();
    }
    const create = parseCreate(value);
    if (create === null) return validation();
    if (create.attachmentIds.length > CHAT_CAPABILITIES.maxAttachmentsPerMessage) {
      return validation();
    }
    if (new Set(create.attachmentIds).size !== create.attachmentIds.length) return validation();
    try {
      const payloadHash = chatMessagePayloadHash(create);
      const generationId = deps.generationId(principal.uid, create.id);
      const admittedAt = deps.nowEpochMilliseconds();
      const resolvedAttachments = deps.attachments.resolveForAdmission({
        accountId: principal.uid,
        scope: MAIN_CHAT_ATTACHMENT_SCOPE,
        attachmentIds: create.attachmentIds,
        messageId: create.id,
        nowEpochMilliseconds: admittedAt,
      });
      if (resolvedAttachments.kind === "not_found") return attachmentNotFound();
      if (resolvedAttachments.attachments.some((attachment) =>
        !isAllowedChatAttachmentMimeType(attachment.mediaType)
        || attachment.sizeBytes <= 0
        || attachment.sizeBytes > CHAT_MAX_ATTACHMENT_BYTES)) return validation();
      const record: ChatMessageRecord = Object.freeze({
        id: create.id,
        text: create.text,
        sender: "human",
        type: create.type,
        createdAt: create.at,
        updatedAt: create.at,
        chatSessionId: null,
        appId: null,
        journalRevision: create.journalRevision,
        payloadHash,
        messageSource: create.messageSource,
        rating: null,
        reported: false,
        revision: deps.revision(
          principal.uid,
          create.id,
          create.journalRevision,
          payloadHash,
        ),
        attachments: resolvedAttachments.attachments,
      });
      const admission = deps.admission.admit({
        accountId: principal.uid,
        message: record,
        generationId,
        acceptedEventId: deps.acceptedEventId(principal.uid, generationId),
        admittedAt,
        attachmentIds: create.attachmentIds,
      });
      if (admission.kind === "conflict") return conflict();
      if (admission.kind === "entitlement") return entitlement();
      if (admission.kind === "attachment_not_found") return attachmentNotFound();
      const admittedGenerationId = admission.stored.generationId ?? generationId;
      const acceptedEvent = admission.kind === "created"
        ? admission.acceptedEvent
        : deps.events.listAfter(principal.uid, admittedGenerationId, null)
          ?.find((event) => event.frame.kind === "accepted");
      if (acceptedEvent === undefined) {
        throw new TypeError("admitted chat generation has no accepted event");
      }
      if (admission.kind === "created") deps.recordAcceptedAdmission();
      // The accepted event is the durable dispatch record. Every replay offers
      // it back to the idempotent supervisor so a synchronous dispatch failure
      // is recoverable without waiting for a process restart.
      deps.supervisor.onAdmitted({
        accountId: principal.uid,
        stored: admission.stored,
        acceptedEvent,
      });
      const projectedMessage = Object.freeze({
        ...admission.stored.message,
        generationOutcome: null,
        attachments: deps.attachments.projectMessageAttachments({
          accountId: principal.uid,
          messageId: admission.stored.message.id,
          attachments: admission.stored.message.attachments ?? Object.freeze([]),
          nowEpochMilliseconds: admittedAt,
        }),
      });
      return response({
        message: projectedMessage,
        generation: { id: admittedGenerationId },
      }, admission.kind === "created" ? 201 : 200);
    } catch {
      return unavailable();
    }
  });

  app.get(`${CHAT_GENERATIONS_PATH}/:generationId/events`, (context) => {
    const authentication = bearerAuthentication(
      context.req.header("authorization"),
      deps.resolvePrincipal,
    );
    if (authentication === null) return unauthorized();
    const { principal } = authentication;
    const revalidate = (): boolean =>
      deps.resolvePrincipal(authentication.token)?.uid === principal.uid;
    recordContractVersion(context.req.header(APP_CONTRACT_VERSION_HEADER));
    const generationId = context.req.param("generationId");
    const lifecycle = deps.events.readLifecycle(principal.uid, generationId);
    if (lifecycle === null) return generationNotFound();
    const all = deps.events.listAfter(principal.uid, generationId, null);
    if (all === null) return generationNotFound();
    const lastEventId = context.req.header("last-event-id") ?? null;
    if (lastEventId === "") return badRequest();

    if (lastEventId !== null) {
      if (all.some((event) => event.id === lastEventId && !isExternalGenerationEvent(event))) {
        return generationReplayExpired();
      }
      const replay = deps.events.listAfter(principal.uid, generationId, lastEventId);
      if (replay === null) {
        const terminal = all.findLast(isTerminal);
        if (terminal === undefined) return generationReplayExpired();
        return streamEvents({
          accountId: principal.uid,
          generationId,
          events: deps.events,
          initial: [terminal],
          afterEventId: terminal.id,
          signal: context.req.raw.signal,
          revalidate,
        });
      }
      if (replay.length === 0 && lifecycle.state === "terminal") {
        const terminal = all.findLast(isTerminal);
        if (terminal === undefined) return generationReplayExpired();
        return streamEvents({
          accountId: principal.uid,
          generationId,
          events: deps.events,
          initial: [terminal],
          afterEventId: terminal.id,
          signal: context.req.raw.signal,
          revalidate,
        });
      }
      const replayTerminal = replay.findLast(isTerminal);
      if (replayTerminal !== undefined) {
        return streamEvents({
          accountId: principal.uid,
          generationId,
          events: deps.events,
          initial: [replayTerminal],
          afterEventId: replayTerminal.id,
          signal: context.req.raw.signal,
          revalidate,
        });
      }
      const snapshot = currentSnapshot(generationId, all);
      if (snapshot === null) return generationReplayExpired();
      return streamEvents({
        accountId: principal.uid,
        generationId,
        events: deps.events,
        initial: [snapshot],
        afterEventId: snapshot.id,
        signal: context.req.raw.signal,
        revalidate,
      });
    }

    const terminal = all.findLast(isTerminal);
    if (terminal !== undefined) {
      return streamEvents({
        accountId: principal.uid,
        generationId,
        events: deps.events,
        initial: [terminal],
        afterEventId: terminal.id,
        signal: context.req.raw.signal,
        revalidate,
      });
    }
    const snapshot = currentSnapshot(generationId, all);
    if (snapshot === null) return generationReplayExpired();
    return streamEvents({
      accountId: principal.uid,
      generationId,
      events: deps.events,
      initial: [snapshot],
      afterEventId: snapshot.id,
      signal: context.req.raw.signal,
      revalidate,
    });
  });

  app.delete(`${CHAT_GENERATIONS_PATH}/:generationId`, (context) => {
    const principal = bearerPrincipal(
      context.req.header("authorization"),
      deps.resolvePrincipal,
    );
    if (principal === null) return unauthorized();
    recordContractVersion(context.req.header(APP_CONTRACT_VERSION_HEADER));
    const generationId = context.req.param("generationId");
    const outcome = deps.events.requestCancellation(principal.uid, generationId);
    if (outcome.kind === "not_found") return generationNotFound();
    if (outcome.kind === "already_terminal") return new Response(null, {
      status: 204,
      headers: { "cache-control": "no-store" },
    });
    if (outcome.kind === "accepted") deps.supervisor.cancel(principal.uid, generationId);
    return response({ cancellation: { state: "accepted" } }, 202);
  });
};
