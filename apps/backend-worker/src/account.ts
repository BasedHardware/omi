import { DurableObject } from "cloudflare:workers";
import { chatMessagePayloadHash } from "@omi-core/kernel";
import { parseRecordId } from "@omi-core/contracts";
import type { ChatCompletedAssistantMessage } from "@omi-core/contracts";

import {
  gatewayConfig,
  gatewayModeEnabled,
  generateViaGateway,
  type GatewaySecretEnv,
} from "./openrouter";
import { gatewayFailureEvent } from "./observability";
import {
  CHAT_CAPABILITIES,
  type ChatCreate,
  type ChatMessage,
  type GenerationEvent,
} from "./wire";

type Admission = {
  message: ChatMessage;
  generation: { id: string };
  created: boolean;
};

type SettingsIdentity = {
  displayName: string;
  email: string;
};

type SettingsEntitlement = {
  planLabel: string;
  limitKey: string;
  used: number;
  limit: number | null;
  limitReached: boolean;
  upgradeAvailable: boolean;
};

type SettingsSnapshot = {
  identity: SettingsIdentity;
  entitlement: SettingsEntitlement | null;
};

type AccountConfiguration = SettingsIdentity & {
  planLabel: string;
  chatLimit: number | null;
};

type StoredMessage = {
  id: string;
  text: string;
  sender: "human" | "ai";
  createdAt: number;
  generationOutcome: "completed" | "cancelled" | null;
  position: number;
  payload: string | null;
};

type HistoryResult =
  | {
      messages: ChatMessage[];
      page:
        | { olderCursor: string; hasOlder: true }
        | { olderCursor: null; hasOlder: false };
      capabilities: typeof CHAT_CAPABILITIES;
    }
  | "invalid_cursor";

export class AccountBackend extends DurableObject<Env & GatewaySecretEnv> {
  private readonly waiters = new Map<
    string,
    Set<(event: GenerationEvent) => void>
  >();

