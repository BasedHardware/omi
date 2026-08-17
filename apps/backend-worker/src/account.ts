import { DurableObject } from "cloudflare:workers";

import type { ChatCreate, ChatMessage, GenerationEvent } from "./wire";

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

type StoredMessage = ChatMessage & { position: number };

export class AccountBackend extends DurableObject<Env> {
  private readonly waiters = new Map<
    string,
    Set<(event: GenerationEvent) => void>
  >();

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    void ctx.blockConcurrencyWhile(async () => {
      this.ctx.storage.sql.exec(`
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY,
          text TEXT NOT NULL,
          sender TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          generation_outcome TEXT,
          position INTEGER NOT NULL
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
    });
  }

  async configure(configuration: AccountConfiguration): Promise<void> {
    this.ctx.storage.sql.exec(
      "INSERT OR IGNORE INTO account_identity (singleton, display_name, email) VALUES (1, ?, ?)",
      configuration.displayName,
      configuration.email
    );
    this.ctx.storage.sql.exec(
      "INSERT OR IGNORE INTO entitlement (limit_key, plan_label, used, limit_value, upgrade_available) VALUES ('chat', ?, 0, ?, 1)",
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

  async history(limit: number): Promise<{
    messages: ChatMessage[];
    page: { olderCursor: null; hasOlder: false };
  }> {
    const rows = this.ctx.storage.sql
      .exec<StoredMessage>(
        "SELECT id, text, sender, created_at AS createdAt, generation_outcome AS generationOutcome, position FROM messages ORDER BY position DESC LIMIT ?",
        limit
      )
      .toArray()
      .reverse();
    return {
      messages: rows.map(({ position: _position, ...message }) => message),
      page: { olderCursor: null, hasOlder: false },
    };
  }

  async admit(
    input: ChatCreate
  ): Promise<Admission | "conflict" | "entitlement"> {
    const payload = JSON.stringify(input);
    const prior = this.ctx.storage.sql
      .exec<{ payload: string; generationId: string }>(
        "SELECT payload, generation_id AS generationId FROM admissions WHERE message_id = ?",
        input.id
      )
      .toArray()[0];
    if (prior !== undefined) {
      if (prior.payload !== payload) return "conflict";
      const message = this.message(input.id);
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
    this.ctx.storage.sql.exec(
      "INSERT INTO messages (id, text, sender, created_at, generation_outcome, position) VALUES (?, ?, 'human', ?, NULL, ?)",
      input.id,
      input.text,
      input.at,
      position
    );
    this.ctx.storage.sql.exec(
      "INSERT INTO admissions (message_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?)",
      input.id,
      input.opId,
      payload,
      generationId
    );
    if (entitlement !== undefined) {
      this.ctx.storage.sql.exec(
        "UPDATE entitlement SET used = used + 1 WHERE limit_key = 'chat'"
      );
    }
    this.appendEvent(generationId, {
      id: "1",
      kind: "accepted",
    });
    return {
      message: this.message(input.id),
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
    const message: ChatMessage = {
      id: `generation:${generationId}`,
      text,
      sender: "ai",
      createdAt: Date.now(),
      generationOutcome: "completed",
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

  async cancel(generationId: string): Promise<boolean> {
    if (!this.hasGeneration(generationId)) return false;
    if (this.terminalEvent(generationId) === null) {
      this.appendEvent(generationId, {
        id: "2",
        kind: "cancelled",
        message: null,
      });
    }
    return true;
  }

  override async fetch(request: Request): Promise<Response> {
    const generationId = new URL(request.url).searchParams.get("generationId");
    if (generationId === null || !this.hasGeneration(generationId))
      return new Response(null, { status: 404 });
    const lastEventId = request.headers.get("last-event-id");
    const existing = this.events(generationId).filter(
      (event) => event.id !== lastEventId
    );
    const terminal = existing.find((event) =>
      ["done", "failed", "cancelled"].includes(event.kind)
    );
    if (terminal !== undefined) return this.sse(existing);
    const stream = new TransformStream<Uint8Array, Uint8Array>();
    const writer = stream.writable.getWriter();
    const encoder = new TextEncoder();
    for (const event of existing)
      await writer.write(encoder.encode(this.encode(event)));
    const settle = async (event: GenerationEvent): Promise<void> => {
      await writer.write(encoder.encode(this.encode(event)));
      if (["done", "failed", "cancelled"].includes(event.kind))
        await writer.close();
    };
    const listener = (event: GenerationEvent): void => {
      void settle(event);
    };
    const listeners = this.waiters.get(generationId) ?? new Set();
    listeners.add(listener);
    this.waiters.set(generationId, listeners);
    request.signal.addEventListener(
      "abort",
      () => {
        listeners.delete(listener);
        void writer.abort();
      },
      { once: true }
    );
    return new Response(stream.readable, {
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

  private message(id: string): ChatMessage {
    return this.ctx.storage.sql
      .exec<ChatMessage>(
        "SELECT id, text, sender, created_at AS createdAt, generation_outcome AS generationOutcome FROM messages WHERE id = ?",
        id
      )
      .one();
  }

  private storeMessage(message: ChatMessage): void {
    this.ctx.storage.sql.exec(
      "INSERT OR IGNORE INTO messages (id, text, sender, created_at, generation_outcome, position) VALUES (?, ?, ?, ?, ?, ?)",
      message.id,
      message.text,
      message.sender,
      message.createdAt,
      message.generationOutcome,
      this.nextPosition()
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
      this.events(generationId).find((event) =>
        ["done", "failed", "cancelled"].includes(event.kind)
      ) ?? null
    );
  }

  private events(generationId: string): GenerationEvent[] {
    return this.ctx.storage.sql
      .exec<{ payload: string }>(
        "SELECT payload FROM generation_events WHERE generation_id = ? ORDER BY ordinal",
        generationId
      )
      .toArray()
      .map((row) => JSON.parse(row.payload) as GenerationEvent);
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
    if (["done", "failed", "cancelled"].includes(event.kind))
      this.waiters.delete(generationId);
  }

  private encode(event: GenerationEvent): string {
    return `id: ${event.id}\ndata: ${JSON.stringify(event)}\n\n`;
  }

  private sse(events: GenerationEvent[]): Response {
    return new Response(events.map((event) => this.encode(event)).join(""), {
      headers: {
        "cache-control": "no-cache, no-store",
        "content-type": "text/event-stream",
      },
    });
  }
}
