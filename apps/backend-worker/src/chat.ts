import { chatMessagePayloadHash } from "@omi-core/kernel";
import { parseRecordId } from "@omi-core/contracts";
import type { ChatCompletedAssistantMessage } from "@omi-core/contracts";

import {
  bindAttachmentStatement,
  listBoundAttachments,
  resolveAttachmentsForAdmit,
} from "./attachments";
import {
  isVisibleGenerationText,
  recoveredPayloadTextKeySql,
} from "./generation-prompt";
import {
  CHAT_CAPABILITIES,
  parseChatCreate,
  type ChatCreate,
  type ChatMessage,
  type GenerationEvent,
} from "./wire";

type StoredMessage = {
  id: string;
  text: string;
  sender: string;
  createdAt: number;
  generationOutcome: "completed" | "cancelled" | null;
  position: number;
  payload: string | null;
};

export type Admission = {
  message: ChatMessage;
  generation: { id: string };
  created: boolean;
};

export type HistoryResult =
  | {
      messages: ChatMessage[];
      page:
        | { olderCursor: string; hasOlder: true }
        | { olderCursor: null; hasOlder: false };
      capabilities: typeof CHAT_CAPABILITIES;
    }
  | "invalid_cursor"
  | "cursor_expired"
  | "unavailable";

export type SettingsIdentity = {
  displayName: string;
  email: string;
};

export type SettingsEntitlement = {
  planLabel: string;
  limitKey: string;
  used: number;
  limit: number | null;
  limitReached: boolean;
  upgradeAvailable: boolean;
};

export type SettingsSnapshot = {
  identity: SettingsIdentity;
  entitlement: SettingsEntitlement | null;
};

export type PendingGeneration = {
  generationId: string;
  input: ChatCreate | "unreadable";
};

export async function admitMessage(
  db: D1Database,
  accountId: string,
  input: ChatCreate,
  chatLimit: number | null
): Promise<
  | Admission
  | "conflict"
  | "entitlement"
  | "attachment_rejected"
  | "attachment_not_found"
  | "attachment_invalid"
> {
  const payloadHash = computePayloadHash(input);
  const prior = await db
    .prepare(
      "SELECT payload, generation_id AS generationId FROM chat_admissions WHERE message_id = ? AND account_id = ?"
    )
    .bind(input.id, accountId)
    .first<{ payload: string; generationId: string }>();

  if (prior !== null) {
    let previous: unknown;
    try {
      previous = JSON.parse(prior.payload);
    } catch {
      return "conflict";
    }
    const previousCreate = parseChatCreate(previous);
    if (
      previousCreate === null ||
      computePayloadHash(previousCreate) !== payloadHash
    )
      return "conflict";
    let message = await readMessage(db, accountId, input.id);
    if (message === null) return "conflict";
    const detached = projectStoredChatMessage(message);
    if (detached === null) {
      throw new TypeError("invalid chat message record");
    }
    message = overlayCreateFields(detached, input);
    if (input.journalRevision > message.journalRevision) {
      message = {
        ...message,
        updatedAt: Math.max(message.updatedAt, input.at),
        journalRevision: input.journalRevision,
        revision: String(input.journalRevision),
      };
      await db
        .prepare(
          "UPDATE chat_messages SET payload = ? WHERE id = ? AND account_id = ?"
        )
        .bind(JSON.stringify(message), input.id, accountId)
        .run();
    }
    return {
      message,
      generation: { id: prior.generationId },
      created: false,
    };
  }

  const resolved = await resolveAttachmentsForAdmit(
    db,
    accountId,
    input.attachmentIds,
    input.id
  );
  if (resolved.kind === "not_found") return "attachment_not_found";
  if (resolved.kind === "invalid") return "attachment_invalid";
  if (resolved.kind === "rejected") return "attachment_rejected";

  const usedRow = await db
    .prepare(
      "SELECT COUNT(*) AS count FROM chat_admissions WHERE account_id = ?"
    )
    .bind(accountId)
    .first<{ count: number }>();
  const used = usedRow?.count ?? 0;
  if (chatLimit !== null && used >= chatLimit) {
    return "entitlement";
  }

  const generationId = crypto.randomUUID();
  const position = await nextPosition(db, accountId);
  const message = humanMessage(
    input,
    payloadHash,
    position,
    resolved.attachments
  );
  const boundAt = Date.now();

  await db.batch([
    db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, ?, ?)"
      )
      .bind(
        message.id,
        accountId,
        message.text,
        message.createdAt,
        position,
        JSON.stringify(message)
      ),
    db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        input.id,
        accountId,
        input.opId,
        JSON.stringify(input),
        generationId
      ),
    db
      .prepare(
        "INSERT OR IGNORE INTO chat_generation_events (generation_id, account_id, event_id, ordinal, payload) VALUES (?, ?, '1', 1, ?)"
      )
      .bind(
        generationId,
        accountId,
        JSON.stringify({ id: "1", kind: "snapshot", text: "" })
      ),
    ...resolved.attachments.map((attachment) =>
      bindAttachmentStatement(db, accountId, input.id, attachment.id, boundAt)
    ),
  ]);

  return {
    message,
    generation: { id: generationId },
    created: true,
  };
}