  constructor(ctx: DurableObjectState, env: Env & GatewaySecretEnv) {
    super(ctx, env);
    void ctx.blockConcurrencyWhile(async () => {
      this.ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY,
          text TEXT NOT NULL,
          sender TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          generation_outcome TEXT,
          position INTEGER NOT NULL,
          payload TEXT
        );
        CREATE TABLE IF NOT EXISTS admissions (
          message_id TEXT PRIMARY KEY,
          op_id TEXT NOT NULL,
          payload TEXT NOT NULL,
          generation_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS generation_events (
          generation_id TEXT NOT NULL,
          event_id TEXT NOT NULL,
          ordinal INTEGER NOT NULL,
          payload TEXT NOT NULL,
          PRIMARY KEY (generation_id, event_id)
        );
        CREATE TABLE IF NOT EXISTS account_identity (
          singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
          display_name TEXT NOT NULL,
          email TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS entitlement (
          limit_key TEXT PRIMARY KEY,
          plan_label TEXT NOT NULL,
          used REAL NOT NULL CHECK (used >= 0),
          limit_value REAL,
          upgrade_available INTEGER NOT NULL CHECK (upgrade_available IN (0, 1))
        );
      `);
      const messageColumns = this.ctx.storage.sql
        .exec<{ name: string }>("PRAGMA table_info(messages)")
        .toArray();
      if (!messageColumns.some((column) => column.name === "payload")) {
        this.ctx.storage.sql.exec(
          "ALTER TABLE messages ADD COLUMN payload TEXT"
        );
      }
    });
  }

  async configure(configuration: AccountConfiguration): Promise<void> {
    this.ctx.storage.sql.exec(
      "INSERT INTO account_identity (singleton, display_name, email) VALUES (1, ?, ?) ON CONFLICT(singleton) DO UPDATE SET display_name = excluded.display_name, email = excluded.email",
      configuration.displayName,
      configuration.email
    );
    this.ctx.storage.sql.exec(
      "INSERT INTO entitlement (limit_key, plan_label, used, limit_value, upgrade_available) VALUES ('chat', ?, 0, ?, 1) ON CONFLICT(limit_key) DO UPDATE SET plan_label = excluded.plan_label, limit_value = excluded.limit_value, upgrade_available = excluded.upgrade_available",
      configuration.planLabel,
      configuration.chatLimit
    );
  }

  async settings(): Promise<SettingsSnapshot> {
    const identity = this.ctx.storage.sql
      .exec<SettingsIdentity>(
        "SELECT display_name AS displayName, email FROM account_identity WHERE singleton = 1"
      )
      .one();
    const row = this.ctx.storage.sql
      .exec<{
        planLabel: string;
        limitKey: string;
        used: number;
        limitValue: number | null;
        upgradeAvailable: number;
      }>(
        "SELECT plan_label AS planLabel, limit_key AS limitKey, used, limit_value AS limitValue, upgrade_available AS upgradeAvailable FROM entitlement WHERE limit_key = 'chat'"
      )
      .toArray()[0];
    return {
      identity,
      entitlement:
        row === undefined
          ? null
          : {
              planLabel: row.planLabel,
              limitKey: row.limitKey,
              used: row.used,
              limit: row.limitValue,
              limitReached:
                row.limitValue !== null && row.used >= row.limitValue,
              upgradeAvailable: row.upgradeAvailable === 1,
            },
    };
  }

  async history(limit: number, olderCursor?: string): Promise<HistoryResult> {
    const boundary =
      olderCursor === undefined ? null : this.decodeCursor(olderCursor);
    if (olderCursor !== undefined && boundary === null) return "invalid_cursor";
    const rows = this.ctx.storage.sql
      .exec<StoredMessage>(
        `SELECT id, text, sender, created_at AS createdAt, generation_outcome AS generationOutcome, position, payload
         FROM messages
         WHERE (? IS NULL OR position < ?)
         ORDER BY position DESC
         LIMIT ?`,
        boundary,
        boundary,
        limit + 1
      )
      .toArray();
    const hasOlder = rows.length > limit;
    const pageRows = rows.slice(0, limit).reverse();
    const oldest = pageRows[0];
    return {
      messages: pageRows.map((row) => this.storedMessage(row)),
      page:
        hasOlder && oldest !== undefined
          ? { olderCursor: this.encodeCursor(oldest.position), hasOlder: true }
          : { olderCursor: null, hasOlder: false },
      capabilities: CHAT_CAPABILITIES,
    };
  }

  async admit(
    input: ChatCreate
  ): Promise<Admission | "conflict" | "entitlement"> {
    const payloadHash = this.payloadHash(input);
    const prior = this.ctx.storage.sql
      .exec<{ payload: string; generationId: string }>(
        "SELECT payload, generation_id AS generationId FROM admissions WHERE message_id = ?",
        input.id
      )
      .toArray()[0];
    if (prior !== undefined) {
      const previous = JSON.parse(prior.payload) as ChatCreate;
      if (this.payloadHash(previous) !== payloadHash) return "conflict";
      let message = this.message(input.id);
      if (input.journalRevision > message.journalRevision) {
        message = {
          ...message,
          updatedAt: Math.max(message.updatedAt, input.at),
          journalRevision: input.journalRevision,
          revision: String(input.journalRevision),
        };
        this.ctx.storage.sql.exec(
          "UPDATE messages SET payload = ? WHERE id = ?",
          JSON.stringify(message),
          input.id
        );
      }
      if (this.terminalEvent(prior.generationId) === null) {
        await this.ensureGenerationAlarm();
      }
      return {
        message,
        generation: { id: prior.generationId },
        created: false,
      };
    }
    const entitlement = this.ctx.storage.sql
      .exec<{ used: number; limitValue: number | null }>(
        "SELECT used, limit_value AS limitValue FROM entitlement WHERE limit_key = 'chat'"
      )
      .toArray()[0];
    if (
      entitlement !== undefined &&
      entitlement.limitValue !== null &&
      entitlement.used >= entitlement.limitValue
    ) {
      return "entitlement";
    }
    const generationId = crypto.randomUUID();
    const position = this.nextPosition();
    const message = this.humanMessage(input, payloadHash, position);
    this.ctx.storage.sql.exec(
      "INSERT INTO messages (id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, 'human', ?, NULL, ?, ?)",
      message.id,
      message.text,
      message.createdAt,
      position,
      JSON.stringify(message)
    );
    this.ctx.storage.sql.exec(
      "INSERT INTO admissions (message_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?)",
      input.id,
      input.opId,
      JSON.stringify(input),
      generationId
    );
    if (entitlement !== undefined) {
      this.ctx.storage.sql.exec(
        "UPDATE entitlement SET used = used + 1 WHERE limit_key = 'chat'"
      );
    }
    this.appendEvent(generationId, {
      id: "1",
      kind: "snapshot",
      text: "",
    });
    await this.ensureGenerationAlarm();
    return {
      message,
      generation: { id: generationId },
      created: true,
    };
  }

  async complete(generationId: string, text: string): Promise<void> {
    if (this.terminalEvent(generationId) !== null) return;
    const admission = this.ctx.storage.sql
      .exec<{ messageId: string }>(
        "SELECT message_id AS messageId FROM admissions WHERE generation_id = ?",
        generationId
      )
      .toArray()[0];
    if (admission === undefined) return;
    const human = this.message(admission.messageId);
    const createdAt = Date.now();
    const message: ChatCompletedAssistantMessage = {
      id: this.recordId(generationId),
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
    this.storeMessage(message);
    this.appendEvent(generationId, { id: "2", kind: "done", message });
  }

  async fail(generationId: string): Promise<void> {
    if (this.terminalEvent(generationId) !== null) return;
    this.appendEvent(generationId, {
      id: "2",
      kind: "failed",
      error: { code: "generation_failed", retryable: true },
    });
  }

  async cancel(
    generationId: string
  ): Promise<"not_found" | "accepted" | "terminal"> {
    if (!this.hasGeneration(generationId)) return "not_found";
    if (this.terminalEvent(generationId) !== null) return "terminal";
    this.appendEvent(generationId, {
      id: "2",
      kind: "cancelled",
      message: null,
    });
    return "accepted";
  }

  override async alarm(): Promise<void> {
    const pending = this.ctx.storage.sql
      .exec<{ generationId: string; payload: string }>(
        `SELECT admissions.generation_id AS generationId, admissions.payload
         FROM admissions
         WHERE NOT EXISTS (
           SELECT 1 FROM generation_events
           WHERE generation_events.generation_id = admissions.generation_id
             AND generation_events.ordinal = 2
         )
         ORDER BY admissions.rowid
         LIMIT 1`
      )
      .toArray()[0];
    if (pending === undefined) return;
    const input = JSON.parse(pending.payload) as ChatCreate;
    await this.runGeneration(pending.generationId, input.text);
    await this.ensureGenerationAlarm();
  }

  override async fetch(request: Request): Promise<Response> {
    const generationId = new URL(request.url).searchParams.get("generationId");
    if (generationId === null || !this.hasGeneration(generationId))
      return new Response(null, { status: 404 });
    const lastEventId = request.headers.get("last-event-id");
    const allEvents = this.events(generationId);
    const replay = this.selectReplay(allEvents, lastEventId);
    if (replay === "expired")
      return Response.json(
        {
          error: {
            code: "generation_replay_expired",
            retryable: false,
            action: "refresh_history",
          },
        },
        { status: 410, headers: { "cache-control": "no-store" } }
      );
    const existing = replay;
    if (existing.some((event) => this.isTerminal(event)))
      return this.sse(existing);
    const encoder = new TextEncoder();
    let listener: ((event: GenerationEvent) => void) | undefined;
    const stream = new ReadableStream<Uint8Array>({
      start: (controller) => {
        for (const event of existing)
          controller.enqueue(encoder.encode(this.encode(event)));
        listener = (event) => {
          try {
            controller.enqueue(encoder.encode(this.encode(event)));
            if (this.isTerminal(event)) controller.close();
          } catch {
            this.waiters.get(generationId)?.delete(listener!);
          }
        };
        const listeners = this.waiters.get(generationId) ?? new Set();
        listeners.add(listener);
        this.waiters.set(generationId, listeners);
      },
      cancel: () => {
        if (listener !== undefined)
          this.waiters.get(generationId)?.delete(listener);
      },
    });
    return new Response(stream, {
      headers: {
        "cache-control": "no-cache, no-store",
        "content-type": "text/event-stream",
      },
    });
  }

  private nextPosition(): number {
    return this.ctx.storage.sql
      .exec<{ position: number }>(
        "SELECT COALESCE(MAX(position), 0) + 1 AS position FROM messages"
      )
      .one().position;
  }

  private async ensureGenerationAlarm(): Promise<void> {
    const pending = this.ctx.storage.sql
      .exec<{ count: number }>(
        `SELECT COUNT(*) AS count
         FROM admissions
         WHERE NOT EXISTS (
           SELECT 1 FROM generation_events
           WHERE generation_events.generation_id = admissions.generation_id
             AND generation_events.ordinal = 2
         )`
      )
      .one().count;
    if (pending > 0 && (await this.ctx.storage.getAlarm()) === null) {
      await this.ctx.storage.setAlarm(Date.now() + 1_000);
    }
  }

  private async runGeneration(
    generationId: string,
    prompt: string
  ): Promise<void> {
    if (gatewayModeEnabled(this.env)) {
      const config = gatewayConfig(this.env);
      if (config === null) {
        console.error(
          JSON.stringify(
            gatewayFailureEvent({
              message: "gateway_unconfigured",
              correlationId: generationId,
              model: "unconfigured",
              status: 0,
            })
          )
        );
        await this.fail(generationId);
        return;
      }
      const result = await generateViaGateway(config, prompt, generationId);
      if (result.kind === "error") {
        await this.fail(generationId);
      } else {
        await this.complete(generationId, result.text);
      }
      return;
    }
    try {
      const result = await this.env.AI.run(
        this.env.AI_MODEL as keyof AiModels,
        {
          messages: [
            {
              role: "system",
              content: "You are Omi, a concise and helpful personal assistant.",
            },
            { role: "user", content: prompt },
          ],
          max_tokens: 768,
        }
      );
      const response = result as { response?: unknown };
      if (
        typeof response.response !== "string" ||
        response.response.length === 0
      ) {
        await this.fail(generationId);
      } else {
        await this.complete(generationId, response.response);
      }
    } catch {
      await this.fail(generationId);
    }
  }

  private message(id: string): ChatMessage {
    const stored = this.ctx.storage.sql
      .exec<StoredMessage>(
        "SELECT id, text, sender, created_at AS createdAt, generation_outcome AS generationOutcome, position, payload FROM messages WHERE id = ?",
        id
      )
      .one();
    return this.storedMessage(stored);
  }

  private storeMessage(message: ChatMessage): void {
    const position = this.nextPosition();
    const stored = { ...message, revision: String(position) };
    this.ctx.storage.sql.exec(
      "INSERT OR IGNORE INTO messages (id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
      stored.id,
      stored.text,
      stored.sender,
      stored.createdAt,
      stored.generationOutcome,
      position,
      JSON.stringify(stored)
    );
  }

  private hasGeneration(generationId: string): boolean {
    return (
      this.ctx.storage.sql
        .exec<{ count: number }>(
          "SELECT COUNT(*) AS count FROM admissions WHERE generation_id = ?",
          generationId
        )
        .one().count > 0
    );
  }

  private terminalEvent(generationId: string): GenerationEvent | null {
    return (
      this.events(generationId).find((event) => this.isTerminal(event)) ?? null
    );
  }

  private events(generationId: string): GenerationEvent[] {
    return this.ctx.storage.sql
      .exec<{ payload: string }>(
        "SELECT payload FROM generation_events WHERE generation_id = ? ORDER BY ordinal",
        generationId
      )
      .toArray()
      .map((row) => {
        const event = this.parseEvent(row.payload);
        return event.kind === "done"
          ? { ...event, message: this.generationMessage(generationId) }
          : event;
      });
  }

  private appendEvent(generationId: string, event: GenerationEvent): void {
    this.ctx.storage.sql.exec(
      "INSERT OR IGNORE INTO generation_events (generation_id, event_id, ordinal, payload) VALUES (?, ?, ?, ?)",
      generationId,
      event.id,
      Number(event.id),
      JSON.stringify(event)
    );
    for (const listener of this.waiters.get(generationId) ?? [])
      listener(event);
    if (this.isTerminal(event)) this.waiters.delete(generationId);
  }

  private encode(event: GenerationEvent): string {
    const { id: _id, ...frame } = event;
    return `id: ${event.id}\nevent: ${event.kind}\ndata: ${JSON.stringify(
      frame
    )}\n\n`;
  }

  private sse(events: GenerationEvent[]): Response {
    return new Response(events.map((event) => this.encode(event)).join(""), {
      headers: {
        "cache-control": "no-cache, no-store",
        "content-type": "text/event-stream",
      },
    });
  }

  private humanMessage(
    input: ChatCreate,
    payloadHash: string,
    position: number
  ): ChatMessage {
    return {
      id: this.recordId(input.id),
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

  private payloadHash(input: ChatCreate): string {
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

  private storedMessage(row: StoredMessage): ChatMessage {
    if (row.payload !== null) return JSON.parse(row.payload) as ChatMessage;
    const base = {
      id: this.recordId(
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

  private parseEvent(payload: string): GenerationEvent {
    const event = JSON.parse(payload) as
      | GenerationEvent
      | { id: string; kind: string };
    return event.kind === "accepted"
      ? { id: event.id, kind: "snapshot", text: "" }
      : (event as GenerationEvent);
  }

  private recordId(value: string): ChatMessage["id"] {
    const parsed = parseRecordId(value);
    if (parsed === null) throw new Error("stored chat message id is invalid");
    return parsed.id;
  }

  private generationMessage(
    generationId: string
  ): ChatCompletedAssistantMessage {
    const row = this.ctx.storage.sql
      .exec<StoredMessage>(
        "SELECT id, text, sender, created_at AS createdAt, generation_outcome AS generationOutcome, position, payload FROM messages WHERE id = ? OR id = ? LIMIT 1",
        generationId,
        `generation:${generationId}`
      )
      .one();
    const message = this.storedMessage(row);
    if (message.sender !== "ai" || message.generationOutcome !== "completed") {
      throw new Error("generation terminal message is not completed");
    }
    return message;
  }

  private isTerminal(event: GenerationEvent): boolean {
    return (
      event.kind === "done" ||
      event.kind === "failed" ||
      event.kind === "cancelled"
    );
  }

  private selectReplay(
    events: GenerationEvent[],
    lastEventId: string | null
  ): GenerationEvent[] | "expired" {
    if (lastEventId === null) return events;
    const terminal = events.find((event) => this.isTerminal(event));
    const cursorIndex = events.findIndex((event) => event.id === lastEventId);
    if (cursorIndex < 0) return terminal === undefined ? "expired" : [terminal];
    const replay = events.slice(cursorIndex + 1);
    return replay.length === 0 && terminal !== undefined ? [terminal] : replay;
  }

  private encodeCursor(position: number): string {
    return btoa(String(position))
      .replaceAll("+", "-")
      .replaceAll("/", "_")
      .replace(/=+$/, "");
  }

  private decodeCursor(cursor: string): number | null {
    if (!/^[A-Za-z0-9_-]{1,32}$/.test(cursor)) return null;
    try {
      const value = Number(
        atob(cursor.replaceAll("-", "+").replaceAll("_", "/"))
      );
      return Number.isSafeInteger(value) && value > 0 ? value : null;
    } catch {
      return null;
    }
  }
}
