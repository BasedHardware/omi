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
  isChatCreate,
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
): Promise<Admission | "conflict" | "entitlement" | "attachment_rejected"> {
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
    if (!isChatCreate(previous) || computePayloadHash(previous) !== payloadHash)
      return "conflict";
    let message = await readMessage(db, accountId, input.id);
    if (message === null) return "conflict";
    message = overlayCreateFields(message, input);
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
  const boundary = olderCursor === undefined ? null : decodeCursor(olderCursor);
  if (olderCursor !== undefined && boundary === null) return "invalid_cursor";
  const sessionFilter = chatSessionId ?? null;

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
       ) AS normalized
       WHERE (? IS NULL OR position < ?)
         AND CASE WHEN ? IS NULL
           THEN NOT (typeof(session_key) = 'text' AND length(CAST(session_key AS BLOB)) > 0)
           ELSE typeof(session_key) = 'text' AND length(CAST(session_key AS BLOB)) > 0 AND session_key = ?
         END
       ORDER BY position DESC
       LIMIT ?`
    )
    .bind(
      accountId,
      boundary,
      boundary,
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
        ? { olderCursor: encodeCursor(oldest.position), hasOlder: true }
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
    if (isChatCreate(parsed)) {
      return { generationId: row.generationId, input: parsed };
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
    chatSessionId: human.chatSessionId,
    appId: human.appId,
    journalRevision: human.journalRevision,
    payloadHash: chatMessagePayloadHash({
      text,
      sender: "ai",
      appId: human.appId,
      sessionId: human.chatSessionId,
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
    id: recordId(input.id),
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
    return outcome === null ? null : { ...message, generationOutcome: outcome };
  }
  if (message.sender === "human") {
    return { ...message, sender: "human", generationOutcome: null };
  }
  return { ...message, sender: "unknown" };
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
  if (isChatCreate(parsed)) {
    if (message.sender === "human") {
      return overlayCreateFields(message, parsed);
    }
    return {
      ...message,
      chatSessionId: parsed.chatSessionId ?? null,
      appId: parsed.appId ?? null,
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

function historyOutcomeFromTerminal(
  events: GenerationEvent[],
  message: ChatMessage
): "completed" | "cancelled" | null {
  const terminals = events.filter((event) => isTerminal(event));
  if (terminals.length !== 1) return null;
  const terminal = terminals[0]!;
  if (terminal.kind !== "done" && terminal.kind !== "cancelled") return null;
  if (terminal.message === null || terminal.message === undefined) return null;
  if (
    terminal.message.id !== message.id ||
    terminal.message.text !== message.text ||
    terminal.message.sender !== "ai"
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
  let id: ChatMessage["id"];
  try {
    id = recordId(
      row.id.startsWith("generation:")
        ? row.id.slice("generation:".length)
        : row.id
    );
  } catch {
    return null;
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

function encodeCursor(position: number): string {
  return btoa(String(position))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

function decodeCursor(cursor: string): number | null {
  if (!/^[A-Za-z0-9_-]{1,32}$/.test(cursor)) return null;
  try {
    const standard = cursor.replaceAll("-", "+").replaceAll("_", "/");
    const padded = standard + "=".repeat((4 - (standard.length % 4)) % 4);
    const value = Number(atob(padded));
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}