export async function readHistory(
  db: D1Database,
  accountId: string,
  limit: number,
  olderCursor?: string,
  chatSessionId?: string
): Promise<HistoryResult> {
  const sessionFilter = chatSessionId ?? null;
  let boundary: { createdAt: number; id: string } | null = null;
  let expiresAt = Math.floor(Date.now() / 1000) + CHAT_CURSOR_TTL_SECONDS;
  if (olderCursor !== undefined) {
    const decoded = decodeCursor(olderCursor, sessionFilter);
    if (decoded.status === "invalid") return "invalid_cursor";
    if (decoded.status === "expired") return "cursor_expired";
    boundary = { createdAt: decoded.createdAt, id: decoded.id };
    expiresAt = decoded.expiresAt;
  }

  const result = await db
    .prepare(
      `SELECT id, text, sender, created_at AS createdAt, generation_outcome AS generationOutcome, position, payload
       FROM (
         SELECT id, text, sender, created_at, generation_outcome, position, payload,
           ${recoveredPayloadTextKeySql(
             "chat_messages",
             "chatSessionId"
           )} AS session_key
         FROM chat_messages WHERE account_id = ?
           AND ${recoveredPayloadTextKeySql("chat_messages", "appId")} IS NULL
       ) AS normalized
       WHERE (? IS NULL OR created_at < ? OR (created_at = ? AND id < ?))
         AND CASE WHEN ? IS NULL
           THEN NOT (typeof(session_key) = 'text' AND length(CAST(session_key AS BLOB)) > 0)
           ELSE typeof(session_key) = 'text' AND length(CAST(session_key AS BLOB)) > 0 AND session_key = ?
         END
       ORDER BY created_at DESC, id DESC
       LIMIT ?`
    )
    .bind(
      accountId,
      boundary?.createdAt ?? null,
      boundary?.createdAt ?? 0,
      boundary?.createdAt ?? 0,
      boundary?.id ?? "",
      sessionFilter,
      sessionFilter,
      limit + 1
    )
    .all<StoredMessage>();

  const rows = result.results;
  const hasOlder = rows.length > limit;
  const pageRows = rows.slice(0, limit).reverse();
  const oldest = pageRows[0];
  const messages: ChatMessage[] = [];
  for (const row of pageRows) {
    const message = await projectHistoryMessage(db, accountId, row);
    if (message === null) return "unavailable";
    messages.push(message);
  }
  return {
    messages,
    page:
      hasOlder && oldest !== undefined
        ? {
            olderCursor: encodeCursor(
              oldest.createdAt,
              oldest.id,
              sessionFilter,
              expiresAt
            ),
            hasOlder: true,
          }
        : { olderCursor: null, hasOlder: false },
    capabilities: CHAT_CAPABILITIES,
  };
}

export async function readSettings(
  db: D1Database,
  accountId: string,
  chatLimit: number | null
): Promise<SettingsSnapshot> {
  const usedRow = await db
    .prepare(
      "SELECT COUNT(*) AS count FROM chat_admissions WHERE account_id = ?"
    )
    .bind(accountId)
    .first<{ count: number }>();
  const used = usedRow?.count ?? 0;
  return {
    identity: { displayName: "", email: "" },
    entitlement: {
      planLabel: "",
      limitKey: "chat",
      used,
      limit: chatLimit,
      limitReached: chatLimit !== null && used >= chatLimit,
      upgradeAvailable: false,
    },
  };
}

