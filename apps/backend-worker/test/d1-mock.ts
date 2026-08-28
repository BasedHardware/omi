import { Database } from "bun:sqlite";

const chatSchema = [
  "CREATE TABLE IF NOT EXISTS chat_messages (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, text TEXT NOT NULL, sender TEXT NOT NULL, created_at INTEGER NOT NULL, generation_outcome TEXT, position INTEGER NOT NULL, payload TEXT)",
  "CREATE INDEX IF NOT EXISTS chat_messages_account_position ON chat_messages (account_id, position)",
  "CREATE TABLE IF NOT EXISTS chat_admissions (message_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, op_id TEXT NOT NULL, payload TEXT NOT NULL, generation_id TEXT NOT NULL)",
  "CREATE INDEX IF NOT EXISTS chat_admissions_account ON chat_admissions (account_id)",
  "CREATE INDEX IF NOT EXISTS chat_admissions_generation ON chat_admissions (generation_id)",
  "CREATE TABLE IF NOT EXISTS chat_generation_events (generation_id TEXT NOT NULL, account_id TEXT NOT NULL, event_id TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (generation_id, event_id))",
  "CREATE INDEX IF NOT EXISTS chat_generation_events_account ON chat_generation_events (account_id)",
  "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, description TEXT NOT NULL, completed INTEGER NOT NULL, completed_at INTEGER, due_at INTEGER, owner TEXT, source TEXT NOT NULL, provenance TEXT NOT NULL, sort_order REAL NOT NULL, indent_level INTEGER NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, revision TEXT)",
  "CREATE INDEX IF NOT EXISTS tasks_account_id_id ON tasks (account_id, id)",
  "CREATE TABLE IF NOT EXISTS chat_attachments (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, op_id TEXT NOT NULL, display_name TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, state TEXT NOT NULL CHECK (state IN ('staged', 'uploaded', 'ingesting', 'ingested', 'invalid', 'bound', 'expired')), r2_key TEXT NOT NULL, expires_at INTEGER NOT NULL, bound_message_id TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)",
  "CREATE INDEX IF NOT EXISTS chat_attachments_account ON chat_attachments (account_id)",
  "CREATE INDEX IF NOT EXISTS chat_attachments_account_state ON chat_attachments (account_id, state)",
  "CREATE UNIQUE INDEX IF NOT EXISTS chat_attachments_account_op ON chat_attachments (account_id, op_id)",
  "CREATE UNIQUE INDEX IF NOT EXISTS chat_attachments_r2_key ON chat_attachments (r2_key)",
  "CREATE TABLE IF NOT EXISTS device_sessions (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, device_id TEXT NOT NULL, device_name TEXT, codec INTEGER NOT NULL, state TEXT NOT NULL CHECK (state IN ('open', 'complete', 'failed')), r2_prefix TEXT NOT NULL, byte_count INTEGER NOT NULL DEFAULT 0, chunk_count INTEGER NOT NULL DEFAULT 0, started_at INTEGER NOT NULL, ended_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)",
  "CREATE INDEX IF NOT EXISTS device_sessions_account_started ON device_sessions (account_id, started_at DESC)",
  "CREATE UNIQUE INDEX IF NOT EXISTS device_sessions_r2_prefix ON device_sessions (r2_prefix)",
];

export function createD1Mock(): D1Database {
  const db = new Database(":memory:");
  for (const statement of chatSchema) db.exec(statement);

  const prepareStatement = (
    sql: string,
    bindings: unknown[] = []
  ): D1PreparedStatement => {
    const bind = (...values: unknown[]): D1PreparedStatement =>
      prepareStatement(sql, values);
    const all = async <T = Record<string, unknown>>(): Promise<D1Result<T>> => {
      const stmt = db.prepare(sql);
      const rows =
        bindings.length > 0 ? stmt.all(...(bindings as never[])) : stmt.all();
      return {
        results: rows as T[],
        success: true,
        meta: {} as never,
      };
    };
    const first = async <T = Record<string, unknown>>(): Promise<T | null> => {
      const stmt = db.prepare(sql);
      const row =
        bindings.length > 0 ? stmt.get(...(bindings as never[])) : stmt.get();
      return (row as T) ?? null;
    };
    const run = async (): Promise<D1Result<unknown>> => {
      const stmt = db.prepare(sql);
      const runResult =
        bindings.length > 0
          ? (stmt.run(...(bindings as never[])) as { changes?: number })
          : (stmt.run() as { changes?: number });
      return {
        results: [],
        success: true,
        meta: { changes: runResult?.changes ?? 0 } as never,
      };
    };
    const raw = async (): Promise<unknown[]> => {
      const stmt = db.prepare(sql);
      const rows =
        bindings.length > 0 ? stmt.all(...(bindings as never[])) : stmt.all();
      return rows as unknown[];
    };
    return {
      bind,
      all,
      first,
      run,
      raw,
    } as unknown as D1PreparedStatement;
  };

  return {
    prepare: (sql: string) => prepareStatement(sql),
    exec: async (sql: string) => {
      db.exec(sql);
    },
    batch: async (statements: D1PreparedStatement[]) => {
      const results: D1Result<unknown>[] = [];
      for (const stmt of statements) {
        results.push(await stmt.run());
      }
      return results;
    },
    withSession: () => {
      throw new Error("withSession not supported in mock");
    },
    binding: "DB" as never,
  } as unknown as D1Database;
}
