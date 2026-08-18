CREATE TABLE IF NOT EXISTS chat_attachments (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  op_id TEXT NOT NULL,
  display_name TEXT NOT NULL,
  media_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('staged', 'uploaded', 'ingesting', 'ingested', 'invalid', 'bound', 'expired')),
  r2_key TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  bound_message_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS chat_attachments_account ON chat_attachments (account_id);
CREATE INDEX IF NOT EXISTS chat_attachments_account_state ON chat_attachments (account_id, state);
CREATE UNIQUE INDEX IF NOT EXISTS chat_attachments_account_op ON chat_attachments (account_id, op_id);
CREATE UNIQUE INDEX IF NOT EXISTS chat_attachments_r2_key ON chat_attachments (r2_key);
