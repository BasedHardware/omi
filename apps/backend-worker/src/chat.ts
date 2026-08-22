import { chatMessagePayloadHash } from "@omi-core/kernel";
import { parseRecordId } from "@omi-core/contracts";
import type { ChatCompletedAssistantMessage } from "@omi-core/contracts";

import {
  CHAT_CAPABILITIES,
  type ChatCreate,
  type ChatMessage,
  type GenerationEvent,
} from "./wire";

type StoredMessage = {
  id: string;
  text: string;
  sender: "human" | "ai";
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
  | "invalid_cursor";

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
  input: ChatCreate;
};

export async function admitMessage(
  db: D1Database,
  accountId: string,
  input: ChatCreate,
  chatLimit: number | null
): Promise<Admission | "conflict" | "entitlement"> {
  const payloadHash = computePayloadHash(input);
  const prior = await db
    .prepare(
      "SELECT payload, generation_id AS generationId FROM chat_admissions WHERE message_id = ? AND account_id = ?"
    )
    .bind(input.id, accountId)
    .first<{ payload: string; generationId: string }>();

  if (prior !== null) {
    const previous = JSON.parse(prior.payload) as ChatCreate;
    if (computePayloadHash(previous) !== payloadHash) return "conflict";
    let message = await readMessage(db, accountId, input.id);
    if (message === null)
      throw new Error("admission references missing message");
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
  const message = humanMessage(input, payloadHash, position);

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
  olderCursor?: string
): Promise<HistoryResult> {
  const boundary = olderCursor === undefined ? null : decodeCursor(olderCursor);
  if (olderCursor !== undefined && boundary === null) return "invalid_cursor";

  const result = await db
    .prepare(
      `SELECT id, text, sender, created_at AS createdAt, generation_outcome AS generationOutcome, position, payload
       FROM chat_messages
       WHERE account_id = ? AND (? IS NULL OR position < ?)
       ORDER BY position DESC
       LIMIT ?`
    )
    .bind(accountId, boundary, boundary, limit + 1)
    .all<StoredMessage>();

  const rows = result.results;
  const hasOlder = rows.length > limit;
  const pageRows = rows.slice(0, limit).reverse();
  const oldest = pageRows[0];
  return {
    messages: pageRows.map((row) => storedMessage(row)),
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
  identity: SettingsIdentity,
  planLabel: string,
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
    identity,
    entitlement: {
      planLabel,
      limitKey: "chat",
      used,
      limit: chatLimit,
      limitReached: chatLimit !== null && used >= chatLimit,
      upgradeAvailable: true,
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
  if (terminal !== null) return "terminal";
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
  return {
    generationId: row.generationId,
    input: JSON.parse(row.payload) as ChatCreate,
  };
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
  if (human === null) throw new Error("human message not found for generation");

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
  generationId: string
): Promise<GenerationEvent> {
  const event: GenerationEvent = {
    id: "2",
    kind: "failed",
    error: { code: "generation_failed", retryable: true },
  };
  await appendGenerationEvent(db, accountId, generationId, event);
  return event;
}

export async function readGenerationEvents(
  db: D1Database,
  accountId: string,
  generationId: string
): Promise<GenerationEvent[]> {
  const result = await db
    .prepare(
      "SELECT payload FROM chat_generation_events WHERE generation_id = ? AND account_id = ? ORDER BY ordinal"
    )
    .bind(generationId, accountId)
    .all<{ payload: string }>();

  return result.results.map((row) => {
    const event = parseEvent(row.payload);
    return event.kind === "done"
      ? { ...event, message: generationMessageSync(event) }
      : event;
  });
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
): Promise<GenerationEvent | null> {
  const events = await readGenerationEvents(db, accountId, generationId);
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
  return storedMessage(row);
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
  position: number
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
    attachments: [],
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

function storedMessage(row: StoredMessage): ChatMessage {
  if (row.payload !== null) return JSON.parse(row.payload) as ChatMessage;
  const base = {
    id: recordId(
      row.id.startsWith("generation:")
        ? row.id.slice("generation:".length)
        : row.id
    ),
    text: row.text,
    sender: row.sender,
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
  return row.sender === "human"
    ? { ...base, sender: "human", generationOutcome: null }
    : {
        ...base,
        sender: "ai",
        generationOutcome:
          row.generationOutcome === "cancelled" ? "cancelled" : "completed",
      };
}

function parseEvent(payload: string): GenerationEvent {
  const event = JSON.parse(payload) as
    | GenerationEvent
    | { id: string; kind: string };
  return event.kind === "accepted"
    ? { id: event.id, kind: "snapshot", text: "" }
    : (event as GenerationEvent);
}

function generationMessageSync(
  event: GenerationEvent
): ChatCompletedAssistantMessage {
  if (
    event.kind === "done" &&
    event.message !== null &&
    event.message !== undefined
  ) {
    return event.message;
  }
  throw new Error("done event missing message");
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
