CREATE TABLE IF NOT EXISTS device_sessions (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  device_name TEXT,
  codec INTEGER NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('open', 'complete', 'failed')),
  r2_prefix TEXT NOT NULL,
  byte_count INTEGER NOT NULL DEFAULT 0,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  started_at INTEGER NOT NULL,
  ended_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS device_sessions_account_started
  ON device_sessions (account_id, started_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS device_sessions_r2_prefix
  ON device_sessions (r2_prefix);
