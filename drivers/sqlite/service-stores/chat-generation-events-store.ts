import type { Database } from "bun:sqlite";

import type {
  AppendChatGenerationEventOutcome,
  ChatCancellationRequestOutcome,
  ChatGenerationEvent,
  ChatGenerationEventsStore,
  ChatGenerationFrame,
  ChatGenerationLifecycle,
} from "../../../apps/service/stores/chat-generation-events-store";
import { configureServiceStoreConnection } from "./connection";

interface EventRow {
  readonly event_id: string;
  readonly generation_id: string;
  readonly sequence: number;
  readonly created_at: number;
  readonly frame_json: string;
}

const eventFromRow = (row: EventRow): ChatGenerationEvent => Object.freeze({
  id: row.event_id,
  generationId: row.generation_id,
  sequence: row.sequence,
  createdAt: row.created_at,
  frame: JSON.parse(row.frame_json) as ChatGenerationFrame,
});

/** SQLite adapter for the reconnectable generation event log. */
export class SqliteChatGenerationEventsStore implements ChatGenerationEventsStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_chat_generation_events (
        account_id TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        event_id TEXT NOT NULL,
        created_at INTEGER NOT NULL CHECK (created_at >= 0),
        frame_json TEXT NOT NULL,
        PRIMARY KEY (account_id, generation_id, sequence),
        UNIQUE (account_id, generation_id, event_id)
      );
      CREATE INDEX IF NOT EXISTS service_chat_generation_events_by_id
        ON service_chat_generation_events (account_id, generation_id, event_id);
      CREATE TABLE IF NOT EXISTS service_chat_generation_lifecycle (
        account_id TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('active', 'cancellation_requested', 'terminal')),
        PRIMARY KEY (account_id, generation_id)
      );
      INSERT INTO service_chat_generation_lifecycle (account_id, generation_id, state)
      SELECT
        account_id,
        generation_id,
        CASE WHEN MAX(CASE
          WHEN json_extract(frame_json, '$.kind') IN ('done', 'failed', 'cancelled') THEN 1
          ELSE 0
        END) = 1 THEN 'terminal' ELSE 'active' END
      FROM service_chat_generation_events
      GROUP BY account_id, generation_id
      ON CONFLICT (account_id, generation_id) DO NOTHING;
    `);
  }

  append(input: Parameters<ChatGenerationEventsStore["append"]>[0]): AppendChatGenerationEventOutcome {
    if (!input.eventId || !input.generationId || !Number.isSafeInteger(input.createdAt)
      || input.createdAt < 0) {
      throw new TypeError("invalid chat generation event");
    }
    const frameJson = JSON.stringify(input.frame);
    const append = this.db.transaction((): AppendChatGenerationEventOutcome => {
      const existing = this.db.query(`
        SELECT event_id, generation_id, sequence, created_at, frame_json
        FROM service_chat_generation_events
        WHERE account_id = ? AND generation_id = ? AND event_id = ?
      `).get(input.accountId, input.generationId, input.eventId) as EventRow | null;
      if (existing !== null) {
        return existing.created_at === input.createdAt && existing.frame_json === frameJson
          ? { kind: "replay", event: eventFromRow(existing) }
          : { kind: "conflict" };
      }
      const row = this.db.query(`
        SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
        FROM service_chat_generation_events
        WHERE account_id = ? AND generation_id = ?
      `).get(input.accountId, input.generationId) as { readonly sequence: number };
      this.db.query(`
        INSERT INTO service_chat_generation_events (
          account_id, generation_id, sequence, event_id, created_at, frame_json
        ) VALUES (?, ?, ?, ?, ?, ?)
      `).run(
        input.accountId,
        input.generationId,
        row.sequence,
        input.eventId,
        input.createdAt,
        frameJson,
      );
      this.db.query(`
        INSERT INTO service_chat_generation_lifecycle (account_id, generation_id, state)
        VALUES (?, ?, ?)
        ON CONFLICT (account_id, generation_id) DO UPDATE SET
          state = CASE
            WHEN excluded.state = 'terminal' THEN 'terminal'
            ELSE service_chat_generation_lifecycle.state
          END
      `).run(
        input.accountId,
        input.generationId,
        ["done", "failed", "cancelled"].includes(input.frame.kind) ? "terminal" : "active",
      );
      return {
        kind: "appended",
        event: eventFromRow({
          event_id: input.eventId,
          generation_id: input.generationId,
          sequence: row.sequence,
          created_at: input.createdAt,
          frame_json: frameJson,
        }),
      };
    });
    return append.immediate();
  }

  listAfter(
    accountId: string,
    generationId: string,
    afterEventId: string | null,
  ): readonly ChatGenerationEvent[] | null {
    let afterSequence = 0;
    if (afterEventId !== null) {
      const row = this.db.query(`
        SELECT sequence FROM service_chat_generation_events
        WHERE account_id = ? AND generation_id = ? AND event_id = ?
      `).get(accountId, generationId, afterEventId) as { readonly sequence: number } | null;
      if (row === null) return null;
      afterSequence = row.sequence;
    }
    const rows = this.db.query(`
      SELECT event_id, generation_id, sequence, created_at, frame_json
      FROM service_chat_generation_events
      WHERE account_id = ? AND generation_id = ? AND sequence > ?
      ORDER BY sequence ASC
    `).all(accountId, generationId, afterSequence) as EventRow[];
    return Object.freeze(rows.map(eventFromRow));
  }

  readLifecycle(accountId: string, generationId: string): ChatGenerationLifecycle | null {
    const row = this.db.query(`
      SELECT state FROM service_chat_generation_lifecycle
      WHERE account_id = ? AND generation_id = ?
    `).get(accountId, generationId) as { readonly state: ChatGenerationLifecycle["state"] } | null;
    return row === null ? null : Object.freeze({ accountId, generationId, state: row.state });
  }

  listUnterminated(): readonly ChatGenerationLifecycle[] {
    const rows = this.db.query(`
      SELECT account_id, generation_id, state
      FROM service_chat_generation_lifecycle
      WHERE state != 'terminal'
      ORDER BY account_id, generation_id
    `).all() as Array<{
      readonly account_id: string;
      readonly generation_id: string;
      readonly state: ChatGenerationLifecycle["state"];
    }>;
    return Object.freeze(rows.map((row) => Object.freeze({
      accountId: row.account_id,
      generationId: row.generation_id,
      state: row.state,
    })));
  }

  requestCancellation(accountId: string, generationId: string): ChatCancellationRequestOutcome {
    const request = this.db.transaction((): ChatCancellationRequestOutcome => {
      const lifecycle = this.readLifecycle(accountId, generationId);
      if (lifecycle === null) return { kind: "not_found" };
      if (lifecycle.state === "terminal") return { kind: "already_terminal" };
      if (lifecycle.state === "cancellation_requested") return { kind: "already_requested" };
      this.db.query(`
        UPDATE service_chat_generation_lifecycle SET state = 'cancellation_requested'
        WHERE account_id = ? AND generation_id = ? AND state = 'active'
      `).run(accountId, generationId);
      return { kind: "accepted" };
    });
    return request.immediate();
  }

  reset(): void {
    const reset = this.db.transaction(() => {
      this.db.exec("DELETE FROM service_chat_generation_events;");
      this.db.exec("DELETE FROM service_chat_generation_lifecycle;");
    });
    reset.immediate();
  }
}