export async function cancelGeneration(
  db: D1Database,
  accountId: string,
  generationId: string
): Promise<"not_found" | "terminal" | GenerationEvent> {
  const hasGen = await hasGeneration(db, accountId, generationId);
  if (!hasGen) return "not_found";
  const terminal = await terminalEvent(db, accountId, generationId);
  if (terminal === "unreadable" || terminal !== null) return "terminal";
  const event: GenerationEvent = {
    id: "2",
    kind: "cancelled",
    message: null,
  };
  await appendGenerationEvent(db, accountId, generationId, event);
  return event;
}

export async function countPendingGenerations(
  db: D1Database,
  accountId: string
): Promise<number> {
  const row = await db
    .prepare(
      `SELECT COUNT(*) AS count
       FROM chat_admissions
       WHERE account_id = ?
         AND NOT EXISTS (
           SELECT 1 FROM chat_generation_events
           WHERE chat_generation_events.generation_id = chat_admissions.generation_id
             AND chat_generation_events.ordinal = 2
         )`
    )
    .bind(accountId)
    .first<{ count: number }>();
  return row?.count ?? 0;
}

export async function readPendingGeneration(
  db: D1Database,
  accountId: string
): Promise<PendingGeneration | null> {
  const row = await db
    .prepare(
      `SELECT chat_admissions.generation_id AS generationId, chat_admissions.payload
       FROM chat_admissions
       WHERE chat_admissions.account_id = ?
         AND NOT EXISTS (
           SELECT 1 FROM chat_generation_events
           WHERE chat_generation_events.generation_id = chat_admissions.generation_id
             AND chat_generation_events.ordinal = 2
         )
       ORDER BY chat_admissions.rowid
       LIMIT 1`
    )
    .bind(accountId)
    .first<{ generationId: string; payload: string }>();
  if (row === null) return null;
  try {
    const parsed: unknown = JSON.parse(row.payload);
    const input = parseChatCreate(parsed);
    if (input !== null) {
      return { generationId: row.generationId, input };
    }
  } catch {}
  return { generationId: row.generationId, input: "unreadable" };
}

export async function completeGeneration(
  db: D1Database,
  accountId: string,
  generationId: string,
  text: string
): Promise<GenerationEvent> {
  const admission = await db
    .prepare(
      "SELECT message_id AS messageId FROM chat_admissions WHERE generation_id = ? AND account_id = ?"
    )
    .bind(generationId, accountId)
    .first<{ messageId: string }>();
  if (admission === null) throw new Error("admission not found for generation");

  const human = await readMessage(db, accountId, admission.messageId);
  if (human === null) return failGeneration(db, accountId, generationId);
  const detached = projectStoredChatMessage(human);
  if (detached === null) {
    throw new TypeError("invalid chat message record");
  }
  if (!isVisibleGenerationText(text)) {
    return failGeneration(db, accountId, generationId);
  }

  const createdAt = Date.now();
  const message: ChatCompletedAssistantMessage = {
    id: recordId(generationId),
    text,
    sender: "ai",
    type: "text",
    createdAt,
    updatedAt: createdAt,
    chatSessionId: detached.chatSessionId,
    appId: detached.appId,
    journalRevision: detached.journalRevision,
    payloadHash: chatMessagePayloadHash({
      text,
      sender: "ai",
      appId: detached.appId,
      sessionId: detached.chatSessionId,
      metadata: null,
      messageSource: "assistant_generation",
      attachmentIds: [],
    }),
    messageSource: "assistant_generation",
    rating: null,
    reported: false,
    generationOutcome: "completed",
    revision: null,
    attachments: [],
  };

  const position = await nextPosition(db, accountId);
  const stored = { ...message, revision: String(position) };

  await db.batch([
    db
      .prepare(
        "INSERT OR IGNORE INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'ai', ?, 'completed', ?, ?)"
      )
      .bind(
        stored.id,
        accountId,
        stored.text,
        stored.createdAt,
        position,
        JSON.stringify(stored)
      ),
    db
      .prepare(
        "INSERT OR IGNORE INTO chat_generation_events (generation_id, account_id, event_id, ordinal, payload) VALUES (?, ?, '2', 2, ?)"
      )
      .bind(
        generationId,
        accountId,
        JSON.stringify({ id: "2", kind: "done", message })
      ),
  ]);

  return { id: "2", kind: "done", message };
}

