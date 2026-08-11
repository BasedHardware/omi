import type { Database } from "bun:sqlite";

import {
  createInMemoryAgentRunEventStore,
  parseAgentRunEvent,
  type AgentRunEvent,
  type AgentRunEventStore,
  type AgentRunEventStoreSnapshot,
} from "../../../apps/service/chat/agent-run-events";
import { configureServiceStoreConnection } from "./connection";

interface AgentRunEventRow {
  readonly run_id: string;
  readonly event_id: string;
  readonly sequence: number;
  readonly event_json: string;
}

const eventBytes = (event: AgentRunEvent): string => JSON.stringify(event);

const parseRow = (row: AgentRunEventRow): AgentRunEvent => {
  let parsedInput: unknown;
  try {
    parsedInput = JSON.parse(row.event_json);
  } catch {
    throw new TypeError("corrupt agent run event JSON");
  }
  const parsed = parseAgentRunEvent(parsedInput);
  if (!parsed.ok || parsed.event.runId !== row.run_id
    || parsed.event.eventId !== row.event_id || parsed.event.sequence !== row.sequence) {
    throw new TypeError("corrupt agent run event row");
  }
  return parsed.event;
};

const rowsSnapshot = (db: Database): AgentRunEventStoreSnapshot => {
  const rows = db.query(`
    SELECT run_id, event_id, sequence, event_json
    FROM service_agent_run_events
    ORDER BY run_id ASC, sequence ASC
  `).all() as AgentRunEventRow[];
  const grouped = new Map<string, AgentRunEvent[]>();
  for (const row of rows) {
    const event = parseRow(row);
    const events = grouped.get(row.run_id) ?? [];
    events.push(event);
    grouped.set(row.run_id, events);
  }
  return {
    runs: [...grouped.entries()].map(([runId, events]) => ({ runId, events })),
  };
};

const hydrate = (db: Database): ReturnType<typeof createInMemoryAgentRunEventStore> => {
  const store = createInMemoryAgentRunEventStore();
  const snapshot = rowsSnapshot(db);
  if (snapshot.runs.length > 0) store.restore(snapshot);
  return store;
};

/** Strict durable AgentRunEventStore backed by the service SQLite database. */
export class SqliteAgentRunEventStore implements AgentRunEventStore {
  constructor(private readonly db: Database) {
    configureServiceStoreConnection(db);
    db.exec(`
      CREATE TABLE IF NOT EXISTS service_agent_run_events (
        run_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        event_json TEXT NOT NULL,
        PRIMARY KEY (run_id, event_id),
        UNIQUE (run_id, sequence)
      );
      CREATE INDEX IF NOT EXISTS service_agent_run_events_by_run
        ON service_agent_run_events (run_id, sequence);
    `);
    // Construction is a corruption boundary: malformed rows never become a
    // partially usable timeline and are not silently discarded.
    rowsSnapshot(db);
  }

  append(input: unknown): ReturnType<AgentRunEventStore["append"]> {
    return this.db.transaction(() => {
      const store = hydrate(this.db);
      const outcome = store.append(input);
      if (outcome.kind !== "appended") return outcome;
      const event = outcome.event;
      this.db.query(`
        INSERT INTO service_agent_run_events (run_id, event_id, sequence, event_json)
        VALUES (?, ?, ?, ?)
      `).run(event.runId, event.eventId, event.sequence, eventBytes(event));
      return outcome;
    })();
  }

  list(runId: string): readonly AgentRunEvent[] {
    const store = hydrate(this.db);
    return store.list(runId);
  }

  snapshot(): AgentRunEventStoreSnapshot {
    return hydrate(this.db).snapshot();
  }

  restore(snapshot: unknown): void {
    const next = createInMemoryAgentRunEventStore();
    next.restore(snapshot);
    this.db.transaction(() => {
      // Validate existing bytes before replacement so a corrupt store cannot be
      // laundered by an unrelated restore call.
      rowsSnapshot(this.db);
      this.db.exec("DELETE FROM service_agent_run_events;");
      for (const run of next.snapshot().runs) {
        for (const event of run.events) {
          this.db.query(`
            INSERT INTO service_agent_run_events (run_id, event_id, sequence, event_json)
            VALUES (?, ?, ?, ?)
          `).run(event.runId, event.eventId, event.sequence, eventBytes(event));
        }
      }
    })();
  }

  reset(): void {
    this.db.exec("DELETE FROM service_agent_run_events;");
  }
}

export const createSqliteAgentRunEventStore = (db: Database): AgentRunEventStore =>
  new SqliteAgentRunEventStore(db);
