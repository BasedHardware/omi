ALTER TABLE device_sessions ADD COLUMN capture_id TEXT;
CREATE UNIQUE INDEX device_sessions_account_capture
ON device_sessions (account_id, capture_id);
