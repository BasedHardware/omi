-- Forward-only rebuild: tenant-scoped primary keys for chat and tasks.
-- Duplicate ids may exist across accounts after this migration; they must not
-- collide inside one account. Do not apply to shared D1 from this change set
-- without the operator migration sequence.
PRAGMA foreign_keys=OFF;

CREATE TABLE chat_messages_v10 (
  account_id TEXT NOT NULL,
  id TEXT NOT NULL,
  text TEXT NOT NULL,
  sender TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  generation_outcome TEXT,
  position INTEGER NOT NULL,
  payload TEXT,
  PRIMARY KEY (account_id, id)
);
INSERT INTO chat_messages_v10 (
  account_id, id, text, sender, created_at, generation_outcome, position, payload
)
SELECT account_id, id, text, sender, created_at, generation_outcome, position, payload
FROM chat_messages;
DROP TABLE chat_messages;
ALTER TABLE chat_messages_v10 RENAME TO chat_messages;
CREATE INDEX IF NOT EXISTS chat_messages_account_position ON chat_messages (account_id, position);

CREATE TABLE chat_admissions_v10 (
  account_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  op_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  generation_id TEXT NOT NULL,
  PRIMARY KEY (account_id, message_id)
);
INSERT INTO chat_admissions_v10 (
  account_id, message_id, op_id, payload, generation_id
)
SELECT account_id, message_id, op_id, payload, generation_id
FROM chat_admissions;
DROP TABLE chat_admissions;
ALTER TABLE chat_admissions_v10 RENAME TO chat_admissions;
CREATE INDEX IF NOT EXISTS chat_admissions_account ON chat_admissions (account_id);
CREATE INDEX IF NOT EXISTS chat_admissions_generation ON chat_admissions (generation_id);
CREATE UNIQUE INDEX IF NOT EXISTS chat_admissions_account_generation
  ON chat_admissions (account_id, generation_id);

CREATE TABLE chat_generation_events_v10 (
  account_id TEXT NOT NULL,
  generation_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (account_id, generation_id, event_id)
);
INSERT INTO chat_generation_events_v10 (
  account_id, generation_id, event_id, ordinal, payload
)
SELECT account_id, generation_id, event_id, ordinal, payload
FROM chat_generation_events;
DROP TABLE chat_generation_events;
ALTER TABLE chat_generation_events_v10 RENAME TO chat_generation_events;
CREATE INDEX IF NOT EXISTS chat_generation_events_account ON chat_generation_events (account_id);

CREATE TABLE tasks_v10 (
  account_id TEXT NOT NULL,
  id TEXT NOT NULL,
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
  revision TEXT,
  PRIMARY KEY (account_id, id)
);
INSERT INTO tasks_v10 (
  account_id, id, description, completed, completed_at, due_at, owner, source,
  provenance, sort_order, indent_level, created_at, updated_at, revision
)
SELECT account_id, id, description, completed, completed_at, due_at, owner, source,
  provenance, sort_order, indent_level, created_at, updated_at, revision
FROM tasks;
DROP TABLE tasks;
ALTER TABLE tasks_v10 RENAME TO tasks;
CREATE INDEX IF NOT EXISTS tasks_account_id_id ON tasks (account_id, id);

PRAGMA foreign_keys=ON;
