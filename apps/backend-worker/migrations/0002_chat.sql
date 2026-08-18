CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  text TEXT NOT NULL,
  sender TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  generation_outcome TEXT,
  position INTEGER NOT NULL,
  payload TEXT
);

CREATE INDEX IF NOT EXISTS chat_messages_account_position ON chat_messages (account_id, position);

CREATE TABLE IF NOT EXISTS chat_admissions (
  message_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  op_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  generation_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS chat_admissions_account ON chat_admissions (account_id);
CREATE INDEX IF NOT EXISTS chat_admissions_generation ON chat_admissions (generation_id);

CREATE TABLE IF NOT EXISTS chat_generation_events (
  generation_id TEXT NOT NULL,
  account_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (generation_id, event_id)
);

CREATE INDEX IF NOT EXISTS chat_generation_events_account ON chat_generation_events (account_id);