export async function failGeneration(
  db: D1Database,
  accountId: string,
  generationId: string,
  retryable = true
): Promise<GenerationEvent> {
  const event: GenerationEvent = {
    id: "2",
    kind: "failed",
    error: { code: "generation_failed", retryable },
  };
  await appendGenerationEvent(db, accountId, generationId, event);
  return event;
}

export async function readGenerationEvents(
  db: D1Database,
  accountId: string,
  generationId: string
): Promise<GenerationEvent[] | "unreadable"> {
  const result = await db
    .prepare(
      "SELECT payload FROM chat_generation_events WHERE generation_id = ? AND account_id = ? ORDER BY ordinal"
    )
    .bind(generationId, accountId)
    .all<{ payload: string }>();

  const events: GenerationEvent[] = [];
  for (const row of result.results) {
    const event = parseEvent(row.payload);
    if (event === null) return "unreadable";
    if (event.kind === "done") {
      const message = generationMessageSync(event);
      if (message === null) return "unreadable";
      events.push({ ...event, message });
    } else {
      events.push(event);
    }
  }
  return events;
}

export async function hasGeneration(
  db: D1Database,
  accountId: string,
  generationId: string
): Promise<boolean> {
  const row = await db
    .prepare(
      "SELECT COUNT(*) AS count FROM chat_admissions WHERE generation_id = ? AND account_id = ?"
    )
    .bind(generationId, accountId)
    .first<{ count: number }>();
  return (row?.count ?? 0) > 0;
}

export async function terminalEvent(
  db: D1Database,
  accountId: string,
  generationId: string
): Promise<GenerationEvent | null | "unreadable"> {
  const events = await readGenerationEvents(db, accountId, generationId);
  if (events === "unreadable") return "unreadable";
  return events.find((event) => isTerminal(event)) ?? null;
}

async function appendGenerationEvent(
  db: D1Database,
  accountId: string,
  generationId: string,
  event: GenerationEvent
): Promise<void> {
  await db
    .prepare(
      "INSERT OR IGNORE INTO chat_generation_events (generation_id, account_id, event_id, ordinal, payload) VALUES (?, ?, ?, ?, ?)"
    )
    .bind(
      generationId,
      accountId,
      event.id,
      Number(event.id),
      JSON.stringify(event)
    )
    .run();
}

async function readMessage(
  db: D1Database,
  accountId: string,
  id: string
): Promise<ChatMessage | null> {
  const row = await db
    .prepare(
      "SELECT id, text, sender, created_at AS createdAt, generation_outcome AS generationOutcome, position, payload FROM chat_messages WHERE id = ? AND account_id = ?"
    )
    .bind(id, accountId)
    .first<StoredMessage>();
  if (row === null) return null;
  const parsed = parseStoredMessage(row);
  if (parsed === null) return null;
  return parsed.fromColumns
    ? hydrateColumnMessage(db, accountId, parsed.message)
    : parsed.message;
}

async function nextPosition(
  db: D1Database,
  accountId: string
): Promise<number> {
  const row = await db
    .prepare(
      "SELECT COALESCE(MAX(position), 0) + 1 AS position FROM chat_messages WHERE account_id = ?"
    )
    .bind(accountId)
    .first<{ position: number }>();
  return row?.position ?? 1;
}

function humanMessage(
  input: ChatCreate,
  payloadHash: string,
  position: number,
  attachments: ChatMessage["attachments"]
): ChatMessage {
  return {
    id: input.id as ChatMessage["id"],
    text: input.text,
    sender: "human",
    type: input.type ?? "text",
    createdAt: input.at,
    updatedAt: input.at,
    chatSessionId: input.chatSessionId ?? null,
    appId: input.appId ?? null,
    journalRevision: input.journalRevision,
    payloadHash,
    messageSource: input.messageSource ?? "desktop_chat",
    rating: null,
    reported: false,
    generationOutcome: null,
    revision: String(position),
    attachments,
  };
}

