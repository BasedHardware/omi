ALTER TABLE device_sessions ADD COLUMN uploaded_chunk_count INTEGER NOT NULL DEFAULT 0;
UPDATE device_sessions SET state = 'failed', ended_at = COALESCE(ended_at, updated_at) WHERE state = 'open' AND chunk_count > 0;
