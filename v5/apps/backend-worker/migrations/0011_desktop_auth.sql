CREATE TABLE desktop_auth_sessions (
  id TEXT PRIMARY KEY,
  verifier_challenge TEXT NOT NULL,
  confirmation_challenge TEXT NOT NULL,
  client_ip TEXT NOT NULL,
  uid TEXT,
  confirmation_attempts INTEGER NOT NULL DEFAULT 0,
  confirmation_locked_at INTEGER,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER
);

CREATE INDEX desktop_auth_sessions_expiry_idx
  ON desktop_auth_sessions(expires_at, consumed_at);