function computePayloadHash(input: ChatCreate): string {
  return chatMessagePayloadHash({
    text: input.text,
    sender: input.sender,
    appId: input.appId ?? null,
    sessionId: input.chatSessionId ?? null,
    metadata: input.metadata ?? null,
    messageSource: input.messageSource ?? "desktop_chat",
    attachmentIds: input.attachmentIds ?? [],
  });
}

const isNonNegativeSafeInteger = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

function projectStoredChatAttachments(
  attachments: unknown
): ChatMessage["attachments"] | null {
  if (attachments === undefined) return [];
  if (!Array.isArray(attachments)) return null;
  for (const attachment of attachments) {
    if (
      attachment === null ||
      typeof attachment !== "object" ||
      typeof attachment.displayName !== "string" ||
      typeof attachment.mediaType !== "string" ||
      typeof attachment.id !== "string" ||
      attachment.id.length === 0 ||
      !isNonNegativeSafeInteger(attachment.sizeBytes) ||
      !(
        attachment.contentReference === null ||
        (typeof attachment.contentReference === "string" &&
          attachment.contentReference.length > 0)
      )
    ) {
      return null;
    }
  }
  return attachments as ChatMessage["attachments"];
}

function projectStoredChatMessage(message: ChatMessage): ChatMessage | null {
  if (
    typeof message.id !== "string" ||
    message.id.length === 0 ||
    typeof message.text !== "string" ||
    typeof message.sender !== "string" ||
    message.sender.length === 0 ||
    typeof message.type !== "string" ||
    message.type.length === 0 ||
    !isNonNegativeSafeInteger(message.createdAt) ||
    !isNonNegativeSafeInteger(message.updatedAt) ||
    !(
      message.chatSessionId === null ||
      typeof message.chatSessionId === "string"
    ) ||
    !(message.appId === null || typeof message.appId === "string") ||
    !isNonNegativeSafeInteger(message.journalRevision) ||
    typeof message.payloadHash !== "string" ||
    typeof message.messageSource !== "string" ||
    !(
      message.rating === null ||
      (typeof message.rating === "number" && Number.isFinite(message.rating))
    ) ||
    typeof message.reported !== "boolean" ||
    !(message.revision === null || typeof message.revision === "string")
  ) {
    return null;
  }
  const attachments = projectStoredChatAttachments(message.attachments);
  if (attachments === null) return null;
  return attachments === message.attachments
    ? message
    : { ...message, attachments };
}

async function projectHistoryMessage(
  db: D1Database,
  accountId: string,
  row: StoredMessage
): Promise<ChatMessage | null> {
  const parsed = parseStoredMessage(row);
  if (parsed === null) return null;
  const message = parsed.fromColumns
    ? await hydrateColumnMessage(db, accountId, parsed.message)
    : parsed.message;
  if (message.sender === "ai") {
    const events = await readGenerationEvents(db, accountId, row.id);
    if (events === "unreadable") return null;
    const outcome = historyOutcomeFromTerminal(events, message);
    return outcome === null
      ? null
      : projectStoredChatMessage({ ...message, generationOutcome: outcome });
  }
  if (message.sender === "human") {
    return projectStoredChatMessage({
      ...message,
      sender: "human",
      generationOutcome: null,
    });
  }
  return projectStoredChatMessage({ ...message, sender: "unknown" });
}

function overlayCreateFields(
  message: ChatMessage,
  input: ChatCreate
): ChatMessage {
  return {
    ...message,
    chatSessionId: input.chatSessionId ?? null,
    appId: input.appId ?? null,
    messageSource: input.messageSource ?? message.messageSource,
    payloadHash: computePayloadHash(input),
  };
}

function overlayAdmissionPayload(
  message: ChatMessage,
  payload: string
): ChatMessage {
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    return message;
  }
  const create = parseChatCreate(parsed);
  if (create !== null) {
    if (message.sender === "human") {
      return overlayCreateFields(message, create);
    }
    return {
      ...message,
      chatSessionId: create.chatSessionId ?? null,
      appId: create.appId ?? null,
    };
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return message;
  }
  const session = (parsed as Record<string, unknown>)["chatSessionId"];
  if (
    typeof session !== "string" ||
    session.length === 0 ||
    session.length > 128
  ) {
    return message;
  }
  return { ...message, chatSessionId: session };
}

