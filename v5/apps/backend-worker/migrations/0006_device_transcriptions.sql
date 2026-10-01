CREATE TABLE device_transcriptions (
  session_id TEXT PRIMARY KEY REFERENCES device_sessions(id) ON DELETE CASCADE,
  account_id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'completed', 'failed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  lease_token TEXT,
  available_at INTEGER NOT NULL,
  text TEXT,
  segments TEXT,
  language TEXT,
  discarded_leading_packets INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  updated_at INTEGER NOT NULL
);
CREATE INDEX device_transcriptions_due ON device_transcriptions(state, available_at);
CREATE INDEX device_transcriptions_account ON device_transcriptions(account_id);
CREATE TRIGGER device_session_transcription_ready
AFTER UPDATE OF state ON device_sessions
WHEN NEW.state = 'complete' AND OLD.state = 'open'
  AND NEW.chunk_count > 0 AND NEW.uploaded_chunk_count = NEW.chunk_count
BEGIN
  INSERT INTO device_transcriptions (session_id, account_id, available_at, updated_at)
  VALUES (NEW.id, NEW.account_id, NEW.updated_at, NEW.updated_at);
END;
