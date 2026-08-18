CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  description TEXT NOT NULL,
  completed INTEGER NOT NULL CHECK (completed IN (0, 1)),
  completed_at INTEGER,
  due_at INTEGER,
  owner TEXT,
  source TEXT NOT NULL,
  provenance TEXT NOT NULL,
  sort_order REAL NOT NULL,
  indent_level INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  revision TEXT
);

CREATE INDEX IF NOT EXISTS tasks_account_id_id ON tasks (account_id, id);