async function withAdmissionCreateFields(
  db: D1Database,
  accountId: string,
  message: ChatMessage
): Promise<ChatMessage> {
  const row = await db
    .prepare(
      "SELECT payload FROM chat_admissions WHERE account_id = ? AND (message_id = ? OR generation_id = ?) LIMIT 1"
    )
    .bind(accountId, message.id, message.id)
    .first<{ payload: string }>();
  if (row === null) return message;
  return overlayAdmissionPayload(message, row.payload);
}

async function hydrateColumnMessage(
  db: D1Database,
  accountId: string,
  message: ChatMessage
): Promise<ChatMessage> {
  return withBoundHistoryAttachments(
    db,
    accountId,
    await withAdmissionCreateFields(db, accountId, message)
  );
}

async function withBoundHistoryAttachments(
  db: D1Database,
  accountId: string,
  message: ChatMessage
): Promise<ChatMessage> {
  const bound = await listBoundAttachments(db, accountId, message.id);
  return {
    ...message,
    attachments: bound.map((attachment) => ({
      id: attachment.id,
      displayName: attachment.displayName,
      mediaType: attachment.mediaType,
      sizeBytes: attachment.sizeBytes,
      contentReference: attachment.id,
    })),
  };
}

const TERMINAL_CANONICAL_KEYS = [
  "type",
  "createdAt",
  "updatedAt",
  "chatSessionId",
  "appId",
  "journalRevision",
  "payloadHash",
  "messageSource",
  "rating",
  "reported",
] as const satisfies readonly (keyof ChatMessage)[];

function presentCanonicalFieldDisagrees(
  terminal: ChatMessage,
  message: ChatMessage,
  key: (typeof TERMINAL_CANONICAL_KEYS)[number]
): boolean {
  return Object.hasOwn(terminal, key) && terminal[key] !== message[key];
}

function historyOutcomeFromTerminal(
  events: GenerationEvent[],
  message: ChatMessage
): "completed" | "cancelled" | null {
  const terminals = events.filter((event) => isTerminal(event));
  if (terminals.length !== 1) return null;
  const terminal = terminals[0]!;
  if (terminal.kind !== "done" && terminal.kind !== "cancelled") return null;
  const terminalMessage = terminal.message;
  if (terminalMessage === null || terminalMessage === undefined) return null;
  if (
    terminalMessage.id !== message.id ||
    terminalMessage.text !== message.text ||
    terminalMessage.sender !== "ai" ||
    TERMINAL_CANONICAL_KEYS.some((key) =>
      presentCanonicalFieldDisagrees(terminalMessage, message, key)
    )
  ) {
    return null;
  }
  return terminal.kind === "done" ? "completed" : "cancelled";
}

function parseStoredMessage(
  row: StoredMessage
): { message: ChatMessage; fromColumns: boolean } | null {
  if (row.payload !== null) {
    try {
      const parsed = JSON.parse(row.payload) as unknown;
      if (
        parsed !== null &&
        typeof parsed === "object" &&
        !Array.isArray(parsed)
      ) {
        const message = parsed as ChatMessage;
        if (
          message.sender !== row.sender ||
          message.id !== row.id ||
          message.text !== row.text
        ) {
          return null;
        }
        return { message, fromColumns: false };
      }
    } catch {}
  }
  const rawId = row.id.startsWith("generation:")
    ? row.id.slice("generation:".length)
    : row.id;
  let id: ChatMessage["id"];
  try {
    id = recordId(rawId);
  } catch {
    if (rawId.length === 0) return null;
    id = rawId as ChatMessage["id"];
  }
  const base = {
    id,
    text: row.text,
    type: "text" as const,
    createdAt: row.createdAt,
    updatedAt: row.createdAt,
    chatSessionId: null,
    appId: null,
    journalRevision: 0,
    payloadHash: chatMessagePayloadHash({
      text: row.text,
      sender: row.sender,
      appId: null,
      sessionId: null,
      metadata: null,
      messageSource:
        row.sender === "human" ? "desktop_chat" : "assistant_generation",
      attachmentIds: [],
    }),
    messageSource:
      row.sender === "human" ? "desktop_chat" : "assistant_generation",
    rating: null,
    reported: false,
    revision: String(row.position),
    attachments: [],
  };
  if (row.sender === "human") {
    return {
      message: { ...base, sender: "human", generationOutcome: null },
      fromColumns: true,
    };
  }
  if (row.sender === "ai") {
    if (
      row.generationOutcome !== "completed" &&
      row.generationOutcome !== "cancelled"
    ) {
      return null;
    }
    return {
      message: {
        ...base,
        sender: "ai",
        generationOutcome: row.generationOutcome,
      },
      fromColumns: true,
    };
  }
  return {
    message: { ...base, sender: "unknown", generationOutcome: null },
    fromColumns: true,
  };
}

