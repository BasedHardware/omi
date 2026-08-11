import type { Database } from "bun:sqlite";

import type {
  AppendChatGenerationEventOutcome,
  ChatCancellationRequestOutcome,
  ChatGenerationEvent,
  ChatGenerationEventsStore,
  ChatGenerationFrame,
  ChatGenerationLifecycle,
  ChatGenerationCompactionResult,
  ChatGenerationRetentionMetadata,
  ChatGenerationRetentionPolicy,
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
      CREATE TABLE IF NOT EXISTS service_chat_generation_retention (
        account_id TEXT NOT NULL,
        generation_id TEXT NOT NULL,
        ttl_ms INTEGER NOT NULL CHECK (ttl_ms > 0),
        expires_at INTEGER NOT NULL CHECK (expires_at >= 0),
        compacted_at INTEGER,
        replay_cursor TEXT NOT NULL,
        redacted_event_count INTEGER NOT NULL CHECK (redacted_event_count >= 0),
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
      const terminal = this.db.query(`
        SELECT event_id, generation_id, sequence, created_at, frame_json
        FROM service_chat_generation_events
        WHERE account_id = ? AND generation_id = ?
          AND json_extract(frame_json, '$.kind') IN ('done', 'failed', 'cancelled')
        ORDER BY sequence ASC
        LIMIT 1
      `).get(input.accountId, input.generationId) as EventRow | null;
      if (terminal !== null) return { kind: "replay", event: eventFromRow(terminal) };

      const isTerminal = ["done", "failed", "cancelled"].includes(input.frame.kind);
      if (isTerminal) {
        this.db.query(`
          INSERT INTO service_chat_generation_lifecycle (account_id, generation_id, state)
          VALUES (?, ?, 'active')
          ON CONFLICT (account_id, generation_id) DO NOTHING
        `).run(input.accountId, input.generationId);
        const claimed = this.db.query(`
          UPDATE service_chat_generation_lifecycle
          SET state = 'terminal'
          WHERE account_id = ? AND generation_id = ? AND state != 'terminal'
        `).run(input.accountId, input.generationId);
        if (claimed.changes !== 1) {
          const winner = this.db.query(`
            SELECT event_id, generation_id, sequence, created_at, frame_json
            FROM service_chat_generation_events
            WHERE account_id = ? AND generation_id = ?
              AND json_extract(frame_json, '$.kind') IN ('done', 'failed', 'cancelled')
            ORDER BY sequence ASC
            LIMIT 1
          `).get(input.accountId, input.generationId) as EventRow | null;
          if (winner === null) throw new TypeError("terminal chat generation has no terminal event");
          return { kind: "replay", event: eventFromRow(winner) };
        }
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
        isTerminal ? "terminal" : "active",
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

  retentionMetadata(accountId: string, generationId: string): ChatGenerationRetentionMetadata | null {
    const row = this.db.query(`
      SELECT ttl_ms, expires_at, compacted_at, replay_cursor, redacted_event_count
      FROM service_chat_generation_retention
      WHERE account_id = ? AND generation_id = ?
    `).get(accountId, generationId) as {
      readonly ttl_ms: number;
      readonly expires_at: number;
      readonly compacted_at: number | null;
      readonly replay_cursor: string;
      readonly redacted_event_count: number;
    } | null;
    return row === null ? null : Object.freeze({
      ttlMs: row.ttl_ms,
      expiresAt: row.expires_at,
      compactedAt: row.compacted_at,
      replayCursor: row.replay_cursor,
      redactedEventCount: row.redacted_event_count,
      canonicalTranscriptRetained: true,
    });
  }

  compact(
    accountId: string,
    generationId: string,
    nowEpochMilliseconds: number,
    policy: ChatGenerationRetentionPolicy,
  ): ChatGenerationCompactionResult | null {
    if (!Number.isSafeInteger(nowEpochMilliseconds) || nowEpochMilliseconds < 0
      || !Number.isSafeInteger(policy.ttlMs) || policy.ttlMs <= 0
      || policy.ttlMs > 90 * 24 * 60 * 60 * 1_000
      || !Number.isSafeInteger(policy.maxDetailEvents) || policy.maxDetailEvents < 0
      || policy.maxDetailEvents > 1_024) {
      throw new TypeError("invalid chat generation retention policy");
    }
    const compact = this.db.transaction((): ChatGenerationCompactionResult | null => {
      const rows = this.db.query(`
        SELECT event_id, generation_id, sequence, created_at, frame_json
        FROM service_chat_generation_events
        WHERE account_id = ? AND generation_id = ?
        ORDER BY sequence ASC
      `).all(accountId, generationId) as EventRow[];
      if (rows.length === 0) return null;
      const details = rows.filter((row) => {
        const kind = (JSON.parse(row.frame_json) as { readonly kind?: unknown }).kind;
        return kind === "snapshot" || kind === "delta";
      });
      const retained = new Set((policy.maxDetailEvents === 0 ? [] : details.slice(-policy.maxDetailEvents)).map((row) => row.event_id));
      let redactedEventCount = 0;
      for (const row of details) {
        if (retained.has(row.event_id) || nowEpochMilliseconds < row.created_at + policy.ttlMs) continue;
        const frame = JSON.parse(row.frame_json) as ChatGenerationFrame;
        const redacted: ChatGenerationFrame = frame.kind === "snapshot"
          ? { kind: "snapshot", text: "[redacted]" }
          : { kind: "delta", text: "[redacted]" };
        this.db.query(`
          UPDATE service_chat_generation_events SET frame_json = ?
          WHERE account_id = ? AND generation_id = ? AND event_id = ?
        `).run(JSON.stringify(redacted), accountId, generationId, row.event_id);
        redactedEventCount += 1;
      }
      const previous = this.retentionMetadata(accountId, generationId);
      const expiresAt = details.length === 0
        ? nowEpochMilliseconds + policy.ttlMs
        : Math.max(...details.map((row) => row.created_at)) + policy.ttlMs;
      const metadata = Object.freeze({
        ttlMs: policy.ttlMs,
        expiresAt,
        compactedAt: redactedEventCount === 0 ? previous?.compactedAt ?? null : nowEpochMilliseconds,
        replayCursor: rows[0]!.event_id,
        redactedEventCount: (previous?.redactedEventCount ?? 0) + redactedEventCount,
        canonicalTranscriptRetained: true as const,
      });
      this.db.query(`
        INSERT INTO service_chat_generation_retention (
          account_id, generation_id, ttl_ms, expires_at, compacted_at, replay_cursor, redacted_event_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (account_id, generation_id) DO UPDATE SET
          ttl_ms = excluded.ttl_ms,
          expires_at = excluded.expires_at,
          compacted_at = excluded.compacted_at,
          replay_cursor = excluded.replay_cursor,
          redacted_event_count = excluded.redacted_event_count
      `).run(accountId, generationId, metadata.ttlMs, metadata.expiresAt, metadata.compactedAt,
        metadata.replayCursor, metadata.redactedEventCount);
      return Object.freeze({ metadata, redactedEventCount });
    });
    return compact.immediate();
  }

  reset(): void {
    const reset = this.db.transaction(() => {
      this.db.exec("DELETE FROM service_chat_generation_events;");
      this.db.exec("DELETE FROM service_chat_generation_lifecycle;");
      this.db.exec("DELETE FROM service_chat_generation_retention;");
    });
    reset.immediate();
  }
}
