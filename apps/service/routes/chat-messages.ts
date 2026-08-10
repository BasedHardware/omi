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
import type { ChatGenerationSupervisor } from "../chat/generation-supervisor";
import {
  ExpiredChatHistoryCursorError,
  InvalidChatHistoryCursorError,
  type ChatHistoryCursorCodec,
} from "../chat/history-cursor";
import type { ServedCounter } from "../observability/served-count";
import type { ChatAdmission } from "../stores/chat-admission";
import type {
  ChatAttachmentMetadata,
  ChatMessageRecord,
  ChatMessagesStore,
  WritableChatMessageType,
} from "../stores/chat-messages-store";

export const CHAT_MESSAGES_PATH = "/v1/chat-messages";
export const CHAT_CAPABILITIES = Object.freeze({
  maxAttachmentsPerMessage: 0,
  maxAttachmentBytes: 0,
  allowedAttachmentMimeTypes: Object.freeze([] as string[]),
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
  readonly admission: ChatAdmission;
  readonly supervisor: ChatGenerationSupervisor;
  readonly cursor: ChatHistoryCursorCodec;
  readonly counter: ServedCounter;
  readonly nowEpochMilliseconds: () => number;
  readonly nowEpochSeconds: () => number;
  readonly cursorTtlSeconds: number;
  readonly generationId: (accountId: string, messageId: string) => string;
  readonly acceptedEventId: (accountId: string, generationId: string) => string;
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
  readonly attachments?: readonly ChatAttachmentMetadata[];
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

const bearerPrincipal = (
  authorization: string | undefined,
  resolvePrincipal: ChatMessagesRouteDependencies["resolvePrincipal"],
): DevPrincipal | null => {
  if (authorization === undefined || !authorization.startsWith("Bearer ")) return null;
  const token = authorization.slice("Bearer ".length);
  return token.length === 0 ? null : resolvePrincipal(token);
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

const parseAttachments = (value: unknown): readonly ChatAttachmentMetadata[] | null => {
  if (!Array.isArray(value)) return null;
  const parsed: ChatAttachmentMetadata[] = [];
  for (const item of value) {
    if (!exactObject(item, ["displayName", "mediaType", "size"])
      || typeof item.displayName !== "string"
      || typeof item.mediaType !== "string"
      || !Number.isSafeInteger(item.size) || (item.size as number) < 0) return null;
    parsed.push(Object.freeze({
      displayName: item.displayName,
      mediaType: item.mediaType,
      size: item.size as number,
    }));
  }
  return Object.freeze(parsed);
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
      "attachmentIds", "attachments",
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
  const attachments = value.attachments === undefined ? undefined : parseAttachments(value.attachments);
  if (attachments === null) return null;
  return Object.freeze({
    id: value.id,
    at: value.at as number,
    text: value.text,
    journalRevision: value.journalRevision as number,
    type: (value.type ?? "text") as WritableChatMessageType,
    messageSource: (value.messageSource ?? "desktop_chat") as string,
    metadata: (value.metadata ?? null) as string | null,
    attachmentIds,
    ...(attachments === undefined ? {} : { attachments }),
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
  const attachments: Json = create.attachments === undefined
    ? null
    : create.attachments.map((attachment): Json => ({
        displayName: attachment.displayName,
        mediaType: attachment.mediaType,
        size: attachment.size,
      }));
  const subject: { readonly [key: string]: Json } = {
    at: create.at,
    attachmentIds: create.attachmentIds,
    attachments,
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
      const cursor = query.olderCursor === null ? null : deps.cursor.verify(query.olderCursor, {
        accountId: principal.uid,
        nowEpochSeconds: deps.nowEpochSeconds(),
      });
      const snapshotSequence = cursor?.snapshotSequence
        ?? deps.messages.readSnapshotSequence(principal.uid);
      const page = deps.messages.listHistory(principal.uid, {
        limit: query.limit,
        snapshotSequence,
        olderThan: cursor?.olderThan ?? null,
      });
      const oldest = page.messages[0];
      const cursorIssuedAt = cursor?.issuedAtEpochSeconds ?? deps.nowEpochSeconds();
      const olderCursor = page.hasOlder && oldest !== undefined
        ? deps.cursor.issue({
            accountId: principal.uid,
            snapshotSequence,
            olderThan: { createdAt: oldest.createdAt, id: oldest.id },
            issuedAtEpochSeconds: cursorIssuedAt,
            ttlSeconds: deps.cursorTtlSeconds,
          })
        : null;
      deps.counter.recordDomainRead("served");
      return response({
        messages: page.messages,
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
    const principal = bearerPrincipal(
      context.req.header("authorization"),
      deps.resolvePrincipal,
    );
    if (principal === null) return unauthorized();
    recordContractVersion(context.req.header(APP_CONTRACT_VERSION_HEADER));
    let value: unknown;
    try {
      value = JSON.parse(await context.req.text()) as unknown;
    } catch {
      return badRequest();
    }
    const create = parseCreate(value);
    if (create === null) return validation();
    try {
      const payloadHash = chatMessagePayloadHash(create);
      const generationId = deps.generationId(principal.uid, create.id);
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
        ...(create.attachments === undefined ? {} : { attachments: create.attachments }),
      });
      const admission = deps.admission.admit({
        accountId: principal.uid,
        message: record,
        generationId,
        acceptedEventId: deps.acceptedEventId(principal.uid, generationId),
        admittedAt: deps.nowEpochMilliseconds(),
      });
      if (admission.kind === "conflict") return conflict();
      if (admission.kind === "entitlement") return entitlement();
      if (admission.kind === "created") {
        deps.supervisor.onAdmitted({
          accountId: principal.uid,
          stored: admission.stored,
          acceptedEvent: admission.acceptedEvent,
        });
      }
      return response({
        kind: "accepted",
        message: admission.stored.message,
        generation: { id: admission.stored.generationId ?? generationId },
      }, admission.kind === "created" ? 201 : 200);
    } catch {
      return unavailable();
    }
  });
};