function parseEvent(payload: string): GenerationEvent | null {
  try {
    const parsed: unknown = JSON.parse(payload);
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      Array.isArray(parsed)
    ) {
      return null;
    }
    const event = parsed as GenerationEvent | { id: string; kind: string };
    if (typeof event.id !== "string" || typeof event.kind !== "string") {
      return null;
    }
    return event.kind === "accepted"
      ? { id: event.id, kind: "snapshot", text: "" }
      : (event as GenerationEvent);
  } catch {
    return null;
  }
}

function generationMessageSync(
  event: GenerationEvent
): ChatCompletedAssistantMessage | null {
  if (
    event.kind === "done" &&
    event.message !== null &&
    event.message !== undefined
  ) {
    return event.message;
  }
  return null;
}

function recordId(value: string): ChatMessage["id"] {
  const parsed = parseRecordId(value);
  if (parsed === null) throw new Error("stored chat message id is invalid");
  return parsed.id;
}

function isTerminal(event: GenerationEvent): boolean {
  return (
    event.kind === "done" ||
    event.kind === "failed" ||
    event.kind === "cancelled"
  );
}

const CHAT_CURSOR_TTL_SECONDS = 3_600;

function encodeCursor(
  createdAt: number,
  id: string,
  chatSessionId: string | null,
  expiresAt: number
): string {
  const bytes = new TextEncoder().encode(
    JSON.stringify({ e: expiresAt, i: id, s: chatSessionId, t: createdAt })
  );
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

function decodeCursor(
  cursor: string,
  chatSessionId: string | null
):
  | { status: "ok"; createdAt: number; id: string; expiresAt: number }
  | { status: "expired" }
  | { status: "invalid" } {
  if (!/^[A-Za-z0-9_-]{1,1024}$/.test(cursor)) return { status: "invalid" };
  try {
    const standard = cursor.replaceAll("-", "+").replaceAll("_", "/");
    const padded = standard + "=".repeat((4 - (standard.length % 4)) % 4);
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index++) {
      bytes[index] = binary.charCodeAt(index);
    }
    const parsed: unknown = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(bytes)
    );
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      Array.isArray(parsed)
    ) {
      return { status: "invalid" };
    }
    const record = parsed as Record<string, unknown>;
    if (
      Object.keys(record).sort().join(",") !== "e,i,s,t" ||
      typeof record.t !== "number" ||
      !Number.isSafeInteger(record.t) ||
      record.t < 0 ||
      typeof record.i !== "string" ||
      record.i.length < 1 ||
      record.i.length > 256 ||
      !(record.s === null || typeof record.s === "string") ||
      record.s !== chatSessionId ||
      typeof record.e !== "number" ||
      !Number.isSafeInteger(record.e) ||
      record.e < 0
    ) {
      return { status: "invalid" };
    }
    if (
      typeof record.s === "string" &&
      (record.s.length === 0 || record.s.length > 128)
    ) {
      return { status: "invalid" };
    }
    if (Math.floor(Date.now() / 1000) >= record.e) {
      return { status: "expired" };
    }
    return {
      status: "ok",
      createdAt: record.t,
      id: record.i,
      expiresAt: record.e,
    };
  } catch {
    return { status: "invalid" };
  }
}
